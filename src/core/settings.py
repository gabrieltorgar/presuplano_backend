"""Django settings for presuplano backend.

Modular settings: this file holds Django's own config and initializes
``environ`` once. STATIC/MEDIA/security live in ``core.env``; each third-party
library with significant config gets its own ``settings_<name>.py``.
"""

from pathlib import Path

import environ

# BASE_DIR = repo root (parents: settings.py -> core -> src -> repo)
BASE_DIR = Path(__file__).resolve().parents[2]

env = environ.Env(
    DEBUG=(bool, True),
    SECRET_KEY=(str, "dev-insecure-change-me"),
    ALLOWED_HOSTS=(list, ["*"]),
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

DEBUG = env("DEBUG")
SECRET_KEY = env("SECRET_KEY")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")

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
    # Local apps
    "apps.accounts",
    "apps.catalog",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
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
        "DIRS": [BASE_DIR / "src" / "templates"],
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
ASGI_APPLICATION = "core.asgi.application"

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

# STATIC/MEDIA + security + logging
from .env import *  # noqa: E402,F403
from .logging_config import LOGGING  # noqa: E402,F401
