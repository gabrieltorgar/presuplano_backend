"""Static/media paths and security settings.

Imported via ``from .env import *`` in ``settings.py`` (assumes ``.env`` already
loaded). Holds STATIC_*, MEDIA_*, and SSL/cookie security. The security block is
guarded by ``if not DEBUG``; HttpOnly/SameSite cookies are always on.
"""

from pathlib import Path

import environ

_env = environ.Env()
BASE_DIR = Path(__file__).resolve().parents[2]

DEBUG = _env.bool("DEBUG", default=True)

# --- Static & media ---
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# --- Cookie security (always on) ---
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Lax"

# --- Production security (only when DEBUG is off) ---
if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_BROWSER_XSS_FILTER = True
    X_FRAME_OPTIONS = "DENY"
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
