"""Los correos de la cuenta: a quién van y qué dicen."""

import pytest

from apps.accounts.emails import send_email_changed_notice, send_otp_email
from apps.accounts.models import OtpCode


@pytest.fixture
def enviado(mocker):
    return mocker.patch("apps.accounts.emails.mail.send_email", return_value=True)


@pytest.mark.django_db
class TestCorreosDeLaCuenta:
    def test_the_signup_code_goes_to_the_account(self, user, enviado) -> None:
        """Flujo principal - El código del alta va al correo de la cuenta."""
        send_otp_email(
            user=user, code="123456", purpose=OtpCode.Purpose.SIGNUP, minutes=10
        )

        envio = enviado.call_args.kwargs
        assert envio["to"] == user.email
        assert envio["subject"] == "Tu código de presuplano"
        assert "123456" in envio["html"]

    def test_the_email_change_code_goes_to_the_new_address(self, user, enviado) -> None:
        """US-124 - El código de un cambio de correo va al correo nuevo."""
        send_otp_email(
            user=user,
            code="654321",
            purpose=OtpCode.Purpose.EMAIL_CHANGE,
            minutes=10,
            to="nuevo@estudio.mx",
        )

        envio = enviado.call_args.kwargs
        assert envio["to"] == "nuevo@estudio.mx"
        assert envio["subject"] == "Confirma tu correo nuevo en presuplano"
        assert "654321" in envio["html"]

    def test_the_old_address_is_told_about_the_change(self, enviado) -> None:
        """US-124 - Al correo de antes le llega el aviso del cambio."""
        send_email_changed_notice(
            old_email="viejo@estudio.mx", new_email="nuevo@estudio.mx"
        )

        envio = enviado.call_args.kwargs
        assert envio["to"] == "viejo@estudio.mx"
        assert "nuevo@estudio.mx" in envio["html"]
        assert "Si no fuiste tú" in envio["html"]
