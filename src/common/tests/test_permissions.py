"""La API pide, por omisión, una cuenta con el correo verificado (iteracion-26 #8).

Hasta 4.0.0 el permiso por omisión era ``IsAuthenticated``: la sesión de una
cuenta sin verificar usaba toda la API. Una cuenta sin verificar no podía
entrar (el acceso le pedía el código), pero nada en la API lo garantizaba, y el
registro abre esa sesión desde #12. Ahora ``IsVerifiedUser`` es el permiso por
omisión y el de cada vista que declara los suyos; una sesión sin verificar sólo
llega a lo que hace falta para verificar: saber quién es (``GET me/``), el
código y su reenvío, renovar, salir y la cookie CSRF.
"""

import pytest
from django.conf import settings
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.tests.factories import UserFactory
from apps.legal.tests.consent import accepted
from apps.team.tests.factories import InvitationFactory
from common.auth_cookies import ACCESS_COOKIE, REFRESH_COOKIE
from common.permissions import EMAIL_NOT_VERIFIED, IsVerifiedUser
from tests.platform.routes import api_routes, is_format_twin, sample_url

ME = "/api/auth/me/"
CLIENTS = "/api/clients/"

#: Lo único que una sesión sin verificar alcanza fuera de las rutas públicas:
#: la SPA pregunta quién es y, con ``is_email_verified`` en falso, lo lleva a
#: escribir su código.
UNVERIFIED_REACHES = {("me", "get")}


def sesion_de(user) -> APIClient:
    """Un navegador con la sesión de esa cuenta en sus cookies."""
    client = APIClient()
    refresh = RefreshToken.for_user(user)
    client.cookies[ACCESS_COOKIE] = str(refresh.access_token)
    client.cookies[REFRESH_COOKIE] = str(refresh)
    return client


@pytest.fixture
def sin_verificar(db):
    return UserFactory(email="nueva@estudio.mx", is_email_verified=False)


def test_the_default_permission_is_the_verified_user() -> None:
    """SEC-02 · iteracion-26 #8 — Una vista nueva sin permisos propios ya lo exige."""
    assert settings.REST_FRAMEWORK["DEFAULT_PERMISSION_CLASSES"] == (
        "common.permissions.IsVerifiedUser",
    )


@pytest.mark.django_db
class TestUnaSesionSinVerificar:
    def test_a_data_route_answers_403_email_not_verified(self, sin_verificar) -> None:
        """SEC-02 · iteracion-26 #8 — La SPA reconoce el código y lleva a /verify."""
        response = sesion_de(sin_verificar).get(CLIENTS)

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert response.json() == {
            "detail": "Verifica tu correo para continuar.",
            "code": EMAIL_NOT_VERIFIED,
        }

    def test_it_still_knows_who_is_in(self, sin_verificar) -> None:
        """SEC-02 · iteracion-26 #8 — ``GET me/`` responde aunque no esté verificada."""
        response = sesion_de(sin_verificar).get(ME)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["email"] == "nueva@estudio.mx"
        assert response.data["is_email_verified"] is False

    def test_it_cannot_start_an_email_change(self, sin_verificar) -> None:
        """SEC-02 · iteracion-26 #8 — Lo demás de ``me/`` pide la cuenta verificada."""
        response = sesion_de(sin_verificar).patch(
            ME, {"email": "otra@estudio.mx"}, format="json"
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert response.json()["code"] == EMAIL_NOT_VERIFIED

    def test_it_can_renew_and_close_the_session(self, sin_verificar) -> None:
        """SEC-02 · iteracion-26 #8 — Renovar y salir no piden la verificación."""
        client = sesion_de(sin_verificar)

        assert client.post("/api/auth/refresh/").status_code == status.HTTP_200_OK
        assert client.post("/api/auth/logout/").status_code == (
            status.HTTP_204_NO_CONTENT
        )

    def test_without_a_session_it_is_still_401(self) -> None:
        """SEC-02 · iteracion-26 #8 — Sin sesión es 401 (la SPA renueva), no 403."""
        assert APIClient().get(CLIENTS).status_code == status.HTTP_401_UNAUTHORIZED

    def test_a_verified_account_works_as_before(self) -> None:
        """SEC-02 · iteracion-26 #8 — Control positivo: verificada, la ruta responde."""
        cuenta = UserFactory(is_email_verified=True)

        assert sesion_de(cuenta).get(CLIENTS).status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_every_private_route_refuses_an_unverified_account(sin_verificar) -> None:
    """SEC-02 · iteracion-26 #8 — Cada método de cada ruta con sesión responde 403
    ``email_not_verified`` a una cuenta sin verificar, salvo ``GET me/``.

    Una vista que declara ``permission_classes = [IsAuthenticated]`` reemplaza el
    permiso por omisión: esta prueba la encuentra.
    """
    client = APIClient()
    client.force_authenticate(user=sin_verificar)
    offenders, checked = [], 0
    for route in api_routes():
        if is_format_twin(route) or not route.permissions:
            continue
        if AllowAny in route.permissions:
            continue
        url = sample_url(route)
        for method in route.methods:
            if (route.name, method) in UNVERIFIED_REACHES:
                continue
            checked += 1
            response = client.generic(method.upper(), url)
            # HEAD responde sin cuerpo: basta el estado.
            code = response.json().get("code") if method != "head" else None
            if response.status_code != status.HTTP_403_FORBIDDEN or (
                method != "head" and code != EMAIL_NOT_VERIFIED
            ):
                offenders.append(
                    f"{method.upper()} {url} ({route.name}): {response.status_code}"
                )
    assert checked > 50, f"solo {checked} peticiones: ¿cambió el URLconf?"
    assert not offenders, "usa IsVerifiedUser en sus permisos:\n" + "\n".join(offenders)


@pytest.mark.django_db
def test_an_invited_collaborator_reaches_the_company_data(api_client) -> None:
    """SEC-02 · iteracion-26 #8 — La cuenta que nace de una invitación ya está
    verificada (el enlace llegó a su correo): el permiso nuevo no la deja fuera."""
    admin = UserFactory(email="admin@estudioreyes.mx")
    InvitationFactory(account=admin, email="bea@estudio.mx", token="enlace-bea")

    aceptada = api_client.post(
        "/api/invitations/enlace-bea/accept/",
        {"password": "Teja-Roja-81", **accepted()},
        format="json",
    )

    assert aceptada.status_code == status.HTTP_201_CREATED
    assert aceptada.data["user"]["is_email_verified"] is True
    assert api_client.get(CLIENTS).status_code == status.HTTP_200_OK


def test_the_permission_is_an_authenticated_check_too() -> None:
    """SEC-02 · iteracion-26 #8 — Hereda de IsAuthenticated: sin sesión, 401."""
    assert issubclass(IsVerifiedUser, IsAuthenticated)
