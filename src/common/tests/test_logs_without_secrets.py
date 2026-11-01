"""Sin secretos en los registros (CRD-01 · iteracion-26 #21).

Ni contraseñas, ni códigos de un solo uso, ni tokens, ni la llave de Resend, ni
un correo completo: los registros de la plataforma los lee quien tenga acceso
al proyecto. Un correo se enmascara (``j***@dominio.com``). Lo que Resend
contesta al rechazar un envío puede repetir las direcciones: se enmascaran.
"""

import io
import logging
import urllib.error

import pytest
from rest_framework import status

from apps.accounts.tests.otp_helpers import code_of
from apps.legal.tests.consent import accepted
from common import mail

SECRETO = "re_llave_que_nunca_se_escribe"
PASSWORD = "Teja-Roja-81"
NUEVA = "Piedra-Lisa-42"


def registros(caplog) -> str:
    """Todo lo que quedó: los mensajes y cada campo extra de cada registro."""
    return "\n".join(
        f"{record.getMessage()} {record.__dict__!r}" for record in caplog.records
    )


def rechazo(endpoint: str, cuerpo: bytes) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        endpoint, 422, "Unprocessable", {}, io.BytesIO(cuerpo)
    )


@pytest.fixture
def otp_sent(settings, mocker):
    """El correo configurado y el envío del código interceptado (la frontera)."""
    settings.RESEND_API_KEY = SECRETO
    return mocker.patch("apps.accounts.services.send_otp_email", return_value=True)


@pytest.fixture
def resend(settings):
    settings.RESEND_API_KEY = SECRETO
    settings.RESEND_FROM = "Itzaka <hola@itzaka.com>"


class TestResendRechaza:
    """CRD-01 · el aviso del rechazo dice qué corregir sin escribir a quién."""

    def test_a_refused_email_logs_no_address(self, resend, mocker, caplog) -> None:
        cuerpo = (
            b'{"statusCode":422,"name":"validation_error",'
            b'"message":"Invalid `to` field: cliente.secreto@correo.mx"}'
        )
        mocker.patch(
            "urllib.request.urlopen",
            side_effect=rechazo(mail.RESEND_ENDPOINT, cuerpo),
        )

        with caplog.at_level(logging.DEBUG):
            mail.send_email(to="cliente.secreto@correo.mx", subject="x", html="x")

        texto = registros(caplog)
        assert "cliente.secreto@correo.mx" not in texto
        assert "c***@correo.mx" in texto
        assert "422" in texto and "validation_error" in texto
        assert SECRETO not in texto

    def test_a_refused_batch_logs_no_address(self, resend, mocker, caplog) -> None:
        cuerpo = (
            b'{"name":"validation_error","message":"ana@obra.mx and '
            b'beto.ruiz@obra.mx are not valid"}'
        )
        mocker.patch(
            "urllib.request.urlopen",
            side_effect=rechazo(mail.RESEND_BATCH_ENDPOINT, cuerpo),
        )
        mensajes = [
            mail.Message(to=correo, subject="x", html="x")
            for correo in ("ana@obra.mx", "beto.ruiz@obra.mx")
        ]

        with caplog.at_level(logging.DEBUG):
            mail.send_batch(mensajes)

        texto = registros(caplog)
        assert "ana@obra.mx" not in texto
        assert "beto.ruiz@obra.mx" not in texto
        assert "a***@obra.mx" in texto and "b***@obra.mx" in texto

    def test_a_body_that_is_not_text_is_left_out(self, resend, mocker, caplog):
        """Caso de borde - Lo que no se puede leer no se escribe a ciegas."""
        mocker.patch(
            "urllib.request.urlopen",
            side_effect=rechazo(mail.RESEND_ENDPOINT, b"\xff\xfe\x00 binario"),
        )

        with caplog.at_level(logging.DEBUG):
            assert mail.send_email(to="ana@obra.mx", subject="x", html="x") is False

        assert "ana@obra.mx" not in registros(caplog)


@pytest.mark.django_db
class TestLaCuentaEnLosRegistros:
    """CRD-01 · registrarse, verificar y recuperar no dejan credenciales escritas."""

    def test_signing_up_verifying_and_recovering_leave_no_secret(
        self, api_client, otp_sent, caplog
    ) -> None:
        correo = "persona.privada@estudio.mx"
        with caplog.at_level(logging.DEBUG):
            api_client.post(
                "/api/auth/register/",
                {"email": correo, "password": PASSWORD, **accepted()},
                format="json",
            )
            alta = code_of(otp_sent)
            verificada = api_client.post(
                "/api/auth/verify-otp/", {"email": correo, "code": alta}, format="json"
            )
            api_client.post(
                "/api/auth/password-reset/", {"email": correo}, format="json"
            )
            recuperacion = code_of(otp_sent)
            recuperada = api_client.post(
                "/api/auth/password-reset/confirm/",
                {"email": correo, "code": recuperacion, "password": NUEVA},
                format="json",
            )
            entrada = api_client.post(
                "/api/auth/login/",
                {"email": correo, "password": NUEVA},
                format="json",
            )

        assert verificada.status_code == status.HTTP_200_OK
        assert recuperada.status_code == entrada.status_code == status.HTTP_200_OK
        texto = registros(caplog)
        for secreto in (correo, PASSWORD, NUEVA, alta, recuperacion):
            assert secreto not in texto
        sesion = [c.value for c in entrada.cookies.values() if c.value]
        assert sesion
        for valor in sesion:
            assert valor not in texto
