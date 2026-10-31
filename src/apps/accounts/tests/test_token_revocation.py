"""Las sesiones mueren con la contraseña (iteracion-26 #11).

Hasta 4.0.0 cambiar la contraseña ponía en la lista negra los refresh de las
otras sesiones, pero su access seguía sirviendo hasta vencer (media hora). Un
cambio hecho fuera de la API (el admin) no tocaba nada: el refresh de antes
seguía renovando. Con ``CHECK_REVOKE_TOKEN`` cada token lleva la huella de la
contraseña con la que nació y deja de servir en cuanto cambia; la renovación
revisa lo mismo.

Los tokens emitidos antes de encender la revisión no traen la huella: se
rechazan una vez (401 y la renovación también 401, que borra las cookies) y la
persona vuelve a entrar.
"""

import pytest
from django.conf import settings
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import OtpCode
from apps.accounts.services import issue_otp
from common.auth_cookies import ACCESS_COOKIE, REFRESH_COOKIE

LOGIN = "/api/auth/login/"
REFRESH = "/api/auth/refresh/"
ME = "/api/auth/me/"
PASSWORD_URL = "/api/auth/me/password/"
PASSWORD = "testpass123"
NEW_PASSWORD = "OtraClave#2026"


def entrar(client: APIClient, email: str = "ana@estudio.mx") -> None:
    response = client.post(LOGIN, {"email": email, "password": PASSWORD}, format="json")
    assert response.status_code == status.HTTP_200_OK


@pytest.fixture
def cuenta(user_factory):
    return user_factory(email="ana@estudio.mx", password=PASSWORD)


def test_tokens_carry_the_password_fingerprint() -> None:
    """CRD-02 · iteracion-26 #11 — La revisión está encendida."""
    assert settings.SIMPLE_JWT["CHECK_REVOKE_TOKEN"] is True


@pytest.mark.django_db
class TestLaContrasenaNuevaCierraLasSesiones:
    def test_the_other_sessions_access_dies_at_once(self, cuenta) -> None:
        """CRD-02 · iteracion-26 #11 — Las otras sesiones quedan fuera ya, no
        cuando venza su access."""
        aqui, alla = APIClient(), APIClient()
        entrar(aqui)
        entrar(alla)
        assert alla.get(ME).status_code == status.HTTP_200_OK

        cambio = aqui.post(
            PASSWORD_URL,
            {"current_password": PASSWORD, "new_password": NEW_PASSWORD},
            format="json",
        )

        assert cambio.status_code == status.HTTP_200_OK
        assert alla.get(ME).status_code == status.HTTP_401_UNAUTHORIZED
        assert alla.post(REFRESH).status_code == status.HTTP_401_UNAUTHORIZED
        # Quien la cambió sigue dentro con la sesión nueva, y la renueva.
        assert aqui.get(ME).status_code == status.HTTP_200_OK
        assert aqui.post(REFRESH).status_code == status.HTTP_200_OK
        assert aqui.get(ME).status_code == status.HTTP_200_OK

    def test_a_password_reset_kills_the_live_access(self, cuenta) -> None:
        """CRD-02 · iteracion-26 #11 — Quien recupera la contraseña deja fuera
        a cualquiera que tuviera la sesión, también su access."""
        alla = APIClient()
        entrar(alla)

        recuperada = APIClient().post(
            "/api/auth/password-reset/confirm/",
            {
                "email": cuenta.email,
                "code": issue_otp(user=cuenta, purpose=OtpCode.Purpose.PASSWORD_RESET),
                "password": NEW_PASSWORD,
            },
            format="json",
        )

        assert recuperada.status_code == status.HTTP_200_OK
        assert alla.get(ME).status_code == status.HTTP_401_UNAUTHORIZED

    def test_a_password_set_outside_the_api_kills_access_and_refresh(
        self, cuenta
    ) -> None:
        """CRD-02 · iteracion-26 #11 — Una contraseña puesta desde el admin
        tampoco deja viva la sesión: ni el access ni su renovación."""
        alla = APIClient()
        entrar(alla)

        cuenta.set_password(NEW_PASSWORD)
        cuenta.save()

        assert alla.get(ME).status_code == status.HTTP_401_UNAUTHORIZED
        renovada = alla.post(REFRESH)
        assert renovada.status_code == status.HTTP_401_UNAUTHORIZED
        assert renovada.cookies[ACCESS_COOKIE].value == ""
        assert renovada.cookies[REFRESH_COOKIE].value == ""


@pytest.mark.django_db
class TestSesionesDeAntes:
    def test_a_session_from_before_the_check_is_rejected_once(self, cuenta) -> None:
        """CRD-02 · iteracion-26 #11 — Un token sin la huella (emitido antes de
        encender la revisión) se rechaza; la renovación también y borra las
        cookies, y al volver a entrar todo sirve."""
        refresh = RefreshToken.for_user(cuenta)
        refresh.payload.pop(api_settings.REVOKE_TOKEN_CLAIM, None)
        client = APIClient()
        client.cookies[ACCESS_COOKIE] = str(refresh.access_token)
        client.cookies[REFRESH_COOKIE] = str(refresh)

        assert client.get(ME).status_code == status.HTTP_401_UNAUTHORIZED
        renovada = client.post(REFRESH)
        assert renovada.status_code == status.HTTP_401_UNAUTHORIZED
        assert renovada.cookies[REFRESH_COOKIE].value == ""

        entrar(client)
        assert client.get(ME).status_code == status.HTTP_200_OK

    def test_the_refresh_of_a_deleted_account_is_401(self, cuenta) -> None:
        """CRD-02 · iteracion-26 #11 — Una cuenta que ya no existe no rompe la
        renovación (era un 500): 401 y cookies borradas."""
        client = APIClient()
        client.cookies[REFRESH_COOKIE] = str(RefreshToken.for_user(cuenta))
        cuenta.delete()

        renovada = client.post(REFRESH)

        assert renovada.status_code == status.HTTP_401_UNAUTHORIZED
        assert renovada.cookies[REFRESH_COOKIE].value == ""
