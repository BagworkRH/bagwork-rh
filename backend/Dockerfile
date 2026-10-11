# bagworkRH backend image — Gunicorn and Celery from one build.
#
# The web, worker and beat containers all run this image and differ only in
# their command. That is deliberate: they must execute identical code, and one
# image makes that structural rather than something to remember.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DJANGO_SETTINGS_MODULE=config.settings.prod

# curl is for the healthcheck; libpq5 is what the psycopg2 binary wheel links to.
RUN apt-get update \
 && apt-get install --no-install-recommends -y curl libpq5 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Requirements first, so editing app code does not re-resolve the whole tree.
COPY requirements/ requirements/
RUN pip install --upgrade pip && pip install -r requirements/prod.txt

COPY . .

# Run unprivileged: the process binds 8000, never a privileged port.
# The chmod exists because Windows checkouts carry no executable bit, and an
# entrypoint that is not executable is a container that will not start.
RUN useradd --create-home --shell /bin/bash app \
 && chmod +x /app/docker-entrypoint.sh \
 && mkdir -p /app/staticfiles \
 && chown -R app:app /app
USER app

EXPOSE 8000

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "3", "--threads", "2", \
     "--timeout", "60", \
     "--access-logfile", "-", "--error-logfile", "-"]
