"""Production settings: strict transport security, no debugging."""

from .base import *  # noqa: F401,F403
from .base import env

DEBUG = False

# Both must be provided by the environment — no insecure fallbacks.
SECRET_KEY = env("SECRET_KEY")
DATABASES = {"default": env.db("DATABASE_URL")}
DATABASES["default"]["ATOMIC_REQUESTS"] = True
DATABASES["default"]["CONN_MAX_AGE"] = env.int("CONN_MAX_AGE", default=60)

SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 60 * 60 * 24 * 365
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# Registry data is clinical: sessions expire after 8 hours of inactivity.
SESSION_COOKIE_AGE = 60 * 60 * 8
SESSION_SAVE_EVERY_REQUEST = True
