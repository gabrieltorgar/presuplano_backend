"""US-124 y US-125 — cambiar el correo con su código y cambiar la contraseña.

El correo nuevo no reemplaza al de siempre hasta que se demuestra con el código
que le llega: un error de dedo no puede dejar la cuenta sin acceso.
"""

import pytest
from rest_framework import status

from apps.accounts.models import OtpCode

EMAIL = "/api/auth/me/email/"
VERIFY = "/api/auth/me/email/verify/"
RESEND = "/api/auth/me/email/resend/"
PASSWORD = "/api/auth/me/password/"
LOGIN = "/api/auth/login/"


@pytest.fixture
def correo(settings, mocker):
    """El correo configurado, con los envíos interceptados."""
    settings.RESEND_API_KEY = "re_test"
    return {
        "codigo": mocker.patch(
            "apps.accounts.services.send_otp_email", return_value=True
        ),
        "aviso": mocker.patch(
            "apps.accounts.services.send_email_changed_notice", return_value=True
        ),
    }


def ultimo_codigo(correo) -> str:
    return correo["codigo"].call_args.kwargs["code"]


@pytest.mark.django_db
class TestCambiarElCorreo:
    """US-124: el correo nuevo se confirma con el código que le llega."""

    def test_the_code_goes_to_the_new_email(
        self, authenticated_client, user, correo
    ) -> None:
        """Flujo principal - Pedir el cambio manda el código al correo nuevo."""
        anterior = user.email

        response = authenticated_client.post(EMAIL, {"email": "Nuevo@Estudio.mx"})

        assert response.status_code == status.HTTP_200_OK
        assert response.data["email"] == anterior
        assert response.data["pending_email"] == "nuevo@estudio.mx"
        envio = correo["codigo"].call_args.kwargs
        assert envio["to"] == "nuevo@estudio.mx"
        assert envio["purpose"] == OtpCode.Purpose.EMAIL_CHANGE

    def test_the_code_switches_the_account_and_warns_the_old_email(
        self, authenticated_client, user, correo, django_capture_on_commit_callbacks
    ) -> None:
        """Flujo principal - Con el código, la cuenta usa el correo nuevo."""
        anterior = user.email
        authenticated_client.post(EMAIL, {"email": "nuevo@estudio.mx"})

        with django_capture_on_commit_callbacks(execute=True):
            response = authenticated_client.post(
                VERIFY, {"code": ultimo_codigo(correo)}
            )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["email"] == "nuevo@estudio.mx"
        assert response.data["pending_email"] == ""
        assert response.data["is_email_verified"] is True
        correo["aviso"].assert_called_once_with(
            old_email=anterior, new_email="nuevo@estudio.mx"
        )

    def test_after_the_change_the_new_email_opens_the_account(
        self, authenticated_client, api_client, user, correo
    ) -> None:
        """Flujo principal - Se entra con el correo nuevo, ya no con el viejo."""
        anterior = user.email
        authenticated_client.post(EMAIL, {"email": "nuevo@estudio.mx"})
        authenticated_client.post(VERIFY, {"code": ultimo_codigo(correo)})

        nuevo = api_client.post(
            LOGIN, {"email": "nuevo@estudio.mx", "password": "testpass123"}
        )
        viejo = api_client.post(LOGIN, {"email": anterior, "password": "testpass123"})

        assert nuevo.status_code == status.HTTP_200_OK
        assert viejo.status_code == status.HTTP_401_UNAUTHORIZED

    def test_a_wrong_code_changes_nothing(
        self, authenticated_client, user, correo
    ) -> None:
        """Caso alternativo - Un código equivocado no cambia el correo."""
        anterior = user.email
        authenticated_client.post(EMAIL, {"email": "nuevo@estudio.mx"})

        response = authenticated_client.post(VERIFY, {"code": "000000"})

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Código de verificación inválido" in str(response.data)
        user.refresh_from_db()
        assert user.email == anterior
        assert user.pending_email == "nuevo@estudio.mx"

    def test_the_code_can_be_sent_again(self, authenticated_client, correo) -> None:
        """Flujo alternativo - Si no llegó, se pide otra vez."""
        authenticated_client.post(EMAIL, {"email": "nuevo@estudio.mx"})
        primero = ultimo_codigo(correo)

        response = authenticated_client.post(RESEND)

        assert response.status_code == status.HTTP_200_OK
        assert correo["codigo"].call_count == 2
        assert correo["codigo"].call_args.kwargs["to"] == "nuevo@estudio.mx"
        # El anterior deja de servir: sólo vale el último.
        assert authenticated_client.post(VERIFY, {"code": primero}).status_code == 400

    def test_the_change_can_be_cancelled(
        self, authenticated_client, user, correo
    ) -> None:
        """Flujo alternativo - Desistir deja todo como estaba."""
        authenticated_client.post(EMAIL, {"email": "nuevo@estudio.mx"})
        codigo = ultimo_codigo(correo)

        response = authenticated_client.delete(EMAIL)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["pending_email"] == ""
        assert authenticated_client.post(VERIFY, {"code": codigo}).status_code == 400

    @pytest.mark.parametrize(
        ("email", "message"),
        [
            ("ocupado@estudio.mx", "Ese correo ya está registrado"),
            ("no-es-correo", "Escribe un correo válido"),
            ("", "Escribe el correo nuevo"),
        ],
    )
    def test_an_impossible_email_is_refused(
        self, authenticated_client, user_factory, email, message
    ) -> None:
        """Caso de borde - Un correo ajeno, mal escrito o vacío."""
        user_factory(email="ocupado@estudio.mx")

        response = authenticated_client.post(EMAIL, {"email": email})

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert message in str(response.data)

    def test_the_same_email_is_not_a_change(self, authenticated_client, user) -> None:
        """Caso de borde - El correo de siempre no es un correo nuevo."""
        response = authenticated_client.post(EMAIL, {"email": user.email.upper()})

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Ese ya es el correo de tu cuenta" in str(response.data)

    def test_without_a_pending_change_there_is_nothing_to_confirm(
        self, authenticated_client
    ) -> None:
        """Caso de borde - Confirmar o reenviar sin haber pedido nada."""
        assert "pendiente" in str(
            authenticated_client.post(VERIFY, {"code": "123456"}).data
        )
        assert "pendiente" in str(authenticated_client.post(RESEND).data)

    def test_someone_else_took_it_meanwhile(
        self, authenticated_client, user_factory, correo
    ) -> None:
        """Caso de borde - Si otra cuenta lo tomó mientras llegaba el código."""
        authenticated_client.post(EMAIL, {"email": "nuevo@estudio.mx"})
        user_factory(email="nuevo@estudio.mx")

        response = authenticated_client.post(VERIFY, {"code": ultimo_codigo(correo)})

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Ese correo ya está registrado" in str(response.data)

    def test_without_mail_the_universal_code_confirms(
        self, authenticated_client, settings
    ) -> None:
        """Caso de borde - Sin correo configurado sirve el código universal."""
        settings.RESEND_API_KEY = ""
        authenticated_client.post(EMAIL, {"email": "nuevo@estudio.mx"})

        response = authenticated_client.post(
            VERIFY, {"code": settings.OTP_UNIVERSAL_CODE}
        )

        assert response.data["email"] == "nuevo@estudio.mx"


@pytest.mark.django_db
class TestCambiarLaContrasena:
    """US-125: la contraseña se cambia sabiendo la actual."""

    def test_the_new_password_opens_the_account(
        self, authenticated_client, api_client, user
    ) -> None:
        """Flujo principal - Con la nueva se entra; con la vieja, ya no."""
        response = authenticated_client.post(
            PASSWORD,
            {"current_password": "testpass123", "new_password": "nuevaclave123"},
        )

        assert response.status_code == status.HTTP_200_OK
        nueva = api_client.post(
            LOGIN, {"email": user.email, "password": "nuevaclave123"}
        )
        vieja = api_client.post(LOGIN, {"email": user.email, "password": "testpass123"})
        assert nueva.status_code == status.HTTP_200_OK
        assert vieja.status_code == status.HTTP_401_UNAUTHORIZED

    def test_a_wrong_current_password_changes_nothing(
        self, authenticated_client, user
    ) -> None:
        """Caso alternativo - Sin la contraseña actual no se cambia."""
        response = authenticated_client.post(
            PASSWORD, {"current_password": "otra-cosa", "new_password": "nuevaclave123"}
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "La contraseña actual no es correcta" in str(response.data)
        user.refresh_from_db()
        assert user.check_password("testpass123")

    @pytest.mark.parametrize(
        ("new_password", "message"),
        [
            ("corta", "al menos 8 caracteres"),
            ("testpass123", "distinta de la actual"),
        ],
    )
    def test_a_weak_or_repeated_password_is_refused(
        self, authenticated_client, new_password, message
    ) -> None:
        """Caso de borde - Las mismas reglas que al registrarse, y no repetir."""
        response = authenticated_client.post(
            PASSWORD, {"current_password": "testpass123", "new_password": new_password}
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert message in str(response.data)

    def test_it_needs_a_session(self, api_client) -> None:
        """Caso de borde - Sin sesión no hay contraseña que cambiar."""
        response = api_client.post(
            PASSWORD, {"current_password": "a", "new_password": "nuevaclave123"}
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
