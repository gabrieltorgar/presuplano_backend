"""Django settings for presuplano backend.

Modular settings: this file holds Django's own config and initializes
``environ`` once. STATIC/MEDIA/security live in ``core.env``; each third-party
library with significant config gets its own ``settings_<name>.py``.
"""

from pathlib import Path

import environ

# BASE_DIR = repo root (parents: settings.py -> core -> src -> repo)
BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, True),
    SECRET_KEY=(str, "dev-insecure-change-me"),
    ALLOWED_HOSTS=(list, ["*"]),
    CSRF_TRUSTED_ORIGINS=(list, []),
    CORS_ALLOWED_ORIGINS=(list, ["http://localhost:5173"]),
    DATABASE_URL=(str, f"sqlite:///{BASE_DIR / 'db.sqlite3'}"),
    LOG_DIR=(str, str(BASE_DIR / "tmp" / "logs")),
    OTP_UNIVERSAL_CODE=(str, "123456"),
    OTP_TTL_MINUTES=(int, 10),
)

# Load .env from core/ if present (optional — all vars have safe defaults).
_env_file = BASE_DIR / "src" / "core" / ".env"
if _env_file.exists():
    environ.Env.read_env(str(_env_file))

# Vercel injects VERCEL=1 in build and runtime; harden defaults there
# (DEBUG off by default and the deployment's own hostnames trusted).
ON_VERCEL = env.bool("VERCEL", default=False)

DEBUG = env.bool("DEBUG", default=not ON_VERCEL)
SECRET_KEY = env("SECRET_KEY")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env("CSRF_TRUSTED_ORIGINS")

# On Vercel, trust the deployment's own hostnames so ALLOWED_HOSTS, CSRF and the
# admin login keep working on preview/production URLs without per-deploy config.
_VERCEL_HOSTS = [
    host
    for host in (
        env.str("VERCEL_URL", default=""),
        env.str("VERCEL_BRANCH_URL", default=""),
        env.str("VERCEL_PROJECT_PRODUCTION_URL", default=""),
    )
    if host
]
if _VERCEL_HOSTS:
    ALLOWED_HOSTS = list(dict.fromkeys(ALLOWED_HOSTS + _VERCEL_HOSTS))
    CSRF_TRUSTED_ORIGINS = list(
        dict.fromkeys(CSRF_TRUSTED_ORIGINS + [f"https://{h}" for h in _VERCEL_HOSTS])
    )

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "rest_framework",
    "corsheaders",
    "django_filters",
    "storages",
    # Local apps
    "apps.accounts",
    "apps.catalog",
    "apps.clients",
    "apps.quotes",
    "apps.projects",
    "apps.payments",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    # WhiteNoise serves static files (admin/DRF) from the serverless function;
    # must sit right after SecurityMiddleware.
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "core.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "core.wsgi.application"

DATABASES = {"default": env.db("DATABASE_URL")}

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 8},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "es"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- DRF ---
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_FILTER_BACKENDS": ("django_filters.rest_framework.DjangoFilterBackend",),
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
}

# --- OTP (universal code for the MVP; real SMS/WhatsApp integration later) ---
OTP_UNIVERSAL_CODE = env("OTP_UNIVERSAL_CODE")
OTP_TTL_MINUTES = env("OTP_TTL_MINUTES")

# --- CORS ---
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = env("CORS_ALLOWED_ORIGINS")
CORS_ALLOW_CREDENTIALS = True

# STATIC/MEDIA + security + logging + storages (media on R2 in production)
from .env import *  # noqa: E402,F403
from .settings_storages import *  # noqa: E402,F403
