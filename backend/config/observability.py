"""Request correlation and structured logging (Spec 05 Phase 8).

Every request gets an id: reused from an inbound ``X-Request-ID`` when a proxy
supplies one, otherwise generated. It is bound to a contextvar for the life of
the request, stamped onto every log record by :class:`RequestIDFilter`, and
echoed back in the response header, so one id ties a client error, the server's
log lines, and the upstream trace together.

Celery tasks bind the same context with :func:`bind_request_id`, so worker log
lines for a job carry the id its request started with. Together with
``LOG_FORMAT=json`` this is the substrate a log pipeline alerts and builds
provider dashboards on.
"""
import json
import logging
import uuid
from contextlib import contextmanager
from contextvars import ContextVar, Token
from datetime import datetime, timezone

# Bound per request (or per task). Empty outside any context.
_request_id: ContextVar[str] = ContextVar("request_id", default="")

HEADER = "X-Request-ID"

# A client/proxy-supplied id is trusted only up to a sane length: it is echoed
# in headers and written to logs, so an unbounded value is an injection and
# log-flooding surface.
MAX_REQUEST_ID_LENGTH = 200


def new_request_id() -> str:
    return uuid.uuid4().hex


def get_request_id() -> str:
    return _request_id.get()


def set_request_id(value: str) -> Token:
    return _request_id.set(value or "")


def reset_request_id(token: Token) -> None:
    _request_id.reset(token)


@contextmanager
def bind_request_id(value: str = ""):
    """Bind a request id for a block (e.g. a Celery task), then restore it."""
    token = set_request_id(value or new_request_id())
    try:
        yield get_request_id()
    finally:
        reset_request_id(token)


class RequestIDMiddleware:
    """Assign a request id, expose it on the response, and bind it for logging.

    Placed outermost so the id is set before any inner middleware or view runs
    and is present on the response of every request that reaches the app.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        incoming = request.META.get("HTTP_X_REQUEST_ID", "")
        request_id = incoming[:MAX_REQUEST_ID_LENGTH] if incoming else new_request_id()
        token = set_request_id(request_id)
        request.request_id = request_id
        try:
            response = self.get_response(request)
        finally:
            reset_request_id(token)
        response[HEADER] = request_id
        return response


class RequestIDFilter(logging.Filter):
    """Stamp each record with the current request id (``-`` when none).

    Falls back to the request carried on the record: Django logs 4xx/5xx
    responses *after* the middleware chain has unwound and the contextvar is
    cleared, but it passes ``request`` in ``extra`` and the middleware stored
    the id on it — so those summary lines stay correlatable too.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        request_id = get_request_id()
        if not request_id:
            request = getattr(record, "request", None)
            request_id = getattr(request, "request_id", "") if request is not None else ""
        record.request_id = request_id or "-"
        return True


class JsonFormatter(logging.Formatter):
    """One JSON object per line, so logs are machine-parseable.

    Extra structured fields are passed as ``logger.info("...", extra={
    "structured": {"provider": "x", "outcome": "error", "latency_ms": 812}})``
    and merged into the object — the shape a provider-failure dashboard reads.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", None) or get_request_id() or "-",
        }
        # django.request carries the response status on the record; surfacing it
        # is what a request-error-rate dashboard reads.
        status_code = getattr(record, "status_code", None)
        if status_code is not None:
            payload["status_code"] = status_code
        payload.update(getattr(record, "structured", {}) or {})
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)
