"""El registro abre una sesión sin verificar (iteracion-26 #12).

Hasta 4.0.0 registrarse no abría sesión: la pantalla del código guardaba el
correo y, al verificar, la persona tenía que volver a escribir su contraseña en
el acceso. Ahora el registro deja la sesión en las cookies HttpOnly (el cuerpo
sigue siendo sólo la cuenta) y, como la cuenta no está verificada, esa sesión
sólo alcanza ``GET me/`` y las rutas públicas (#8). Verificar el código es
entrar: deja una sesión nueva de esa cuenta, también en un navegador que llegó
por el acceso de una cuenta sin verificar.

Contrato para la SPA: tras ``POST /api/auth/register/`` (201) y tras
``POST /api/auth/verify-otp/`` (200) el navegador ya tiene sesión; un 403 con
``code: "email_not_verified"`` significa «lleva a /verify».
"""

import pytest
from django.conf import settings
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.accounts.views import RegisterView
from apps.legal.tests.consent import accepted
from common.auth_cookies import ACCESS_COOKIE, REFRESH_COOKIE
from common.permissions import EMAIL_NOT_VERIFIED

REGISTER = "/api/auth/register/"
VERIFY = "/api/auth/verify-otp/"
LOGIN = "/api/auth/login/"
ME = "/api/auth/me/"
CLIENTS = "/api/clients/"
EMAIL = "ana@estudio.mx"
PASSWORD = "Teja-Roja-81"


def claves(obj):
    if isinstance(obj, dict):
        for clave, valor in obj.items():
            yield clave
            yield from claves(valor)
    elif isinstance(obj, list):
        for elemento in obj:
            yield from claves(elemento)


def registrarse(client: APIClient):
    return client.post(
        REGISTER, {"email": EMAIL, "password": PASSWORD, **accepted()}, format="json"
    )


def verificar(client: APIClient, code: str | None = None):
    return client.post(
        VERIFY,
        {"email": EMAIL, "code": code or settings.OTP_UNIVERSAL_CODE},
        format="json",
    )


@pytest.mark.django_db
class TestElRegistroAbreLaSesion:
    def test_register_sets_httponly_cookies_and_returns_only_the_account(
        self,
    ) -> None:
        """CRD-01.1 · iteracion-26 #12 — La sesión llega en cookies HttpOnly; el
        cuerpo es la cuenta, sin tokens ni contraseña."""
        response = registrarse(APIClient())

        assert response.status_code == status.HTTP_201_CREATED
        assert set(response.json()) == {"id", "email", "is_email_verified"}
        assert response.json()["is_email_verified"] is False
        assert {"access", "refresh", "password"}.isdisjoint(claves(response.json()))
        for name in (ACCESS_COOKIE, REFRESH_COOKIE):
            cookie = response.cookies[name]
            assert cookie.value, name
            assert cookie["httponly"], name
            assert cookie.value not in response.content.decode(), name
        assert response.cookies[settings.CSRF_COOKIE_NAME].value
        # Sin is_active=False: la cuenta sin verificar sigue activa.
        assert User.objects.get(email=EMAIL).is_active is True

    def test_the_unverified_session_reaches_me_and_nothing_else(self) -> None:
        """CRD-01.1 · SEC-02 · iteracion-26 #12 — Con la sesión del registro, una
        ruta de datos es 403 email_not_verified y ``me`` responde."""
        client = APIClient()
        registrarse(client)

        bloqueada = client.get(CLIENTS)
        yo = client.get(ME)

        assert bloqueada.status_code == status.HTTP_403_FORBIDDEN
        assert bloqueada.json()["code"] == EMAIL_NOT_VERIFIED
        assert yo.status_code == status.HTTP_200_OK
        assert yo.data["email"] == EMAIL
        assert yo.data["is_email_verified"] is False

    def test_verifying_leaves_a_valid_session(self) -> None:
        """CRD-01.1 · iteracion-26 #12 — Verificar es entrar: la sesión nueva
        alcanza los datos, sin volver a escribir la contraseña."""
        client = APIClient()
        registrarse(client)
        antes = client.cookies[ACCESS_COOKIE].value

        verificada = verificar(client)

        assert verificada.status_code == status.HTTP_200_OK
        assert verificada.data["is_email_verified"] is True
        assert {"access", "refresh"}.isdisjoint(claves(verificada.json()))
        assert verificada.cookies[ACCESS_COOKIE]["httponly"]
        assert verificada.cookies[ACCESS_COOKIE].value != antes
        assert client.get(CLIENTS).status_code == status.HTTP_200_OK
        assert client.post("/api/auth/refresh/").status_code == status.HTTP_200_OK

    def test_verifying_from_the_login_opens_the_session_too(self) -> None:
        """CRD-01.1 · iteracion-26 #12 — Quien entra sin verificar recibe el
        código (403 de siempre); al escribirlo, entra en ese navegador."""
        registrarse(APIClient())
        navegador = APIClient()

        acceso = navegador.post(
            LOGIN, {"email": EMAIL, "password": PASSWORD}, format="json"
        )
        assert acceso.status_code == status.HTTP_403_FORBIDDEN
        assert ACCESS_COOKIE not in acceso.cookies

        assert verificar(navegador).status_code == status.HTTP_200_OK
        assert navegador.get(CLIENTS).status_code == status.HTTP_200_OK

    def test_a_wrong_code_opens_no_session(self) -> None:
        """CRD-01.1 · iteracion-26 #12 — Un código equivocado no deja sesión."""
        registrarse(APIClient())
        navegador = APIClient()

        response = verificar(navegador, code="000000")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert ACCESS_COOKIE not in response.cookies


def test_registration_has_its_own_throttle_scope() -> None:
    """CRD-01.1 · BOT-03 · iteracion-26 #12 — El registro usa el alcance
    ``register`` (5 por hora y dirección); ``signup`` ya no existe."""
    rates = settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]

    assert RegisterView.throttle_scope == "register"
    assert rates["register"] == "5/hour"
    assert "signup" not in rates


@pytest.mark.django_db
def test_the_sixth_registration_in_an_hour_is_429() -> None:
    """CRD-01.1 · BOT-03 · iteracion-26 #12 — Desde una misma dirección, la
    sexta cuenta en una hora espera."""
    client = APIClient()
    respuestas = [
        client.post(
            REGISTER,
            {"email": f"cuenta{n}@estudio.mx", "password": PASSWORD, **accepted()},
            format="json",
        ).status_code
        for n in range(6)
    ]

    assert respuestas[:5] == [status.HTTP_201_CREATED] * 5
    assert respuestas[5] == status.HTTP_429_TOO_MANY_REQUESTS


@pytest.mark.django_db
def test_a_bot_in_the_trap_field_gets_no_session() -> None:
    """CRD-01.1 · BOT-04 · iteracion-26 #12 — La respuesta de siempre, sin cuenta
    ni sesión detrás."""
    response = APIClient().post(
        REGISTER,
        {"email": EMAIL, "password": PASSWORD, "website": "http://spam", **accepted()},
        format="json",
    )

    assert response.status_code == status.HTTP_201_CREATED
    assert ACCESS_COOKIE not in response.cookies
    assert not User.objects.filter(email=EMAIL).exists()
