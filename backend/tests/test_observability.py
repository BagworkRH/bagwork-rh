"""Request correlation and structured logging (Spec 05 Phase 8)."""
import json
import logging
from types import SimpleNamespace

from django.http import HttpResponse
from django.test import RequestFactory, TestCase

from config.observability import (
    MAX_REQUEST_ID_LENGTH,
    JsonFormatter,
    RequestIDFilter,
    RequestIDMiddleware,
    bind_request_id,
    get_request_id,
    new_request_id,
)


def _record(**extra):
    record = logging.LogRecord("test", logging.INFO, __file__, 1, "hello", None, None)
    for key, value in extra.items():
        setattr(record, key, value)
    return record


class RequestIDMiddlewareTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def _call(self, **meta):
        seen = {}

        def view(request):
            # A log line emitted inside the view must carry the same id the
            # response is stamped with — that is the whole point of the id.
            record = _record()
            RequestIDFilter().filter(record)
            seen["request_id"] = record.request_id
            return HttpResponse("ok")

        response = RequestIDMiddleware(view)(self.factory.get("/", **meta))
        return response, seen

    def test_generates_an_id_when_none_supplied(self):
        response, seen = self._call()
        header = response["X-Request-ID"]
        self.assertTrue(header)
        self.assertEqual(header, seen["request_id"])

    def test_reuses_an_inbound_id(self):
        response, seen = self._call(HTTP_X_REQUEST_ID="trace-abc-123")
        self.assertEqual(response["X-Request-ID"], "trace-abc-123")
        self.assertEqual(seen["request_id"], "trace-abc-123")

    def test_truncates_an_overlong_inbound_id(self):
        response, _ = self._call(HTTP_X_REQUEST_ID="a" * 500)
        self.assertEqual(len(response["X-Request-ID"]), MAX_REQUEST_ID_LENGTH)

    def test_id_is_not_leaked_after_the_request(self):
        self._call()
        self.assertEqual(get_request_id(), "")


class RequestIDFilterTests(TestCase):
    def test_stamps_the_current_request_id(self):
        record = _record()
        with bind_request_id("abc123"):
            RequestIDFilter().filter(record)
        self.assertEqual(record.request_id, "abc123")

    def test_uses_a_placeholder_outside_a_request(self):
        record = _record()
        RequestIDFilter().filter(record)
        self.assertEqual(record.request_id, "-")

    def test_falls_back_to_the_request_carried_on_the_record(self):
        # Django logs 4xx/5xx after the context is cleared but passes `request`.
        record = _record(request=SimpleNamespace(request_id="from-request"))
        RequestIDFilter().filter(record)
        self.assertEqual(record.request_id, "from-request")


class JsonFormatterTests(TestCase):
    def test_emits_parseable_json_with_the_request_id(self):
        record = _record()
        with bind_request_id("req-1"):
            RequestIDFilter().filter(record)
        payload = json.loads(JsonFormatter().format(record))
        self.assertEqual(payload["level"], "INFO")
        self.assertEqual(payload["message"], "hello")
        self.assertEqual(payload["request_id"], "req-1")
        self.assertIn("timestamp", payload)

    def test_merges_structured_extra_fields(self):
        # The shape a provider-failure dashboard reads.
        record = _record(structured={"provider": "x", "outcome": "error", "latency_ms": 812})
        payload = json.loads(JsonFormatter().format(record))
        self.assertEqual(payload["provider"], "x")
        self.assertEqual(payload["latency_ms"], 812)

    def test_includes_status_code_when_present(self):
        record = _record(status_code=404)
        payload = json.loads(JsonFormatter().format(record))
        self.assertEqual(payload["status_code"], 404)


class BindRequestIDTests(TestCase):
    def test_binds_and_restores(self):
        self.assertEqual(get_request_id(), "")
        with bind_request_id("outer"):
            self.assertEqual(get_request_id(), "outer")
            with bind_request_id():
                self.assertNotEqual(get_request_id(), "outer")
                self.assertTrue(get_request_id())
            self.assertEqual(get_request_id(), "outer")
        self.assertEqual(get_request_id(), "")

    def test_new_request_id_is_unique(self):
        self.assertNotEqual(new_request_id(), new_request_id())


class RequestIDWiringTests(TestCase):
    """The middleware must be in MIDDLEWARE, so real responses carry the header."""

    def test_health_response_carries_a_request_id_header(self):
        response = self.client.get("/api/health/")
        self.assertIn("X-Request-ID", response)
        self.assertTrue(response["X-Request-ID"])


class _CaptureHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(record)


class RequestLogCorrelationTests(TestCase):
    """A 4xx request's own log line must carry the same id as its response."""

    def test_django_request_log_matches_the_response_header(self):
        handler = _CaptureHandler()
        handler.addFilter(RequestIDFilter())
        logger = logging.getLogger("django.request")
        logger.addHandler(handler)
        try:
            # Unauthenticated claim list -> 401, which django.request logs.
            response = self.client.get("/api/v1/claims/")
        finally:
            logger.removeHandler(handler)

        self.assertGreaterEqual(response.status_code, 400)
        correlated = [r for r in handler.records if getattr(r, "request_id", "-") != "-"]
        self.assertTrue(correlated, "no correlated django.request log line")
        self.assertEqual(correlated[-1].request_id, response["X-Request-ID"])
