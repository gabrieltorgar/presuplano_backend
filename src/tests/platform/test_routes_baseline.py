"""Línea base de rutas: quién entra sin sesión y con qué límite (TDD-B01).

No sale de una historia (iteracion-25 #10): toda ruta de la API pide sesión
salvo las de la lista blanca de abajo, cada una con su motivo. Una vista nueva
que se abra por error (``AllowAny`` o sin permisos) deja esto en rojo hasta
que alguien la anote aquí —un cambio de gate, aprobado en el chat— o la
cierre. Criterios BOT-01…04, SEC-01, SEC-02 y SEC-02.2 de la línea base de
seguridad (iteracion-26 #29: alcances por cuenta, correo verificado, empresa de
la petición y registro de rutas de detalle).
"""

import re

import pytest
from django.conf import settings as dj_settings
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.test import APIClient

from common.cron import IsCronJob
from common.permissions import IsVerifiedUser
from common.views import TenantContextMixin
from tests.platform.routes import ROUTE_KWARG, api_routes, is_format_twin, sample_url
from tests.security.scope_registry import (
    SCOPED_DETAIL_ROUTES,
    UNSCOPED_DETAIL_ROUTES,
)

#: Las únicas rutas que responden sin sesión, por su nombre en el URLconf.
PUBLIC_ROUTES: dict[str, str] = {
    "health": "liveness y versión de la API; no lee datos",
    "csrf": "deja la cookie CSRF que la SPA manda en cada escritura; no lee datos",
    "register": "registro con correo y contraseña (reCAPTCHA y campo trampa)",
    "verify-otp": "confirma la cuenta con el código que llegó por correo",
    "resend-otp": "vuelve a mandar el código de confirmación",
    "login": "abre la sesión web (cookies HttpOnly)",
    "password-reset": "pide el código para recuperar la contraseña",
    "password-reset-confirm": "cambia la contraseña con ese código",
    "refresh": "rota el refresh de la cookie; sin cookie válida, 401",
    "logout": "anula el refresh de la cookie que recibe y borra las cookies",
    "contact": "formulario de contacto del sitio (reCAPTCHA y campo trampa)",
    "documents": "términos y privacidad vigentes, para aceptarlos al registrarse",
    "document": "un documento legal vigente, para leerlo antes de entrar",
    "invitation-detail": "la invitación de su enlace: a quién invita y de dónde",
    "invitation-accept": "acepta la invitación: crea la cuenta o pide la contraseña",
}

#: Públicas sin un límite propio: quedan con el de ``anon``.
PUBLIC_WITHOUT_SCOPE: dict[str, str] = {
    "health": "una sonda; no lee datos",
    "csrf": "no lee datos ni cambia nada",
    "refresh": "solo sirve con un refresh vigente en la cookie",
    "logout": "solo anula el refresh que recibe",
    "documents": "texto público de solo lectura",
    "document": "texto público de solo lectura",
}

#: Las únicas rutas con sesión que no piden el correo verificado (iteracion-26
#: #8), por su nombre en el URLconf: ``IsAuthenticated`` a secas, con su motivo.
VERIFICATION_EXEMPT: dict[str, str] = {
    "me": (
        "GET devuelve is_email_verified para que la SPA lleve a /verify; "
        "PATCH pide IsVerifiedUser (get_permissions)"
    ),
}

#: Cada ruta de auth con su alcance por dirección (security.md §6, iteracion-26
#: #16), por su nombre en el URLconf. Recuperar la contraseña con el código
#: (``password-reset-confirm``) es verificar un código: lleva los de verificar.
AUTH_SCOPES: dict[str, str] = {
    "login": "login",
    "register": "register",
    "verify-otp": "otp_verify",
    "resend-otp": "otp_request",
    "password-reset": "password_reset",
    "password-reset-confirm": "otp_verify",
    "me-email": "otp_request",
    "me-email-verify": "otp_verify",
    "me-email-resend": "otp_request",
    "me-password": "password_change",
    "me-delete": "password_change",
    "invitation-accept": "login",
}

#: Y su alcance por cuenta (``identifier_throttle_scope``, sobre el correo).
IDENTIFIER_SCOPES: dict[str, str] = {
    "login": "login_email",
    "verify-otp": "otp_email",
    "password-reset": "password_reset_email",
    "password-reset-confirm": "otp_email",
    "me-email-verify": "otp_email",
}

#: Lo que delata una acción costosa en su nombre o su ruta (security.md §6).
COSTLY = re.compile(r"send|email|export|pdf|report|notify|stamp", re.IGNORECASE)

ROUTES = [route for route in api_routes() if not is_format_twin(route)]


def _is_public(route) -> bool:
    return not route.permissions or AllowAny in route.permissions


def test_every_throttle_scope_has_a_rate():
    """Un alcance sin tasa hace que su throttle responda 500 (BOT-03.1): el de
    ``throttle_scope`` y el de ``identifier_throttle_scope``."""
    rates = dj_settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]
    missing = [
        f"{route.name}: {scope}"
        for route in ROUTES
        for scope in (route.scope, route.identifier_scope)
        if scope and scope not in rates
    ]
    assert not missing, "agrega su tasa a DEFAULT_THROTTLE_RATES:\n" + "\n".join(
        missing
    )


def test_only_the_known_routes_answer_without_a_session():
    """BOT-01: una ruta nueva abierta por error no pasa el gate."""
    public = {route.name for route in ROUTES if _is_public(route)}

    opened = sorted(public - set(PUBLIC_ROUTES))
    assert not opened, (
        "estas rutas responden sin sesión: ciérralas (IsAuthenticated) o anótalas "
        "en PUBLIC_ROUTES con su motivo:\n" + "\n".join(opened)
    )
    stale = sorted(set(PUBLIC_ROUTES) - public)
    assert not stale, "ya no son públicas; quítalas de PUBLIC_ROUTES:\n" + (
        "\n".join(stale)
    )


def test_auth_routes_use_their_scope():
    """BOT-03.1: cada ruta de auth con su alcance, ninguna con el genérico."""
    routes = {route.name: route for route in ROUTES}
    assert "login" in routes, "¿cambió el URLconf de auth?"
    wrong = [
        f"{name}: {routes[name].scope} (se espera {scope})"
        for name, scope in AUTH_SCOPES.items()
        if name in routes and routes[name].scope != scope
    ]
    wrong += [
        f"{name}: por cuenta {routes[name].identifier_scope} (se espera {scope})"
        for name, scope in IDENTIFIER_SCOPES.items()
        if name in routes and routes[name].identifier_scope != scope
    ]
    wrong += [
        f"{route.name}: alcance genérico {route.scope}"
        for route in ROUTES
        if route.scope in ("dj_rest_auth", "otp")
    ]
    assert not wrong, "usa los alcances de security.md §6:\n" + "\n".join(wrong)


def test_costly_routes_use_the_costly_scope():
    """BOT-03.2: lo que manda correo o genera documentos lleva ``costly``."""
    assert "costly" in dj_settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]
    offenders = [
        f"{route.name} ({route.route}): {route.scope}"
        for route in ROUTES
        if COSTLY.search(f"{route.name} {route.route}")
        and route.name not in AUTH_SCOPES
        and route.scope != "costly"
    ]
    assert not offenders, "declara throttle_scope = 'costly':\n" + "\n".join(offenders)


def test_public_endpoints_declare_a_scope():
    """BOT-03: cada puerta pública tiene su propio límite, o dice por qué no."""
    offenders = sorted(
        route.name
        for route in ROUTES
        if _is_public(route)
        and not route.scope
        and route.name not in PUBLIC_WITHOUT_SCOPE
    )
    assert not offenders, (
        "declara su throttle_scope (o el motivo en PUBLIC_WITHOUT_SCOPE):\n"
        + "\n".join(offenders)
    )


def test_private_routes_require_an_authenticated_user():
    """SEC-02: fuera de la lista blanca, toda vista exige la sesión."""
    offenders = sorted(
        f"{route.name} ({route.route})"
        for route in ROUTES
        if not _is_public(route)
        and not any(issubclass(p, IsAuthenticated) for p in route.permissions)
    )
    assert not offenders, "agrega IsAuthenticated a sus permisos:\n" + "\n".join(
        offenders
    )


def test_views_require_a_verified_user():
    """SEC-02 (iteracion-26 #8): con sesión, el correo verificado. Una lista de
    permisos en la vista reemplaza la de omisión: ``IsAuthenticated`` a secas
    solo en VERIFICATION_EXEMPT, y lo demás pide ``IsVerifiedUser``. La ruta
    del cron pide ``IsCronJob`` (su secreto, no una cuenta), que no cuenta como
    ``IsAuthenticated`` a secas."""
    bare, unverified = set(), set()
    for route in ROUTES:
        if _is_public(route):
            continue
        if IsAuthenticated in route.permissions:
            bare.add(route.name)
        elif not any(
            issubclass(p, (IsVerifiedUser, IsCronJob)) for p in route.permissions
        ):
            unverified.add(f"{route.name} ({route.route})")
    offenders = [
        f"{name}: IsAuthenticated a secas"
        for name in sorted(bare - set(VERIFICATION_EXEMPT))
    ]
    offenders += [f"{route}: sin IsVerifiedUser" for route in sorted(unverified)]
    assert not offenders, (
        "usa common.permissions.IsVerifiedUser (o anota la ruta en "
        "VERIFICATION_EXEMPT con su motivo):\n" + "\n".join(offenders)
    )
    stale = sorted(set(VERIFICATION_EXEMPT) - bare)
    assert not stale, (
        "ya piden el correo verificado; quítalas de VERIFICATION_EXEMPT:\n"
        + "\n".join(stale)
    )


@pytest.mark.django_db
def test_private_routes_answer_401_without_a_session():
    """SEC-02: sin sesión, cada método de cada ruta privada responde 401.

    401 y no 403: la SPA renueva la sesión con un 401 y muestra «sin permiso» con
    un 403. La autenticación por cookie declara ``authenticate_header``.
    """
    client = APIClient()
    offenders, checked = [], 0
    for route in ROUTES:
        if _is_public(route):
            continue
        url = sample_url(route)
        for method in route.methods:
            checked += 1
            response = client.generic(method.upper(), url)
            if response.status_code != status.HTTP_401_UNAUTHORIZED:
                offenders.append(
                    f"{method.upper()} {url} ({route.name}): {response.status_code}"
                )
    assert checked > 50, f"solo {checked} peticiones: ¿cambió el URLconf?"
    assert not offenders, "responden sin sesión o con otro estado:\n" + "\n".join(
        offenders
    )


def test_every_api_view_sets_the_tenant_context():
    """SEC-01 (iteracion-26 #22): con la RLS, una vista que no fija la empresa
    ve cero filas y responde 404. Toda vista de ``apps/`` hereda
    ``TenantContextMixin`` (las bases de ``common/views.py``)."""
    offenders = sorted(
        {
            f"{route.cls.__module__}.{route.cls.__name__}"
            for route in ROUTES
            if route.cls.__module__.startswith("apps.")
            and not issubclass(route.cls, TenantContextMixin)
        }
    )
    assert not offenders, (
        "hereda de common.views (TenantAPIView, TenantModelViewSet…):\n"
        + "\n".join(offenders)
    )


def test_every_detail_route_is_in_the_scope_registry():
    """SEC-02.2: cada ruta de detalle (y cada acción de detalle) está en
    ``tests/security/scope_registry.py``, que la prueba con un registro de otra
    empresa; o en ``UNSCOPED_DETAIL_ROUTES`` con su motivo."""
    scoped = set(SCOPED_DETAIL_ROUTES)
    missing = sorted(
        f"{method} /{ROUTE_KWARG.sub('{pk}', route.route)} ({route.name})"
        for route in ROUTES
        if ROUTE_KWARG.search(route.route) and route.name not in UNSCOPED_DETAIL_ROUTES
        for method in route.methods
        if (method, "/" + ROUTE_KWARG.sub("{pk}", route.route)) not in scoped
    )
    assert not missing, "agrégala a SCOPED_DETAIL_ROUTES:\n" + "\n".join(missing)
    detail = {
        (method, "/" + ROUTE_KWARG.sub("{pk}", route.route))
        for route in ROUTES
        if ROUTE_KWARG.search(route.route)
        for method in route.methods
    }
    stale = sorted(f"{m} {r}" for m, r in scoped - detail)
    assert not stale, "ya no existen; quítalas del registro:\n" + "\n".join(stale)
