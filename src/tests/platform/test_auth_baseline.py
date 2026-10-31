"""Línea base de la sesión web (TDD-B01, iteracion-25 #10).

No sale de una historia: la sesión vive en cookies HttpOnly con CSRF, el
refresh rota y el usado queda en la lista negra, los códigos de un solo uso se
guardan cifrados y no hay rutas de app móvil (CRD-02, CRD-04, SEC-04). Esta API
usa simplejwt con sus propias vistas (no dj-rest-auth), así que se prueba su
contrato, no los ajustes de REST_AUTH.
"""

from datetime import timedelta

import pytest
from django.conf import settings as dj_settings
from django.http import HttpResponse
from django.urls import Resolver404, resolve
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from apps.accounts.models import OtpCode
from common.auth_cookies import (
    ACCESS_COOKIE,
    ACCESS_PATH,
    REFRESH_COOKIE,
    REFRESH_PATH,
    set_token_cookies,
)

CSRF = "/api/auth/csrf/"
#: Una escritura cualquiera de la cuenta, con la sesión en la cookie.
WRITE = "/api/auth/organization/"


def test_token_blacklist_is_installed():
    """CRD-02: sin token_blacklist, rotar y salir dejan vivos los refresh viejos;
    sin CHECK_REVOKE_TOKEN, cambiar la contraseña deja viva cada sesión de antes
    (iteracion-26 #11)."""
    jwt = dj_settings.SIMPLE_JWT
    assert "rest_framework_simplejwt.token_blacklist" in dj_settings.INSTALLED_APPS
    assert hasattr(RefreshToken, "blacklist")
    assert jwt["ROTATE_REFRESH_TOKENS"] is True
    assert jwt["BLACKLIST_AFTER_ROTATION"] is True
    assert jwt.get("CHECK_REVOKE_TOKEN") is True, "la contraseña nueva no revoca"
    assert jwt["ACCESS_TOKEN_LIFETIME"] <= timedelta(minutes=30)
    assert jwt["REFRESH_TOKEN_LIFETIME"] <= timedelta(days=7)


def test_the_session_lives_in_httponly_cookies():
    """CRD-02: JavaScript no lee la sesión; el refresh solo va a /api/auth/."""
    response = HttpResponse()

    set_token_cookies(response, access="a", refresh="r")

    for name, path in ((ACCESS_COOKIE, ACCESS_PATH), (REFRESH_COOKIE, REFRESH_PATH)):
        cookie = response.cookies[name]
        assert cookie["httponly"] is True, name
        assert cookie["samesite"] == "Lax", name
        assert cookie["path"] == path, name
        assert bool(cookie["secure"]) is dj_settings.SESSION_COOKIE_SECURE, name
    assert REFRESH_PATH == "/api/auth/"


@pytest.mark.django_db
def test_cookie_jwt_requires_csrf(user_factory):
    """SEC-04: con la sesión en la cookie, una escritura sin X-CSRFToken es 403."""
    user = user_factory(is_email_verified=True)
    client = APIClient(enforce_csrf_checks=True)
    client.cookies[ACCESS_COOKIE] = str(AccessToken.for_user(user))

    denied = client.patch(WRITE, {}, format="json")
    assert denied.status_code == 403
    assert "CSRF" in str(denied.data["detail"])

    assert client.get(CSRF).status_code == 204
    token = client.cookies[dj_settings.CSRF_COOKIE_NAME].value
    allowed = client.patch(WRITE, {}, format="json", HTTP_X_CSRFTOKEN=token)
    assert allowed.status_code != 403


def test_otp_codes_are_stored_hashed():
    """CRD-04: el código nunca se guarda en claro y cuenta sus intentos."""
    names = {field.name for field in OtpCode._meta.get_fields()}

    assert "code" not in names
    assert {"code_hash", "attempts"} <= names


def test_there_are_no_mobile_auth_routes():
    """Sin app móvil: ninguna ruta entrega tokens en el cuerpo."""
    with pytest.raises(Resolver404):
        resolve("/api/auth/mobile/login/")
