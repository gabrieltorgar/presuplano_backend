"""Las llaves de caché de los límites con HMAC SHA-256 (iteracion-27 #8).

``salted_hmac`` sin ``algorithm`` usa SHA-1 y avisa ``RemovedInDjango2028Warning``
(en Django 2028 el valor por omisión pasa a SHA-256). Las tres llaves que la
llevaban —el cierre del login del admin, el límite por cuenta y la cuota de
códigos— lo piden explícito: la huella sale de SHA-256 y sin aviso. Las llaves
cambian una vez, así que al desplegar los contadores vigentes vuelven a cero.
"""

import warnings

import pytest
from django.test import RequestFactory
from django.utils.crypto import salted_hmac
from django.utils.deprecation import RemovedInDjango2028Warning
from rest_framework.parsers import JSONParser
from rest_framework.request import Request

from apps.accounts import otp_quota
from common.throttling import IdentifierRateThrottle
from core import admin_login

SHA256_HEX = 64


@pytest.fixture
def sin_avisos_de_django_2028():
    """Un RemovedInDjango2028Warning dentro de la prueba es un error."""
    with warnings.catch_warnings():
        warnings.simplefilter("error", RemovedInDjango2028Warning)
        yield


@pytest.mark.usefixtures("sin_avisos_de_django_2028")
class TestLlavesConSha256:
    def test_admin_login_lock_key(self) -> None:
        """Bug iteracion-27 #8 — El cierre del login del admin, por usuario."""
        request = RequestFactory().post(
            "/admin/login/", {"username": " Ana@Estudio.mx "}
        )

        keys = admin_login._keys(request)

        user_key = keys[1].removeprefix("admin-login:user:")
        assert len(user_key) == SHA256_HEX
        assert (
            user_key
            == salted_hmac(
                "admin-login", "ana@estudio.mx", algorithm="sha256"
            ).hexdigest()
        )

    def test_identifier_throttle_key(self) -> None:
        """Bug iteracion-27 #8 — El límite por cuenta, por el correo enviado."""
        raw = RequestFactory().post(
            "/api/auth/login/",
            {"email": "Ana@Estudio.mx", "purpose": "login"},
            content_type="application/json",
        )
        throttle = IdentifierRateThrottle()
        throttle.scope = "login_identifier"

        key = throttle.get_cache_key(Request(raw, parsers=[JSONParser()]), view=None)

        ident = salted_hmac(
            "throttle", "login:ana@estudio.mx", algorithm="sha256"
        ).hexdigest()
        assert key == throttle.cache_format % {
            "scope": "login_identifier",
            "ident": ident,
        }

    @pytest.mark.django_db
    def test_otp_quota_key(self, monkeypatch) -> None:
        """Bug iteracion-27 #8 — La cuota de códigos por correo y propósito."""
        seen: list[str] = []
        monkeypatch.setattr(
            otp_quota.cache, "add", lambda key, *a, **k: seen.append(key) or True
        )
        monkeypatch.setattr(otp_quota.cache, "incr", lambda key, *a, **k: 1)

        otp_quota.check_request_quota(
            email=" Ana@Estudio.mx ", purpose="password_reset"
        )

        expected = salted_hmac(
            "apps.accounts.otp-quota",
            "password_reset:ana@estudio.mx",
            algorithm="sha256",
        ).hexdigest()
        assert seen[0] == f"otp:cd:{expected}"
