"""Static/media paths and security settings.

Imported via ``from .env import *`` in ``settings.py`` (assumes ``.env`` already
loaded). Holds STATIC_*, MEDIA_*, and SSL/cookie security. The security block is
guarded by ``if not DEBUG``; HttpOnly/SameSite cookies are always on.
"""

from pathlib import Path

import environ

_env = environ.Env()
BASE_DIR = Path(__file__).resolve().parent

# Mirror settings.DEBUG: safe by default (False) on Vercel, True locally.
_ON_VERCEL = _env.bool("VERCEL", default=False)
DEBUG = _env.bool("DEBUG", default=not _ON_VERCEL)

# --- Static ---
# On Vercel (read-only fs) STATIC_ROOT must live under /tmp so an optional
# collectstatic can write; WhiteNoise's finders (below) serve straight from the
# apps' static dirs at request time, so it need not even exist.
STATIC_URL = _env.str("STATIC_URL", default="static/")
_default_static_root = "/tmp/static" if _ON_VERCEL else str(BASE_DIR / "static")  # noqa: S108
STATIC_ROOT = _env.str("STATIC_ROOT", default=_default_static_root)
STATICFILES_DIRS = [d for d in (BASE_DIR.parent / "static",) if d.exists()]
# WhiteNoise serves admin/DRF static from finders (no collectstatic dependency).
WHITENOISE_USE_FINDERS = True
WHITENOISE_AUTOREFRESH = DEBUG

# --- Media ---
MEDIA_URL = _env.str("MEDIA_URL", default="/media/")
MEDIA_ROOT = _env.str("MEDIA_ROOT", default=os.path.join(REPO_ROOT, "media"))

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
