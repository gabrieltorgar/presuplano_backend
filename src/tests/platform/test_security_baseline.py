"""Platform baseline: security settings and static scans (TDD-B01, iteracion-12 #8).

Not tied to a user story: encodes the always-on part of the security criteria
(secure DRF defaults, throttling on a shared cache, max_page_size, hashers and
validators, cookie and header settings, the production HTTPS block, reCAPTCHA
on in production, the SPA and the API on the same site, the dependency floors,
the CSP scoped to the admin) and four static scans over ``src/apps/`` and
``src/common/``. A failing scan prints ``file:line``: fix the code, never weaken
the test.
"""

import ast
import json
import os
import re
import subprocess
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from django.conf import settings as dj_settings
from django.core.cache.backends.db import DatabaseCache
from django.db import router
from django.utils.module_loading import import_string
from packaging.version import Version

import core.settings as core_settings

SRC = Path(__file__).resolve().parents[2]  # src/
SCANNED = (SRC / "apps", SRC / "common")
#: Las tasas que una vista puede pedir (security.md §6): por dirección y, las
#: tres últimas, por cuenta (iteracion-26 #16).
SCOPES = (
    "anon",
    "user",
    "login",
    "register",
    "otp_request",
    "otp_verify",
    "password_reset",
    "password_change",
    "contact",
    "costly",
    "bulk",
    "dj_rest_auth",
    "login_email",
    "otp_email",
    "password_reset_email",
)
#: Un host bajo un sufijo público siempre es otro sitio: las cookies SameSite=Lax
#: de la sesión no viajan a la API.
PUBLIC_SUFFIX_HOSTS = (".vercel.app", ".up.railway.app", ".onrender.com", ".fly.dev")
#: Las que fijan los dominios: sin ellas, core.settings lee sus valores por omisión.
DOMAIN_VARS = (
    "DEBUG",
    "ALLOWED_HOSTS",
    "CORS_ALLOWED_ORIGINS",
    "CSRF_TRUSTED_ORIGINS",
    "CSRF_COOKIE_DOMAIN",
)
#: Los pisos de libraries.md §whitelist (verificados el 2026-10-21): (mínimo, tope).
FLOORS: dict[str, tuple[str, str | None]] = {
    # La skill pide django 5.2 LTS (>= 5.2.18, < 5.3). Decisión de la persona
    # (2026-10-31): Itzaka se queda en django 6.1 (6.1.2 sin avisos publicados);
    # el piso de la skill no aplica mientras 6.1 tenga soporte.
    "django": ("6.1.2", "6.2"),
    "djangorestframework": ("3.18.2", None),
    "djangorestframework-simplejwt": ("5.5.1", None),
    "PyJWT": ("2.15", None),
    "whitenoise": ("6.9", None),
    "django-filter": ("25.1", None),
    "django-cors-headers": ("4.7", None),
    "Pillow": ("13.0", None),
    "django-csp": ("4.0", "5"),
}
#: Las mismas reglas, solo si están instaladas (hoy no lo está ninguna).
FLOORS_WHEN_INSTALLED: dict[str, tuple[str, str | None]] = {
    "requests": ("2.33", None),
    "django-allauth": ("65.14.1", None),
}


def _py_files():
    return [
        path
        for root in SCANNED
        for path in root.rglob("*.py")
        if "migrations" not in path.parts and "tests" not in path.parts
    ]


# ---------- settings [SEC-02, SEC-04, SEC-05, SRV-01, SRV-02, SRV-03, BOT-03, VAL-06]


def test_drf_defaults_are_secure():
    """SEC-02 · SEC-04.2 · BOT-03 (iteracion-26 #8, #10, #16): correo verificado
    por omisión, solo JSON y los límites por dirección y por cuenta con su tasa."""
    rf = dj_settings.REST_FRAMEWORK
    assert "common.permissions.IsVerifiedUser" in rf["DEFAULT_PERMISSION_CLASSES"]
    # Sin declararlos, DRF también acepta formularios (FormParser, MultiPartParser).
    assert tuple(rf.get("DEFAULT_PARSER_CLASSES", ())) == (
        "rest_framework.parsers.JSONParser",
    ), "un formulario HTML de otro sitio no llega a la API"
    assert rf.get("DEFAULT_THROTTLE_CLASSES"), "throttling must be on by default"
    assert "common.throttling.IdentifierRateThrottle" in rf["DEFAULT_THROTTLE_CLASSES"]
    for scope in SCOPES:
        assert scope in rf["DEFAULT_THROTTLE_RATES"], f"missing throttle rate '{scope}'"


def test_pagination_has_a_max_page_size():
    paginator = import_string(dj_settings.REST_FRAMEWORK["DEFAULT_PAGINATION_CLASS"])
    assert getattr(paginator, "max_page_size", None), "pagination needs max_page_size"


def test_cache_is_shared_outside_the_tests():
    # The suite swaps in a local-memory cache (conftest.py); what ships is read
    # from the settings module itself.
    backend = core_settings.CACHES["default"]["BACKEND"]
    assert "locmem" not in backend.lower(), "throttling needs a shared cache"


def test_db_cache_writes_outside_atomic_requests():
    """BOT-03.3 (iteracion-26 #22): with ATOMIC_REQUESTS a handled 4xx rolls
    back what the request wrote; the database cache writes through its own
    alias, outside that transaction, or a failed login never counts."""
    default = core_settings.CACHES["default"]
    if not default["BACKEND"].endswith("DatabaseCache") or not any(
        db.get("ATOMIC_REQUESTS") for db in dj_settings.DATABASES.values()
    ):
        return
    alias = router.db_for_write(
        DatabaseCache(default["LOCATION"], {}).cache_model_class
    )
    assert dj_settings.DATABASES[alias].get("ATOMIC_REQUESTS") is False, (
        "a failed request rolls back its throttle hit"
    )


def test_requests_run_in_a_transaction():
    """SEC-01 (iteracion-26 #22): the RLS context (SET LOCAL) lives as long as
    the transaction; without ATOMIC_REQUESTS it would be gone before the query."""
    assert dj_settings.DATABASES["default"].get("ATOMIC_REQUESTS") is True


def test_password_hashing_and_validators():
    assert dj_settings.PASSWORD_HASHERS[0].startswith("django.contrib.auth.hashers.")
    assert len(dj_settings.AUTH_PASSWORD_VALIDATORS) >= 4


def test_cookie_csrf_and_header_settings():
    assert dj_settings.SESSION_COOKIE_HTTPONLY is True
    assert dj_settings.SESSION_COOKIE_SAMESITE in ("Lax", "Strict")
    assert dj_settings.SECURE_CONTENT_TYPE_NOSNIFF is True
    assert dj_settings.X_FRAME_OPTIONS == "DENY"
    assert dj_settings.SECURE_REFERRER_POLICY
    assert dj_settings.USE_TZ is True
    assert dj_settings.DATA_UPLOAD_MAX_MEMORY_SIZE
    assert dj_settings.DATA_UPLOAD_MAX_MEMORY_SIZE <= 10 * 1024 * 1024
    assert getattr(dj_settings, "CORS_ALLOW_ALL_ORIGINS", False) is False


def test_production_https_settings_are_declared():
    """The production block is checked as source: the suite runs with DEBUG on.

    This project keeps CSRF_TRUSTED_ORIGINS in settings.py (it merges the
    Vercel hosts and the CORS origins); the rest lives in core/env.py.
    """
    source = (SRC / "core" / "env.py").read_text(encoding="utf-8") + (
        SRC / "core" / "settings.py"
    ).read_text(encoding="utf-8")
    for name in (
        "SECURE_PROXY_SSL_HEADER",
        "SECURE_SSL_REDIRECT",
        "SESSION_COOKIE_SECURE",
        "CSRF_COOKIE_SECURE",
        "SECURE_HSTS_SECONDS",
        "CSRF_TRUSTED_ORIGINS",
    ):
        assert name in source, f"core settings do not declare {name}"


def _production_settings() -> subprocess.CompletedProcess:
    """``core.settings`` en un intérprete limpio con ``DEBUG=False``.

    La suite corre con ``DEBUG=True`` y un ``SECRET_KEY`` de CI (quality-gate):
    el bloque de producción de ``core/env.py`` solo se ve en otro proceso.
    """
    keys = (
        "DEBUG",
        "SECURE_SSL_REDIRECT",
        "SESSION_COOKIE_SECURE",
        "CSRF_COOKIE_SECURE",
        "SECURE_HSTS_SECONDS",
        "SECURE_PROXY_SSL_HEADER",
        "PASSWORD_HASHERS",
        "CACHES",
        "REST_FRAMEWORK",
        "RECAPTCHA_ENABLED",
    )
    env = {
        # Sin las RECAPTCHA_* de quien corre la suite: se lee el valor por omisión.
        **{k: v for k, v in os.environ.items() if not k.startswith("RECAPTCHA_")},
        "DEBUG": "False",
        "SECRET_KEY": "x" * 50,
    }
    return _settings_in_a_fresh_interpreter(keys, env)


def _settings_in_a_fresh_interpreter(
    keys: tuple[str, ...], env: dict[str, str]
) -> subprocess.CompletedProcess:
    """Los valores de ``keys`` de ``core.settings``, importado con ``env``."""
    code = (
        "import django, json; django.setup(); "
        "from django.conf import settings as s; "
        f"print(json.dumps({{k: getattr(s, k, None) for k in {keys!r}}}, default=str))"
    )
    return subprocess.run(  # noqa: S603 -- el mismo intérprete, sin shell
        [sys.executable, "-c", code],
        cwd=SRC,
        env={**env, "DJANGO_SETTINGS_MODULE": "core.settings", "PYTHONPATH": str(SRC)},
        capture_output=True,
        text=True,
        check=False,
    )


def test_production_settings_values():
    """TDD-B03 · BOT-01: HTTPS, HSTS, cookies Secure, hasher, caché compartida,
    solo JSON y reCAPTCHA encendido aunque falte la llave (iteracion-26 #17).

    Mutación: ``SECURE_SSL_REDIRECT = False`` en core/env.py la pone en rojo; y
    ``RECAPTCHA_ENABLED`` que vuelva a seguir a ``RECAPTCHA_SECRET_KEY``, también.
    """
    run = _production_settings()
    assert run.returncode == 0, run.stderr
    prod = json.loads(run.stdout)

    assert prod["DEBUG"] is False
    assert prod["SECURE_SSL_REDIRECT"] is True
    # Las cookies de la sesión JWT usan SESSION_COOKIE_SECURE (auth_cookies.py).
    assert prod["SESSION_COOKIE_SECURE"] is True
    assert prod["CSRF_COOKIE_SECURE"] is True
    assert prod["SECURE_HSTS_SECONDS"] >= 86_400
    assert prod["SECURE_PROXY_SSL_HEADER"] == ["HTTP_X_FORWARDED_PROTO", "https"]
    assert prod["PASSWORD_HASHERS"][0] in {
        f"django.contrib.auth.hashers.{name}"
        for name in (
            "PBKDF2PasswordHasher",
            "Argon2PasswordHasher",
            "ScryptPasswordHasher",
        )
    }
    backend = prod["CACHES"]["default"]["BACKEND"].lower()
    assert "locmem" not in backend, "throttling needs a shared cache"
    renderers = prod["REST_FRAMEWORK"]["DEFAULT_RENDERER_CLASSES"]
    assert not any("BrowsableAPIRenderer" in r for r in renderers)
    # Formularios públicos (registro, acceso, recuperación, contacto, invitación).
    assert prod["RECAPTCHA_ENABLED"] is True


def _cross_site_origins(cookie_domain: str | None, origins: list[str]) -> list[str]:
    """Los orígenes que no son del sitio de la cookie CSRF, con el porqué."""
    domain = (cookie_domain or "").lstrip(".")
    found = []
    for origin in origins:
        host = urlsplit(origin).hostname or ""
        if "*" in origin:
            found.append(f"{origin}: solo orígenes exactos")
        elif host.endswith(PUBLIC_SUFFIX_HOSTS):
            found.append(f"{origin}: un sufijo público siempre es otro sitio")
        elif domain and host != domain and not host.endswith("." + domain):
            found.append(f"{origin}: fuera de CSRF_COOKIE_DOMAIN ({cookie_domain})")
    return found


def _vercel_settings() -> subprocess.CompletedProcess:
    """``core.settings`` como en un despliegue de Vercel sin variables propias.

    ``VERCEL=1`` y nada más: sin ``DEBUG``, sin las de los dominios y sin las
    ``VERCEL_*`` (``VERCEL_URL`` y las otras dos suman el host ``*.vercel.app``
    del despliegue a ``ALLOWED_HOSTS`` y ``CSRF_TRUSTED_ORIGINS``, fuera de esto).
    """
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in DOMAIN_VARS and not k.startswith(("VERCEL", "RECAPTCHA_"))
    }
    return _settings_in_a_fresh_interpreter(
        DOMAIN_VARS, {**env, "VERCEL": "1", "SECRET_KEY": "x" * 50}
    )


def test_spa_and_api_are_same_site():
    """SEC-04.4 (iteracion-26 #9): la SPA (itzaka.com) y la API (api.itzaka.com)
    en el mismo sitio, o las cookies SameSite=Lax no viajan y cada llamada tras
    el login responde 401. Los ajustes de la suite y los de un despliegue de
    Vercel sin variables (los de producción); el par desplegado lo revisa
    ``post_deploy_check.py --site``.
    """
    here = _cross_site_origins(
        dj_settings.CSRF_COOKIE_DOMAIN,
        [*dj_settings.CORS_ALLOWED_ORIGINS, *dj_settings.CSRF_TRUSTED_ORIGINS],
    )
    assert not here, "orígenes de otro sitio en la suite:\n" + "\n".join(here)

    run = _vercel_settings()
    assert run.returncode == 0, run.stderr
    prod = json.loads(run.stdout)
    assert prod["DEBUG"] is False
    assert prod["CSRF_COOKIE_DOMAIN"] == ".itzaka.com"
    assert prod["CORS_ALLOWED_ORIGINS"] == ["https://itzaka.com"]
    assert prod["ALLOWED_HOSTS"] == ["api.itzaka.com"]
    there = _cross_site_origins(
        prod["CSRF_COOKIE_DOMAIN"],
        [*prod["CORS_ALLOWED_ORIGINS"], *prod["CSRF_TRUSTED_ORIGINS"]],
    )
    assert not there, "orígenes de otro sitio en Vercel:\n" + "\n".join(there)

    env_py = (SRC / "core" / "env.py").read_text(encoding="utf-8")
    assert re.search(r"CSRF_COOKIE_DOMAIN\s*=\s*env\(", env_py), (
        "core/env.py lee CSRF_COOKIE_DOMAIN del entorno (develop pone el suyo)"
    )


def test_installed_versions_meet_floors():
    """SRV-03.6: lo que corre (importlib.metadata), no solo lo que pide pyproject."""
    low = []
    for dist, (floor, ceiling) in {**FLOORS, **FLOORS_WHEN_INSTALLED}.items():
        try:
            installed = Version(version(dist))
        except PackageNotFoundError:
            if dist in FLOORS:
                low.append(f"{dist} no está instalado")
            continue
        if installed < Version(floor) or (ceiling and installed >= Version(ceiling)):
            bounds = f">= {floor}" + (f", < {ceiling}" if ceiling else "")
            low.append(f"{dist} {installed} (se pide {bounds})")
    assert not low, "súbelo con su propio item TEC (uv lock --upgrade-package …):\n" + (
        "\n".join(low)
    )


# ---------- CSP and headers [SRV-01]


def test_security_middlewares_installed():
    """SRV-01 · django-csp 4 tras WhiteNoise y, enseguida, la política del admin."""
    mw = list(dj_settings.MIDDLEWARE)
    for name in (
        "django.middleware.security.SecurityMiddleware",
        "csp.middleware.CSPMiddleware",
        "core.middleware.AdminCSPMiddleware",
        "django.middleware.clickjacking.XFrameOptionsMiddleware",
    ):
        assert name in mw, f"missing {name}"
    assert "csp" in dj_settings.INSTALLED_APPS
    assert mw.index("csp.middleware.CSPMiddleware") > mw.index(
        "whitenoise.middleware.WhiteNoiseMiddleware"
    )
    # Su fase de respuesta corre antes que la de CSPMiddleware: deja _csp_replace.
    assert (
        mw.index("core.middleware.AdminCSPMiddleware")
        == mw.index("csp.middleware.CSPMiddleware") + 1
    )
    directives = dj_settings.CONTENT_SECURITY_POLICY["DIRECTIVES"]  # aplicada
    assert not any(
        "unsafe-eval" in str(v) or "unsafe-inline" in str(v)
        for v in directives.values()
    )


@pytest.mark.django_db
def test_csp_is_scoped_to_admin(client):
    """SRV-01 · pytest-django corre con DEBUG=False: el 404 también la lleva."""
    api = client.get("/api/__csp_probe__/")["Content-Security-Policy"]
    assert "default-src 'none'" in api and "frame-ancestors 'none'" in api
    assert "unsafe-eval" not in api and "unsafe-inline" not in api
    adm = client.get("/admin/login/")["Content-Security-Policy"]
    script_src = next(d for d in adm.split(";") if d.strip().startswith("script-src"))
    assert "'unsafe-eval'" in script_src and "'unsafe-inline'" not in script_src
    assert "style-src 'self' 'unsafe-inline'" in adm and "frame-ancestors 'none'" in adm


# ---------- static scans [SEC-03, API-01, CRD-01]


def _assign_value(node, target):
    for n in ast.walk(node):
        if isinstance(n, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == target for t in n.targets
        ):
            yield n


def test_serializers_list_fields_explicitly():
    offenders = []
    for path in _py_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        metas = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
        for cls in [n for n in metas if n.name == "Meta"]:
            for a in _assign_value(cls, "fields"):
                if isinstance(a.value, ast.Constant) and a.value.value == "__all__":
                    offenders.append(f"{path.relative_to(SRC)}:{a.lineno} '__all__'")
            for a in _assign_value(cls, "exclude"):
                offenders.append(f"{path.relative_to(SRC)}:{a.lineno} exclude")
    assert not offenders, "explicit serializer fields required:\n" + "\n".join(
        offenders
    )


def _is_dynamic_string(node):
    return (
        isinstance(node, ast.JoinedStr)
        or (isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Mod, ast.Add)))
        or (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "format"
        )
    )


def test_raw_sql_is_parameterized():
    offenders = []
    for path in _py_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        calls = [
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        ]
        for call in calls:
            where = f"{path.relative_to(SRC)}:{call.lineno}"
            if call.func.attr == "extra":
                offenders.append(f"{where} .extra() is prohibited")
            if (
                call.func.attr in ("execute", "raw", "executemany")
                and call.args
                and _is_dynamic_string(call.args[0])
            ):
                offenders.append(f"{where} SQL built from a string expression")
    assert not offenders, "use separated parameters:\n" + "\n".join(offenders)


def test_no_partial_in_on_commit():
    """CRD-01 · Django registra el callback que falla: un partial, con sus datos."""
    offenders = []
    for path in _py_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for call in ast.walk(tree):
            if not (
                isinstance(call, ast.Call)
                and isinstance(call.func, ast.Attribute)
                and call.func.attr == "on_commit"
                and call.args
                and isinstance(call.args[0], ast.Call)
            ):
                continue
            callee = call.args[0].func
            name = getattr(callee, "id", None) or getattr(callee, "attr", "")
            if name == "partial":
                offenders.append(f"{path.relative_to(SRC)}:{call.lineno}")
    assert not offenders, "pass a lambda or a function:\n" + "\n".join(offenders)


def test_no_password_or_token_in_logs():
    offenders = []
    for path in _py_files():
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            low = line.lower()
            if "logger." in low and any(
                w in low for w in ("password", "token", "secret", "otp_code")
            ):
                offenders.append(f"{path.relative_to(SRC)}:{i}")
    assert not offenders, "never log credentials:\n" + "\n".join(offenders)
