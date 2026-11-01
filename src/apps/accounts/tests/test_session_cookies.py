"""La sesión vive en cookies HttpOnly (iteracion-12 #1, US-03 / US-69).

Hasta 3.4.0 el access y el refresh viajaban en el cuerpo y la SPA los guardaba en
localStorage, donde cualquier script los lee: un XSS o una extensión se llevaba
la cuenta por 30 días. Ahora los pone el servidor en cookies que JavaScript no
puede leer, el refresh rota y el viejo queda en la lista negra, y salir lo anula.
"""

import json
import os
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

import pytest
from django.conf import settings
from rest_framework import status
from rest_framework.test import APIClient

import core.settings as core_settings
from apps.accounts.tests.factories import UserFactory
from apps.legal.tests.consent import accepted
from apps.team.tests.factories import InvitationFactory
from common.auth_cookies import ACCESS_COOKIE, REFRESH_COOKIE

LOGIN = "/api/auth/login/"
REFRESH = "/api/auth/refresh/"
LOGOUT = "/api/auth/logout/"
ME = "/api/auth/me/"
PASSWORD = "/api/auth/me/password/"
ORGANIZATION = "/api/auth/organization/"


def entrar(
    client: APIClient, email: str = "ana@estudio.mx", password: str = "testpass123"
):
    return client.post(LOGIN, {"email": email, "password": password}, format="json")


@pytest.fixture
def cuenta(user_factory):
    return user_factory(
        email="ana@estudio.mx", password="testpass123", is_email_verified=True
    )


@pytest.mark.django_db
class TestLaSesionVaEnCookies:
    def test_login_sets_httponly_cookies_and_returns_no_tokens(
        self, api_client, cuenta
    ) -> None:
        """Flujo principal - La sesión no queda a la vista de otros programas."""
        response = entrar(api_client)

        assert response.status_code == status.HTTP_200_OK
        assert "access" not in response.data
        assert "refresh" not in response.data
        assert response.data["user"]["email"] == "ana@estudio.mx"
        for name in (ACCESS_COOKIE, REFRESH_COOKIE):
            cookie = response.cookies[name]
            assert cookie.value
            assert cookie["httponly"]
            assert cookie["samesite"] == "Lax"
        # El refresh sólo viaja a las rutas de la sesión.
        assert response.cookies[REFRESH_COOKIE]["path"] == "/api/auth/"
        # La SPA necesita leer el token CSRF para mandarlo en cada escritura.
        assert response.cookies["csrftoken"].value
        assert not response.cookies["csrftoken"]["httponly"]

    def test_the_access_cookie_opens_the_account(self, api_client, cuenta) -> None:
        """Flujo principal - Con la cookie, la cuenta responde sin cabecera."""
        entrar(api_client)

        response = api_client.get(ME)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["email"] == "ana@estudio.mx"

    def test_a_write_without_the_csrf_token_is_refused(self, cuenta) -> None:
        """Caso de borde - Otra página no puede escribir con la cookie de la sesión."""
        client = APIClient(enforce_csrf_checks=True)
        login = entrar(client)
        token = login.cookies["csrftoken"].value

        sin_token = client.patch(ORGANIZATION, {}, format="json")
        con_token = client.patch(
            ORGANIZATION, {}, format="json", HTTP_X_CSRFTOKEN=token
        )

        assert sin_token.status_code == status.HTTP_403_FORBIDDEN
        assert con_token.status_code == status.HTTP_200_OK

    def test_a_stale_access_cookie_does_not_block_logging_in(
        self, api_client, cuenta
    ) -> None:
        """Caso de borde - Una cookie vencida o falsa no impide volver a entrar."""
        api_client.cookies[ACCESS_COOKIE] = "basura"

        assert entrar(api_client).status_code == status.HTTP_200_OK


@pytest.mark.django_db
class TestLaSesionSeRenuevaYSeCierra:
    def test_refresh_rotates_and_the_old_refresh_dies(self, api_client, cuenta) -> None:
        """Flujo principal - La sesión se renueva; el refresh usado ya no sirve."""
        entrar(api_client)
        viejo = api_client.cookies[REFRESH_COOKIE].value

        renovada = api_client.post(REFRESH, {}, format="json")

        assert renovada.status_code == status.HTTP_200_OK
        assert "access" not in renovada.data
        nuevo = renovada.cookies[REFRESH_COOKIE].value
        assert nuevo and nuevo != viejo

        otro = APIClient()
        otro.cookies[REFRESH_COOKIE] = viejo
        assert (
            otro.post(REFRESH, {}, format="json").status_code
            == status.HTTP_401_UNAUTHORIZED
        )

    def test_logout_clears_the_cookies_and_revokes_the_refresh(
        self, api_client, cuenta
    ) -> None:
        """Flujo principal - Salir invalida la sesión, aun si alguien la copió."""
        entrar(api_client)
        copiado = api_client.cookies[REFRESH_COOKIE].value

        salida = api_client.post(LOGOUT, {}, format="json")

        assert salida.status_code == status.HTTP_204_NO_CONTENT
        assert salida.cookies[ACCESS_COOKIE].value == ""
        assert salida.cookies[REFRESH_COOKIE].value == ""
        otro = APIClient()
        otro.cookies[REFRESH_COOKIE] = copiado
        assert (
            otro.post(REFRESH, {}, format="json").status_code
            == status.HTTP_401_UNAUTHORIZED
        )

    def test_logout_without_a_session_is_harmless(self, api_client) -> None:
        """Caso de borde - Salir sin sesión no falla."""
        assert (
            api_client.post(LOGOUT, {}, format="json").status_code
            == status.HTTP_204_NO_CONTENT
        )

    def test_refresh_without_a_session_is_401(self, api_client) -> None:
        """Caso de borde - Sin sesión no hay nada que renovar."""
        assert (
            api_client.post(REFRESH, {}, format="json").status_code
            == status.HTTP_401_UNAUTHORIZED
        )

    def test_changing_the_password_closes_the_other_sessions(self, cuenta) -> None:
        """Caso de borde - Cambiar la contraseña deja fuera las otras sesiones."""
        aqui, alla = APIClient(), APIClient()
        entrar(aqui)
        entrar(alla)

        cambio = aqui.post(
            PASSWORD,
            {"current_password": "testpass123", "new_password": "OtraClave#2026"},
            format="json",
        )

        assert cambio.status_code == status.HTTP_200_OK
        assert (
            alla.post(REFRESH, {}, format="json").status_code
            == status.HTTP_401_UNAUTHORIZED
        )
        # Quien la cambió sigue dentro, con una sesión nueva.
        assert aqui.post(REFRESH, {}, format="json").status_code == status.HTTP_200_OK


def test_lifetimes_rotation_and_blacklist() -> None:
    """Flujo principal - Media hora de acceso, una semana de sesión, rotación."""
    jwt = settings.SIMPLE_JWT
    assert jwt["ACCESS_TOKEN_LIFETIME"] <= timedelta(minutes=30)
    assert jwt["REFRESH_TOKEN_LIFETIME"] <= timedelta(days=7)
    assert jwt["ROTATE_REFRESH_TOKENS"] is True
    assert jwt["BLACKLIST_AFTER_ROTATION"] is True
    assert jwt["CHECK_REVOKE_TOKEN"] is True
    assert "rest_framework_simplejwt.token_blacklist" in settings.INSTALLED_APPS
    assert settings.CSRF_COOKIE_HTTPONLY is False


def claves(obj):
    """Todas las claves de un JSON, también las anidadas."""
    if isinstance(obj, dict):
        for clave, valor in obj.items():
            yield clave
            yield from claves(valor)
    elif isinstance(obj, list):
        for elemento in obj:
            yield from claves(elemento)


def solo_en_cookies(response) -> None:
    """La sesión llega en cookies HttpOnly y el cuerpo no trae ningún token."""
    assert response.status_code in (status.HTTP_200_OK, status.HTTP_201_CREATED)
    assert {"access", "refresh"}.isdisjoint(claves(response.json()))
    cuerpo = response.content.decode()
    for nombre in (ACCESS_COOKIE, REFRESH_COOKIE):
        valor = response.cookies[nombre].value
        assert valor
        assert valor not in cuerpo


@pytest.mark.django_db
def test_web_auth_responses_carry_no_tokens(api_client, cuenta) -> None:
    """CRD-02.1 · API-03 · iteracion-24 #2 — Ninguna respuesta que abre sesión
    deja un token donde un script lo lea: entrar, renovar, cambiar la contraseña
    y aceptar una invitación."""
    solo_en_cookies(entrar(api_client))
    solo_en_cookies(api_client.post(REFRESH, {}, format="json"))
    solo_en_cookies(
        api_client.post(
            PASSWORD,
            {"current_password": "testpass123", "new_password": "OtraClave#2026"},
            format="json",
        )
    )

    admin = UserFactory(email="admin@estudioreyes.mx")
    InvitationFactory(account=admin, email="bea@estudio.mx", token="enlace-bea")
    solo_en_cookies(
        APIClient().post(
            "/api/invitations/enlace-bea/accept/",
            {"password": "Teja-Roja-81", **accepted()},
            format="json",
        )
    )


#: Lo que decide a qué dominios responde la API y a dónde viajan sus cookies.
DOMAIN_SETTINGS = (
    "DEBUG",
    "ALLOWED_HOSTS",
    "CORS_ALLOWED_ORIGINS",
    "CORS_ALLOW_CREDENTIALS",
    "CSRF_TRUSTED_ORIGINS",
    "CSRF_COOKIE_DOMAIN",
    "CSRF_COOKIE_NAME",
    "CSRF_COOKIE_HTTPONLY",
    "CSRF_COOKIE_SECURE",
    "SESSION_COOKIE_SECURE",
    "APP_BASE_URL",
)


def ajustes_en(entorno_extra: dict[str, str]) -> dict:
    """``core.settings`` en un intérprete limpio, sin las variables de dominio
    de quien corre la suite (ni ``DEBUG`` ni las de Vercel) más las dadas."""
    entorno = {
        k: v
        for k, v in os.environ.items()
        if k not in DOMAIN_SETTINGS and not k.startswith("VERCEL")
    }
    entorno.update(
        {
            "DJANGO_SETTINGS_MODULE": "core.settings",
            "SECRET_KEY": "x" * 50,
            **entorno_extra,
        }
    )
    salida = subprocess.run(  # noqa: S603 -- el mismo intérprete, sin shell
        [
            sys.executable,
            "-c",
            "import json; from django.conf import settings as s; "
            f"print(json.dumps({{n: getattr(s, n) for n in {DOMAIN_SETTINGS!r}}}))",
        ],
        cwd=Path(core_settings.__file__).resolve().parents[1],
        env=entorno,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(salida.stdout)


@pytest.mark.django_db
def test_session_cookie_settings(settings, cuenta) -> None:
    """SEC-04 · SEC-04.1 · SEC-04.4 · iteracion-26 #9 — La SPA en itzaka.com y la
    API en api.itzaka.com: el mismo sitio, con las cookies seguras.

    En Vercel y sin DEBUG, los valores por omisión son los de producción. Las
    cookies JWT quedan sólo en la API (sin Domain); la CSRF, en el dominio padre
    para que la SPA la lea y la repita en X-CSRFToken.
    """
    prod = ajustes_en({"VERCEL": "1"})

    assert prod["DEBUG"] is False
    assert prod["SESSION_COOKIE_SECURE"] is True
    assert prod["CSRF_COOKIE_SECURE"] is True
    assert prod["CSRF_COOKIE_HTTPONLY"] is False
    assert prod["CSRF_COOKIE_DOMAIN"] == ".itzaka.com"
    assert prod["CSRF_COOKIE_NAME"] == "csrftoken"
    assert prod["ALLOWED_HOSTS"] == ["api.itzaka.com"]
    assert prod["CORS_ALLOWED_ORIGINS"] == ["https://itzaka.com"]
    assert prod["CSRF_TRUSTED_ORIGINS"] == ["https://itzaka.com"]
    assert prod["CORS_ALLOW_CREDENTIALS"] is True
    assert prod["APP_BASE_URL"] == "https://itzaka.com"

    settings.SESSION_COOKIE_SECURE = True
    settings.CSRF_COOKIE_SECURE = True
    settings.CSRF_COOKIE_DOMAIN = prod["CSRF_COOKIE_DOMAIN"]
    response = entrar(APIClient())

    assert response.status_code == status.HTTP_200_OK
    for name in (ACCESS_COOKIE, REFRESH_COOKIE):
        cookie = response.cookies[name]
        assert cookie["secure"] is True, name
        assert cookie["httponly"] is True, name
        assert cookie["samesite"] == "Lax", name
        assert cookie["domain"] == "", f"{name}: las cookies JWT no llevan Domain"
    csrf = response.cookies[settings.CSRF_COOKIE_NAME]
    assert csrf.value
    assert not csrf["httponly"]
    assert csrf["secure"] is True
    assert csrf["samesite"] == "Lax"
    assert csrf["domain"] == ".itzaka.com"


class TestDominiosPorEntorno:
    def test_with_debug_the_defaults_are_local(self) -> None:
        """SEC-04 · iteracion-26 #9 — En local, la SPA de Vite y cookies sin Domain."""
        local = ajustes_en({"DEBUG": "True"})

        assert local["ALLOWED_HOSTS"] == ["localhost", "127.0.0.1", "[::1]"]
        assert local["CORS_ALLOWED_ORIGINS"] == ["http://localhost:5173"]
        assert local["CSRF_TRUSTED_ORIGINS"] == ["http://localhost:5173"]
        assert local["CSRF_COOKIE_DOMAIN"] is None
        assert local["CSRF_COOKIE_NAME"] == "csrftoken"
        assert local["APP_BASE_URL"] == "http://localhost:5173"

    def test_develop_sets_its_own_domains(self) -> None:
        """SEC-04 · iteracion-26 #9 — develop: dev.itzaka.com y api-dev.itzaka.com,
        con su propia cookie CSRF en el mismo dominio padre."""
        develop = ajustes_en(
            {
                "VERCEL": "1",
                "ALLOWED_HOSTS": "api-dev.itzaka.com",
                "CORS_ALLOWED_ORIGINS": "https://dev.itzaka.com",
                "CSRF_COOKIE_NAME": "csrftoken_dev",
                "APP_BASE_URL": "https://dev.itzaka.com",
            }
        )

        assert develop["ALLOWED_HOSTS"] == ["api-dev.itzaka.com"]
        assert develop["CORS_ALLOWED_ORIGINS"] == ["https://dev.itzaka.com"]
        assert develop["CSRF_TRUSTED_ORIGINS"] == ["https://dev.itzaka.com"]
        assert develop["CSRF_COOKIE_DOMAIN"] == ".itzaka.com"
        assert develop["CSRF_COOKIE_NAME"] == "csrftoken_dev"
        assert develop["APP_BASE_URL"] == "https://dev.itzaka.com"

    def test_the_deployment_hosts_are_still_trusted(self) -> None:
        """SEC-04 · iteracion-26 #9 — Los hosts que Vercel da al despliegue se
        suman a los del dominio, nunca en su lugar."""
        prod = ajustes_en({"VERCEL": "1", "VERCEL_URL": "itzaka-api-abc.vercel.app"})

        assert prod["ALLOWED_HOSTS"] == ["api.itzaka.com", "itzaka-api-abc.vercel.app"]
        assert prod["CORS_ALLOWED_ORIGINS"] == ["https://itzaka.com"]

    def test_production_trusts_only_exact_origins_for_csrf(self) -> None:
        """SEC-04 · iteracion-27 #7 — En producción, CSRF confía solo en los
        orígenes exactos configurados: los hosts *.vercel.app del despliegue
        siguen en ALLOWED_HOSTS, pero no como orígenes de confianza."""
        prod = ajustes_en(
            {
                "VERCEL": "1",
                "VERCEL_ENV": "production",
                "VERCEL_URL": "itzaka-api-abc.vercel.app",
                "VERCEL_PROJECT_PRODUCTION_URL": "itzaka-api.vercel.app",
            }
        )

        assert prod["CSRF_TRUSTED_ORIGINS"] == ["https://itzaka.com"]
        assert "itzaka-api-abc.vercel.app" in prod["ALLOWED_HOSTS"]

    def test_preview_still_trusts_its_deployment_hosts(self) -> None:
        """SEC-04 · iteracion-27 #7 — En Preview (develop, que todavía vive en
        *.vercel.app) los hosts del despliegue siguen siendo de confianza."""
        preview = ajustes_en(
            {
                "VERCEL": "1",
                "VERCEL_ENV": "preview",
                "VERCEL_URL": "itzaka-api-git-develop.vercel.app",
                "CORS_ALLOWED_ORIGINS": "https://dev.cuotreka.vercel.app",
            }
        )

        assert preview["CSRF_TRUSTED_ORIGINS"] == [
            "https://itzaka-api-git-develop.vercel.app",
            "https://dev.cuotreka.vercel.app",
        ]

    def test_without_vercel_env_the_deployment_hosts_are_not_trusted(self) -> None:
        """SEC-04 · iteracion-27 #7 — Sin VERCEL_ENV no se sabe si es Preview:
        falla cerrado, como en producción."""
        prod = ajustes_en({"VERCEL": "1", "VERCEL_URL": "itzaka-api-abc.vercel.app"})

        assert prod["CSRF_TRUSTED_ORIGINS"] == ["https://itzaka.com"]
