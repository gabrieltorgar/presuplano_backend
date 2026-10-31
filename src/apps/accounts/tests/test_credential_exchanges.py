"""Intercambios de credenciales sin autenticar, solo JSON y cuerpos sin tokens
(iteracion-26 #10).

Hasta 4.0.0 la API leía también formularios (``application/x-www-form-urlencoded``
y multipart) en todas sus rutas: un ``<form>`` de otro sitio podía iniciar una
sesión en el navegador de quien lo visitara (CSRF de login). El acceso, el
registro, el código y la recuperación autenticaban la petición: una cookie de
acceso de una sesión muerta (la cuenta ya no existe) respondía 401 al intentar
entrar. Y la renovación aceptaba el refresh en el cuerpo, que ningún cliente
manda: la SPA lo renueva con la cookie.
"""

import pytest
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import Resolver404, resolve
from rest_framework import status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.otp_helpers import code_of
from apps.accounts.tests.test_organization import PNG
from apps.legal.tests.consent import accepted
from apps.team.tests.factories import InvitationFactory
from common.auth_cookies import ACCESS_COOKIE, REFRESH_COOKIE
from tests.platform.routes import api_routes, is_format_twin

LOGIN = "/api/auth/login/"
REFRESH = "/api/auth/refresh/"
PASSWORD = "testpass123"

#: Las únicas rutas que reciben archivos (multipart). ``plan-asset-detail`` es
#: de solo lectura: comparte la vista con la subida de ``plan-asset-list``.
UPLOAD_ROUTES = {
    "organization",
    "progress-evidence",
    "plan-photo-conversions",
    "plan-asset-list",
    "plan-asset-detail",
    "send",
}

#: Toda respuesta de usuario, de sesión o de equipo los deja fuera.
SENSITIVE = {
    "password",
    "password_hash",
    "code",
    "code_hash",
    "otp",
    "token",
    "token_hash",
    "access",
    "refresh",
    "is_superuser",
    "is_staff",
    "is_active",
    "groups",
    "user_permissions",
    "last_login",
}


def claves(obj):
    """Todas las claves de un JSON, también las anidadas."""
    if isinstance(obj, dict):
        for clave, valor in obj.items():
            yield clave
            yield from claves(valor)
    elif isinstance(obj, list):
        for elemento in obj:
            yield from claves(elemento)


def parsers_of(route) -> list:
    return list(route.initkwargs.get("parser_classes", route.cls.parser_classes))


@pytest.mark.django_db
class TestSoloJson:
    def test_login_rejects_form_encoded_body(self, user_factory) -> None:
        """SEC-04.2 · iteracion-26 #10 — Un formulario HTML de otro sitio no
        inicia sesión: la API sólo lee JSON (415)."""
        user = user_factory(password=PASSWORD)
        client = APIClient()

        response = client.post(
            LOGIN,
            f"email={user.email}&password={PASSWORD}",
            content_type="application/x-www-form-urlencoded",
        )

        assert response.status_code == status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
        assert ACCESS_COOKIE not in response.cookies

    def test_login_rejects_a_multipart_form_too(self, user_factory) -> None:
        """SEC-04.2 · iteracion-26 #10 — Ni un ``<form enctype=multipart>``."""
        user = user_factory(password=PASSWORD)

        response = APIClient().post(
            LOGIN, {"email": user.email, "password": PASSWORD}, format="multipart"
        )

        assert response.status_code == status.HTTP_415_UNSUPPORTED_MEDIA_TYPE

    def test_json_still_logs_in(self, user_factory) -> None:
        """SEC-04.2 · iteracion-26 #10 — Control positivo: con JSON, entra."""
        user = user_factory(password=PASSWORD)

        response = APIClient().post(
            LOGIN, {"email": user.email, "password": PASSWORD}, format="json"
        )

        assert response.status_code == status.HTTP_200_OK


def test_the_default_parser_is_json_only() -> None:
    """SEC-04.2 · iteracion-26 #10 — Una vista nueva sólo lee JSON."""
    assert settings.REST_FRAMEWORK["DEFAULT_PARSER_CLASSES"] == (
        "rest_framework.parsers.JSONParser",
    )


def test_no_route_reads_urlencoded_and_only_uploads_read_multipart() -> None:
    """SEC-04.2 · iteracion-26 #10 — Nadie manda formularios urlencoded; las
    subidas declaran MultiPartParser explícito y ninguna otra ruta lo lee."""
    form, multipart = [], []
    for route in api_routes():
        if is_format_twin(route):
            continue
        parsers = parsers_of(route)
        if FormParser in parsers:
            form.append(route.name)
        if MultiPartParser in parsers and route.name not in UPLOAD_ROUTES:
            multipart.append(route.name)
        assert set(parsers) <= {JSONParser, MultiPartParser}, route.name
    assert not form, f"leen application/x-www-form-urlencoded: {sorted(form)}"
    assert not multipart, f"leen multipart sin ser subidas: {sorted(multipart)}"


@pytest.mark.django_db
def test_an_upload_still_takes_its_file(user_factory) -> None:
    """SEC-04.2 · iteracion-26 #10 — Control positivo: el logotipo sube por
    multipart y el nombre sigue por JSON en la misma ruta."""
    client = APIClient()
    client.force_authenticate(user=user_factory())
    logo = client.patch(
        "/api/auth/organization/",
        {"logo": SimpleUploadedFile("logo.png", PNG, "image/png")},
        format="multipart",
    )
    nombre = client.patch(
        "/api/auth/organization/", {"name": "Estudio Reyes"}, format="json"
    )

    assert logo.status_code == status.HTTP_200_OK, logo.data
    assert nombre.status_code == status.HTTP_200_OK
    assert nombre.data["name"] == "Estudio Reyes"


def sesion_muerta() -> APIClient:
    """Un navegador con la cookie de acceso de una cuenta que ya no existe."""
    gone = UserFactory()
    access = str(AccessToken.for_user(gone))
    gone.delete()
    client = APIClient()
    client.cookies[ACCESS_COOKIE] = access
    return client


@pytest.mark.django_db
class TestLosIntercambiosNoAutentican:
    """SEC-04.5 · iteracion-26 #10 — Una cookie de acceso que quedó en el
    navegador nunca bloquea entrar, registrarse, verificar o recuperar."""

    def test_login_works_with_a_dead_access_cookie(self, user_factory) -> None:
        """SEC-04.5 · iteracion-26 #10 — Entrar con una sesión muerta: 200."""
        user = user_factory(password=PASSWORD)

        response = sesion_muerta().post(
            LOGIN, {"email": user.email, "password": PASSWORD}, format="json"
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.cookies[ACCESS_COOKIE].value

    def test_a_wrong_password_is_still_401(self, user_factory) -> None:
        """SEC-04.5 · iteracion-26 #10 — Sin autenticar la petición, unas
        credenciales malas siguen siendo 401 (no 403, que es «sin verificar»)."""
        user = user_factory(password=PASSWORD)

        response = sesion_muerta().post(
            LOGIN, {"email": user.email, "password": "otra-cosa-1"}, format="json"
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response["WWW-Authenticate"] == 'Bearer realm="api"'

    def test_login_ignores_a_bearer_header_too(self, user_factory) -> None:
        """SEC-04.5 · iteracion-26 #10 — Ni una cabecera Authorization vieja."""
        user = user_factory(password=PASSWORD)

        response = APIClient().post(
            LOGIN,
            {"email": user.email, "password": PASSWORD},
            format="json",
            HTTP_AUTHORIZATION="Bearer basura",
        )

        assert response.status_code == status.HTTP_200_OK

    def test_a_live_access_cookie_without_csrf_does_not_block_login(
        self, user_factory
    ) -> None:
        """SEC-04.5 · iteracion-26 #10 — Con otra sesión viva y sin X-CSRFToken,
        el acceso no es un 403 de CSRF: no lee la sesión."""
        user = user_factory(password=PASSWORD)
        client = APIClient(enforce_csrf_checks=True)
        client.cookies[ACCESS_COOKIE] = str(AccessToken.for_user(UserFactory()))

        response = client.post(
            LOGIN, {"email": user.email, "password": PASSWORD}, format="json"
        )

        assert response.status_code == status.HTTP_200_OK

    @pytest.mark.parametrize(
        ("url", "body", "expected"),
        [
            (
                "/api/auth/register/",
                {"email": "nueva@estudio.mx", "password": "Teja-Roja-81"},
                status.HTTP_201_CREATED,
            ),
            (
                "/api/auth/verify-otp/",
                {"email": "nadie@estudio.mx", "code": "000000"},
                # Un correo sin cuenta: el 400 de un código equivocado (#14).
                status.HTTP_400_BAD_REQUEST,
            ),
            (
                "/api/auth/resend-otp/",
                {"email": "nadie@estudio.mx"},
                status.HTTP_200_OK,
            ),
            (
                "/api/auth/password-reset/",
                {"email": "nadie@estudio.mx"},
                status.HTTP_200_OK,
            ),
            (
                "/api/auth/password-reset/confirm/",
                {
                    "email": "nadie@estudio.mx",
                    "code": "000000",
                    "password": "Teja-Roja-81",
                },
                status.HTTP_400_BAD_REQUEST,
            ),
        ],
    )
    def test_the_other_exchanges_ignore_a_dead_access_cookie(
        self, url, body, expected
    ) -> None:
        """SEC-04.5 · iteracion-26 #10 — Registro, código, reenvío y recuperación
        responden lo suyo, no 401."""
        if url.endswith("register/"):
            body = {**body, **accepted()}

        response = sesion_muerta().post(url, body, format="json")

        assert response.status_code == expected, response.data


@pytest.mark.django_db
class TestLaRenovacion:
    def test_refresh_answered_401_clears_both_cookies(self) -> None:
        """CRD-02.1 · SEC-04.5 · iteracion-26 #10 — Una sesión muerta se borra:
        el siguiente acceso, código o recuperación no carga una cookie vieja."""
        client = APIClient()
        client.cookies[ACCESS_COOKIE] = "vieja"
        client.cookies[REFRESH_COOKIE] = "basura"

        response = client.post(REFRESH, {}, format="json")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.cookies[ACCESS_COOKIE].value == ""
        assert response.cookies[REFRESH_COOKIE].value == ""

    def test_a_refresh_in_the_body_is_ignored(self, user_factory) -> None:
        """CRD-02.1 · iteracion-26 #10 — La renovación web sólo lee la cookie:
        un script que tuviera un refresh no lo cambia por una sesión."""
        refresh = str(RefreshToken.for_user(user_factory()))

        response = APIClient().post(REFRESH, {"refresh": refresh}, format="json")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert not response.cookies[ACCESS_COOKIE].value

    def test_the_refresh_cookie_renews_with_a_body_without_tokens(
        self, user_factory
    ) -> None:
        """CRD-02.1 · iteracion-26 #10 — Control positivo: con la cookie, 200 y
        el cuerpo sin tokens."""
        client = APIClient()
        client.cookies[REFRESH_COOKIE] = str(RefreshToken.for_user(user_factory()))

        response = client.post(REFRESH, {}, format="json")

        assert response.status_code == status.HTTP_200_OK
        assert {"access", "refresh"}.isdisjoint(claves(response.json()))
        assert response.cookies[ACCESS_COOKIE].value


def test_allauth_html_urls_not_mounted() -> None:
    """CRD-02.2 · iteracion-26 #10 — Sin registro ni acceso HTML fuera de la API
    (sin reCAPTCHA ni límites): ni allauth ni dj-rest-auth están montados."""
    for url in (
        "/accounts/signup/",
        "/accounts/login/",
        "/accounts/confirm-email/x/",
        "/api/auth/registration/",
        "/api/auth/password/reset/",
    ):
        with pytest.raises(Resolver404):
            resolve(url)
    installed = " ".join(settings.INSTALLED_APPS)
    assert "allauth" not in installed
    assert "dj_rest_auth" not in installed


@pytest.mark.django_db
def test_user_data_does_not_expose_sensitive_fields(user_factory, otp_sent) -> None:
    """API-03 · MAN-06 · iteracion-26 #10 — Ni contraseñas, códigos, tokens ni
    banderas internas en lo que la API dice de las cuentas y del equipo."""
    admin = user_factory(email="admin@estudioreyes.mx", password=PASSWORD)
    InvitationFactory(account=admin, email="bea@estudio.mx", token="enlace-bea")
    client = APIClient()
    respuestas = {
        "login": client.post(
            LOGIN, {"email": admin.email, "password": PASSWORD}, format="json"
        ),
        "me": client.get("/api/auth/me/"),
        "organization": client.get("/api/auth/organization/"),
        "team": client.get("/api/collaborators/"),
        "invite": client.post(
            "/api/collaborators/invitations/",
            {"emails": ["luis@obra.mx"]},
            format="json",
            HTTP_X_CSRFTOKEN=client.cookies[settings.CSRF_COOKIE_NAME].value,
        ),
        "register": APIClient().post(
            "/api/auth/register/",
            {"email": "nueva@estudio.mx", "password": "Teja-Roja-81", **accepted()},
            format="json",
        ),
        "verify": APIClient().post(
            "/api/auth/verify-otp/",
            # El código que le llegó al registrarse (iteracion-26 #15).
            {"email": "nueva@estudio.mx", "code": code_of(otp_sent)},
            format="json",
        ),
        "invitation": APIClient().get("/api/invitations/enlace-bea/"),
        "accept": APIClient().post(
            "/api/invitations/enlace-bea/accept/",
            {"password": "Teja-Roja-81", **accepted()},
            format="json",
        ),
    }

    for nombre, response in respuestas.items():
        assert response.status_code < 300, f"{nombre}: {response.status_code}"
        expuestas = SENSITIVE & set(claves(response.json()))
        assert not expuestas, f"{nombre} expone {sorted(expuestas)}"
