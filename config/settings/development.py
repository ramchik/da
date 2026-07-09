"""Development settings: permissive defaults so a fresh checkout runs."""

from .base import *  # noqa: F401,F403
from .base import env

DEBUG = env.bool("DEBUG", default=True)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
