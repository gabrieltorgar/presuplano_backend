"""Límites de intentos (bug iteracion-12 #3, US-02 · US-03 · US-82 · US-89).

Sin tope, un código de seis dígitos se adivina probando, y una contraseña se
prueba contra una lista de las que se filtraron. Cada puerta pública tiene su
límite por dirección, cada código muere al quinto intento fallido, y el código
universal del MVP no abre nada en producción.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status

import core.settings as core_settings
from apps.accounts.models import OtpCode
from apps.accounts.services import check_otp, issue_otp, send_verification_code

LOGIN = "/api/auth/login/"


@pytest.fixture
def correo(settings, mocker):
    """El correo configurado, con el envío interceptado."""
    settings.RESEND_API_KEY = "re_test"
    return mocker.patch("apps.accounts.emails.mail.send_email", return_value=True)


def agotar(client, url, payload, veces, **extra):
    """Pide `veces` y devuelve la respuesta de la siguiente."""
    for _ in range(veces):
        client.post(url, payload, **extra)
    return client.post(url, payload, **extra)


@pytest.mark.django_db
class TestLimitesPorPuerta:
    """Cada puerta pública responde 429 al pasarse, con cuándo volver."""

    def test_login_stops_after_ten_tries_a_minute(self, api_client, user) -> None:
        """Flujo principal - El relleno de credenciales choca con el límite."""
        payload = {"email": user.email, "password": "no-es-esta"}

        response = agotar(api_client, LOGIN, payload, 10)

        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert int(response["Retry-After"]) > 0
        # Se dice en palabras de la aplicación, no con el texto del framework.
        assert "Demasiados intentos" in response.data["detail"]

    @pytest.mark.parametrize(
        ("url", "payload", "veces"),
        [
            # Verificar: 10 por minuto y dirección (otp_verify, iteracion-26 #16).
            ("/api/auth/verify-otp/", {"email": "a@b.mx", "code": "000000"}, 10),
            ("/api/auth/resend-otp/", {"email": "a@b.mx"}, 5),
            ("/api/auth/password-reset/", {"email": "a@b.mx"}, 5),
            (
                "/api/auth/password-reset/confirm/",
                {"email": "a@b.mx", "code": "000000", "password": "nueva12345"},
                10,
            ),
            (
                "/api/contact/",
                {"name": "Ana", "email": "a@b.mx", "message": "Hola"},
                5,
            ),
        ],
    )
    def test_each_public_door_has_its_limit(
        self, api_client, url, payload, veces
    ) -> None:
        response = agotar(api_client, url, payload, veces)

        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS

    def test_sending_documents_has_its_limit(
        self, authenticated_client, settings, mocker
    ) -> None:
        """Caso de borde - La aplicación no es un relevo de correo masivo.

        Con el alcance de las acciones costosas: 20 por hora (iteracion-26 #16).
        """
        settings.RESEND_API_KEY = "re_test"
        mocker.patch("common.mail.send_email", return_value=True)

        def enviar():
            return authenticated_client.post(
                "/api/documents/send/",
                {
                    "kind": "quote",
                    "to": "cliente@correo.mx",
                    "file": SimpleUploadedFile("c.pdf", b"%PDF-1.4", "application/pdf"),
                },
                format="multipart",
            )

        respuestas = [enviar().status_code for _ in range(21)]

        assert respuestas[:20] == [status.HTTP_200_OK] * 20
        assert respuestas[20] == status.HTTP_429_TOO_MANY_REQUESTS

    def test_other_doors_are_not_counted_together(self, api_client, user) -> None:
        """Caso de borde - Agotar el acceso no cierra la recuperación."""
        agotar(api_client, LOGIN, {"email": user.email, "password": "x"}, 10)

        response = api_client.post("/api/auth/password-reset/", {"email": user.email})

        assert response.status_code == status.HTTP_200_OK


class TestConfiguracionDeLimites:
    """El estado de los límites se comparte entre instancias."""

    def test_throttling_is_on_for_every_endpoint(self) -> None:
        rest = core_settings.REST_FRAMEWORK

        assert set(rest["DEFAULT_THROTTLE_CLASSES"]) == {
            "rest_framework.throttling.AnonRateThrottle",
            "rest_framework.throttling.UserRateThrottle",
            "rest_framework.throttling.ScopedRateThrottle",
            # Por cuenta (iteracion-26 #16): rotar la IP no reinicia un correo.
            "common.throttling.IdentifierRateThrottle",
        }
        assert {
            "anon",
            "user",
            "login",
            "otp_request",
            "otp_verify",
            "password_reset",
            "contact",
        } <= set(rest["DEFAULT_THROTTLE_RATES"])

    def test_the_counters_live_in_the_database_cache(self) -> None:
        """Flujo principal - En Vercel cada invocación puede ser otra instancia."""
        backend = core_settings.CACHES["default"]["BACKEND"]

        assert backend == "django.core.cache.backends.db.DatabaseCache"


@pytest.mark.django_db
class TestCodigoConIntentosContados:
    """Un código muere al quinto intento fallido."""

    def test_five_wrong_tries_void_the_code(self, user, correo) -> None:
        """Flujo principal - Ni el código correcto sirve después."""
        code = issue_otp(user=user, purpose=OtpCode.Purpose.PASSWORD_RESET)

        for _ in range(5):
            assert not check_otp(
                user=user, purpose=OtpCode.Purpose.PASSWORD_RESET, code="000000"
            )

        assert not check_otp(
            user=user, purpose=OtpCode.Purpose.PASSWORD_RESET, code=code
        )

    def test_a_few_mistakes_still_let_the_right_code_in(self, user, correo) -> None:
        """Caso alternativo - Equivocarse un par de veces es normal."""
        code = issue_otp(user=user, purpose=OtpCode.Purpose.SIGNUP)

        for _ in range(4):
            check_otp(user=user, purpose=OtpCode.Purpose.SIGNUP, code="000000")

        assert check_otp(user=user, purpose=OtpCode.Purpose.SIGNUP, code=code)

    def test_a_new_code_starts_counting_again(self, user, correo) -> None:
        """Caso alternativo - Pedir otro código da otros cinco intentos."""
        issue_otp(user=user, purpose=OtpCode.Purpose.SIGNUP)
        for _ in range(5):
            check_otp(user=user, purpose=OtpCode.Purpose.SIGNUP, code="000000")

        code = issue_otp(user=user, purpose=OtpCode.Purpose.SIGNUP)

        assert check_otp(user=user, purpose=OtpCode.Purpose.SIGNUP, code=code)


@pytest.mark.django_db
class TestCodigoUniversalCerrado:
    """El código universal sólo vive donde se pidió (local/develop, #15)."""

    def test_without_mail_in_production_the_universal_code_opens_nothing(
        self, user, settings
    ) -> None:
        """Flujo principal - Si el correo se cae, nadie entra con el de todos."""
        settings.RESEND_API_KEY = ""
        settings.OTP_UNIVERSAL_CODE = "123456"
        settings.OTP_UNIVERSAL_EMAILS = [user.email]

        assert not check_otp(user=user, purpose=OtpCode.Purpose.SIGNUP, code="123456")

    def test_without_mail_in_production_a_real_code_is_issued(
        self, user, settings, mocker
    ) -> None:
        """Caso alternativo - Se intenta mandar el código propio, no se regala."""
        settings.RESEND_API_KEY = ""
        enviar = mocker.patch("apps.accounts.services.send_otp_email")

        send_verification_code(user=user)

        assert enviar.called
        assert OtpCode.objects.filter(user=user).exists()

    def test_in_development_the_universal_code_still_works(
        self, user, settings
    ) -> None:
        """Caso alternativo - En local, sin correo, la cuenta de la lista se
        verifica con él."""
        settings.RESEND_API_KEY = ""
        settings.APP_ENV = "local"
        settings.OTP_UNIVERSAL_CODE = "123456"
        settings.OTP_UNIVERSAL_EMAILS = [user.email]

        assert check_otp(user=user, purpose=OtpCode.Purpose.SIGNUP, code="123456")

    def test_it_is_off_by_default_outside_debug(self) -> None:
        """Caso de borde - En Vercel (DEBUG apagado) no hay código universal:
        sin APP_ENV es producción y el código no tiene valor por omisión."""
        entorno = {
            k: v
            for k, v in os.environ.items()
            if k not in ("DEBUG", "APP_ENV", "OTP_UNIVERSAL_CODE")
        }
        entorno.update(VERCEL="1", DJANGO_SETTINGS_MODULE="core.settings")
        leer = (
            "from django.conf import settings as s;"
            "print(s.DEBUG, s.APP_ENV, repr(s.OTP_UNIVERSAL_CODE))"
        )

        salida = subprocess.run(  # noqa: S603 -- el mismo intérprete, sin shell
            [sys.executable, "-c", leer],
            cwd=Path(core_settings.__file__).resolve().parents[1],
            env=entorno,
            capture_output=True,
            text=True,
            check=True,
        )

        assert salida.stdout.split() == ["False", "production", "''"]
