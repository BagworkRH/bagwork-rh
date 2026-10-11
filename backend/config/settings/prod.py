"""Production settings. Safety-critical defaults: DEBUG off, HTTPS, secure cookies."""
from .base import *  # noqa: F401,F403
from .base import ALLOWED_HOSTS, CORS_ALLOWED_ORIGINS  # noqa: F401

DEBUG = False
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# Nginx terminates TLS and speaks plain HTTP to Gunicorn, so without this Django
# never learns the original request was https — and SECURE_SSL_REDIRECT would
# then redirect every request to itself, forever. The matching header is set in
# deploy/nginx/app.conf.template.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
