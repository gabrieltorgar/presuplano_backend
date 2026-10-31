"""Django settings for Itzaka backend.

Modular settings: this file holds Django's own config and initializes
``environ`` once. STATIC/MEDIA/security live in ``core.env``; each third-party
library with significant config gets its own ``settings_<name>.py``.
"""

import tomllib
from datetime import timedelta
from pathlib import Path

import environ
from corsheaders.defaults import default_headers

# BASE_DIR = repo root (parents: settings.py -> core -> src -> repo)
BASE_DIR = Path(__file__).resolve().parent.parent

# The release number lives only in pyproject.toml ([project].version): git-deploy-ops
# set_version.py bumps it in the «Versión X.Y.Z» commit. Never a literal (DOC-VER02).
with (BASE_DIR.parent / "pyproject.toml").open("rb") as pyproject:
    APP_VERSION: str = tomllib.load(pyproject)["project"]["version"]

env = environ.Env(
    DEBUG=(bool, True),
    SECRET_KEY=(str, "dev-insecure-change-me"),
    ALLOWED_HOSTS=(list, ["*"]),
    DATABASE_URL=(str, f"sqlite:///{BASE_DIR / 'db.sqlite3'}"),
    LOG_DIR=(str, str(BASE_DIR / "tmp" / "logs")),
    OTP_UNIVERSAL_CODE=(str, "123456"),
    OTP_TTL_MINUTES=(int, 10),
    # Intentos fallidos que aguanta un código antes de morir (iteracion-12).
    OTP_MAX_ATTEMPTS=(int, 5),
    THROTTLE_ANON=(str, "60/min"),
    THROTTLE_USER=(str, "300/min"),
    # Long enough to keep an active session working; a refresh token silently
    # renews access so the user is not logged out mid-use (see /auth/refresh/).
    ACCESS_TOKEN_LIFETIME_MINUTES=(int, 30),
    REFRESH_TOKEN_LIFETIME_DAYS=(int, 7),
)

# Load .env from core/ if present (optional — all vars have safe defaults).
# BASE_DIR is src/, so the file is src/core/.env. It is only a local fallback:
# read_env never overrides what the environment already holds (Infisical's
# `infisical sm run` or Vercel), so a stale .env never beats the vault.
_env_file = BASE_DIR / "core" / ".env"
if _env_file.exists():
    environ.Env.read_env(str(_env_file))

# Vercel injects VERCEL=1 in build and runtime; harden defaults there
# (DEBUG off by default and the deployment's own hostnames trusted).
ON_VERCEL = env.bool("VERCEL", default=False)

DEBUG = env.bool("DEBUG", default=not ON_VERCEL)
SECRET_KEY = env("SECRET_KEY")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")
# Orígenes exactos (https://app.dominio.com), nunca comodines.
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

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
    # Unfold antes del admin de Django, o sus plantillas nunca cargan.
    "unfold",
    "unfold.contrib.filters",
    "unfold.contrib.forms",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "csp",
    "django_filters",
    "phonenumber_field",
    "storages",
    # Local apps
    "apps.accounts",
    "apps.catalog",
    "apps.clients",
    "apps.quotes",
    "apps.projects",
    "apps.payments",
    "apps.leads",
    "apps.planner",
    "apps.staff",
    "apps.dashboard",
    "apps.assets",
    "apps.documents",
    "apps.legal",
    "apps.team",
    "apps.folios",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    # WhiteNoise serves static files (admin/DRF) from the serverless function;
    # must sit right after SecurityMiddleware.
    "whitenoise.middleware.WhiteNoiseMiddleware",
    # Content-Security-Policy (settings_csp.py), con lo que Unfold necesita
    # sólo bajo /admin/ (common/csp.py).
    "common.csp.ScopedCSPMiddleware",
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
        "DIRS": [BASE_DIR / "templates"],
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
# El pooler de Neon corre PgBouncer en modo transacción: los cursores del
# servidor (.iterator()) se rompen entre transacciones, y tras el reposo de Neon
# una conexión guardada puede estar muerta. Conexiones cortas y revisadas antes
# de reusarse.
DATABASES["default"].update(
    {
        "CONN_MAX_AGE": env.int("CONN_MAX_AGE", default=0),
        "CONN_HEALTH_CHECKS": True,
        "DISABLE_SERVER_SIDE_CURSORS": True,
    }
)

AUTH_USER_MODEL = "accounts.User"
# La única pantalla con sesión de Django es el admin, y el login de Unfold no
# manda «next»: sin esto, entrar llevaba a /accounts/profile/ (404).
LOGIN_REDIRECT_URL = "admin:index"

# Se aplican de verdad al registrarse, recuperar y cambiar la contraseña
# (accounts.services.check_password_strength), no sólo en el admin.
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": (
            "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
        )
    },
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
    # El access llega en una cookie HttpOnly (common/auth_cookies.py); la
    # cabecera Authorization sigue sirviendo a clientes de API.
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "common.authentication.CookieJWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    # El servidor filtra, busca (sin acentos) y ordena cada lista; la pantalla
    # pide solo la página que muestra (api-lists-errors.md §1, iteracion-17).
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "common.search.AccentInsensitiveSearchFilter",
        "common.search.AccentInsensitiveOrderingFilter",
    ),
    # Siempre pagina: 20 por omisión y nunca más de 100 por página.
    "DEFAULT_PAGINATION_CLASS": "common.pagination.DefaultPagination",
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
    # Límites por dirección o por cuenta en todo, y uno propio en cada puerta
    # pública: sin tope, un código de seis dígitos se adivina probando.
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.ScopedRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "anon": env("THROTTLE_ANON"),
        "user": env("THROTTLE_USER"),
        "login": "10/min",
        "signup": "10/hour",
        "otp": "5/min",
        "password_reset": "5/hour",
        "contact": "5/hour",
        "documents": "30/hour",
        "invitations": "30/hour",
        "invitation": "30/min",
        # Acciones en lote (common/bulk.py): cada una puede tocar hasta
        # BULK_MAX_ITEMS registros, así que tienen su propio límite.
        "bulk": "30/min",
    },
    # Detrás del proxy de Vercel, la dirección real es la del X-Forwarded-For.
    "NUM_PROXIES": env.int("NUM_PROXIES", default=1),
    "EXCEPTION_HANDLER": "common.exceptions.api_exception_handler",
    # JSON y nada más en producción: la API navegable es una página más que
    # cuidar (y que pone estilos en línea, que la CSP no deja pasar).
    "DEFAULT_RENDERER_CLASSES": (
        ("rest_framework.renderers.JSONRenderer",)
        + (("rest_framework.renderers.BrowsableAPIRenderer",) if DEBUG else ())
    ),
}

# --- Acciones en lote (common/bulk.py) ---
# Cuántos registros toca una acción a la vez; el frontend repite el número
# (src/types/api.ts) para no ofrecer «Seleccionar los N resultados» por encima.
BULK_MAX_ITEMS = env.int("BULK_MAX_ITEMS", default=500)
# Las costosas (mandan correo, generan documentos) tienen un tope menor.
BULK_COSTLY_MAX_ITEMS = env.int("BULK_COSTLY_MAX_ITEMS", default=50)

# --- Caché compartida (estado de los límites) ---
# En Vercel cada invocación puede ser otra instancia: una caché en memoria no
# cuenta nada. La tabla vive en la misma base y la crea el build
# (createcachetable); las pruebas usan memoria local (conftest.py).
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "itzaka_cache",
    }
}

# --- SimpleJWT (sesión en cookies HttpOnly, iteracion-12) ---
# Media hora de access y una semana de refresh como máximo, aunque el entorno
# pida más: una sesión robada vale poco y por poco tiempo. El refresh rota en
# cada renovación y el usado queda en la lista negra; salir lo anula.
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(
        minutes=min(env("ACCESS_TOKEN_LIFETIME_MINUTES"), 30)
    ),
    "REFRESH_TOKEN_LIFETIME": timedelta(
        days=min(env("REFRESH_TOKEN_LIFETIME_DAYS"), 7)
    ),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": False,
}

# --- OTP (universal code for the MVP; real SMS/WhatsApp integration later) ---
# Con correo configurado, una cuenta con correo recibe un código propio y este
# deja de servirle; sigue siendo el de las cuentas que sólo tienen teléfono,
# porque todavía no hay SMS por donde mandarles el suyo.
OTP_UNIVERSAL_CODE = env("OTP_UNIVERSAL_CODE")
# Y sólo donde se pidió: en local (DEBUG) sí; en producción hay que pedirlo a
# propósito, para que una llave de correo que falte no abra todas las cuentas.
OTP_UNIVERSAL_CODE_ENABLED = env.bool("OTP_UNIVERSAL_CODE_ENABLED", default=DEBUG)
OTP_MAX_ATTEMPTS = env("OTP_MAX_ATTEMPTS")

# --- reCAPTCHA v3 en los formularios públicos (common/recaptcha.py) ---
# Se verifica en cuanto hay llave secreta: sin ella no se cierra la puerta a
# todos. La llave del sitio vive en el frontend (VITE_RECAPTCHA_SITE_KEY).
RECAPTCHA_SECRET_KEY = env.str("RECAPTCHA_SECRET_KEY", default="").strip()
RECAPTCHA_ENABLED = env.bool("RECAPTCHA_ENABLED", default=bool(RECAPTCHA_SECRET_KEY))
RECAPTCHA_MIN_SCORE = env.float("RECAPTCHA_MIN_SCORE", default=0.5)
RECAPTCHA_HOSTNAMES = env.list(
    "RECAPTCHA_HOSTNAMES", default=["itzaka.grupotorresmucino.com", "localhost"]
)

# Tope de lo que puede viajar adjunto en un correo. Un PDF de cotización pesa
# kilobytes; uno con fotos de avance, no tanto como para pagarlo en base64.
DOCUMENT_EMAIL_MAX_BYTES = env.int("DOCUMENT_EMAIL_MAX_BYTES", default=8 * 1024 * 1024)

# --- Resend (correo saliente por su API HTTP, no por el mailer de Django) ---
# Se recortan: un salto de línea o un espacio pegado al pegar el valor
# invalida la llave —Resend contesta 401— sin que se vea en ningún lado.
RESEND_API_KEY = env.str("RESEND_API_KEY", default="").strip()
RESEND_FROM = env.str("RESEND_FROM", default="Itzaka <onboarding@resend.dev>").strip()
# Producción no sale sin correo (iteracion-16): sin la llave, o con el remitente
# de prueba de Resend, `migrate` —parte del build— se detiene (common/checks.py)
# y un correo que no puede salir queda como error, no como aviso.
REQUIRE_EMAIL_DELIVERY = env.bool(
    "REQUIRE_EMAIL_DELIVERY",
    default=env.str("VERCEL_ENV", default="") == "production",
)
# A dónde llevan los enlaces de los correos: la aplicación, no la API.
APP_BASE_URL = env.str("APP_BASE_URL", default="https://itzaka.grupotorresmucino.com")

# Tope del documento de un plano. Una textura suelta y el plano de fondo
# escaneado viajan dentro del JSON, que es lo que puede engordarlo.
PLAN_MAX_BYTES = env.int("PLAN_MAX_BYTES", default=4 * 1024 * 1024)

# Tope por archivo del editor (una textura, una malla). Lo que no cabe en el
# documento del plano vive en el bucket, pero tampoco sin límite.
PLAN_ASSET_MAX_BYTES = env.int("PLAN_ASSET_MAX_BYTES", default=10 * 1024 * 1024)

# --- Foto de un plano en papel → plano editable (US-129) ---
# La lee Claude con visión. Sin llave la conversión responde «no disponible»
# en vez de romperse; también se recorta, como la de Resend.
ANTHROPIC_API_KEY = env.str("ANTHROPIC_API_KEY", default="").strip()
PHOTO_PLAN_MODEL = env.str("PHOTO_PLAN_MODEL", default="claude-opus-5-5")
# Cada foto cuesta dinero: cinco por cuenta al día (decidido en GATE PROPUESTA).
PHOTO_PLAN_DAILY_LIMIT = env.int("PHOTO_PLAN_DAILY_LIMIT", default=5)
# El navegador la comprime antes de enviarla; Vercel no acepta cuerpos de más
# de ~4.5 MB en una función, así que lo que pase de 4 MB ni se intenta.
PHOTO_PLAN_MAX_BYTES = env.int("PHOTO_PLAN_MAX_BYTES", default=4 * 1024 * 1024)
OTP_TTL_MINUTES = env("OTP_TTL_MINUTES")

# --- CORS ---
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = env.list(
    "CORS_ALLOWED_ORIGINS", default=["http://localhost:5173"]
)
CORS_ALLOW_CREDENTIALS = True
# La empresa en la que se trabaja viaja en su propia cabecera (iteracion-14).
CORS_ALLOW_HEADERS = (*default_headers, "x-empresa")
# Tras un 429 la SPA muestra cuánto esperar: sin esto no puede leer la cabecera.
CORS_EXPOSE_HEADERS = ["Retry-After"]
# La SPA escribe con la cookie de la sesión y su token CSRF: el origen de la
# aplicación tiene que ser de confianza para la comprobación CSRF de Django.
CSRF_TRUSTED_ORIGINS = list(dict.fromkeys(CSRF_TRUSTED_ORIGINS + CORS_ALLOWED_ORIGINS))

# Tope explícito del cuerpo de una petición que no es archivo. Vercel corta en
# ~4.5 MB; el documento de un plano (PLAN_MAX_BYTES) es lo más grande que viaja.
DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024

# --- Teléfonos (django-phonenumber-field, iteracion-13) ---
# Se escriben como sea y se guardan en E.164; sin lada del país, son de México.
PHONENUMBER_DEFAULT_REGION = "MX"
PHONENUMBER_DB_FORMAT = "E164"

# STATIC/MEDIA + security + logging + storages (media on R2 in production)
from .env import *  # noqa: E402,F403
from .settings_csp import *  # noqa: E402,F403
from .settings_storages import *  # noqa: E402,F403
from .settings_unfold import *  # noqa: E402,F403
