"""Entrar con correo o con teléfono, y el código que llega de verdad.

Hasta aquí la identidad era el teléfono y el código de verificación era uno
solo para todos: servía mientras no hubiera por dónde mandar uno propio. Con
el correo sí lo hay, así que quien se registra con correo recibe el suyo y el
universal deja de abrirle la puerta.
"""

import pytest
from django.utils import timezone
from rest_framework import status

from apps.accounts.models import OtpCode, User

REGISTER = "/api/auth/register/"
LOGIN = "/api/auth/login/"
VERIFY = "/api/auth/verify-otp/"
ME = "/api/auth/me/"
RESET = "/api/auth/password-reset/"


@pytest.fixture
def correo(settings, mocker):
    """El correo configurado, con el envío interceptado."""
    settings.RESEND_API_KEY = "re_test"
    return mocker.patch("apps.accounts.services.send_otp_email", return_value=True)


def codigo_enviado(correo) -> str:
    """El código que salió en el último correo."""
    return correo.call_args.kwargs["code"]


@pytest.mark.django_db
class TestIdentidad:
    """Una cuenta se identifica por su teléfono, su correo, o ambos."""

    def test_registering_with_an_email_creates_the_account(
        self, api_client, correo
    ) -> None:
        """Flujo principal - Alta con correo."""
        response = api_client.post(
            REGISTER, {"email": "Ana@Estudio.mx", "password": "secret123"}
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["email"] == "ana@estudio.mx"
        assert response.data["phone"] is None
        assert User.objects.get(email="ana@estudio.mx").is_email_verified is False

    def test_the_code_travels_to_that_email(self, api_client, correo) -> None:
        """Flujo principal - El código sale hacia el correo del alta."""
        api_client.post(REGISTER, {"email": "ana@estudio.mx", "password": "secret123"})

        assert correo.called
        assert len(codigo_enviado(correo)) == 6
        assert OtpCode.objects.filter(purpose=OtpCode.Purpose.SIGNUP).count() == 1

    def test_that_code_verifies_the_account(self, api_client, correo) -> None:
        """Flujo principal - Con su código la cuenta queda verificada."""
        api_client.post(REGISTER, {"email": "ana@estudio.mx", "password": "secret123"})

        response = api_client.post(
            VERIFY, {"identifier": "ana@estudio.mx", "code": codigo_enviado(correo)}
        )

        assert response.status_code == status.HTTP_200_OK
        assert User.objects.get(email="ana@estudio.mx").is_email_verified is True

    def test_the_universal_code_no_longer_opens_an_account_with_email(
        self, api_client, correo, settings
    ) -> None:
        """Caso de borde - Quien puede recibir el suyo necesita el suyo."""
        api_client.post(REGISTER, {"email": "ana@estudio.mx", "password": "secret123"})

        response = api_client.post(
            VERIFY,
            {"identifier": "ana@estudio.mx", "code": settings.OTP_UNIVERSAL_CODE},
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_a_code_is_spent_when_used(self, api_client, correo) -> None:
        """Caso de borde - El mismo código no sirve dos veces."""
        api_client.post(REGISTER, {"email": "ana@estudio.mx", "password": "secret123"})
        code = codigo_enviado(correo)
        api_client.post(VERIFY, {"identifier": "ana@estudio.mx", "code": code})
        User.objects.filter(email="ana@estudio.mx").update(is_email_verified=False)

        response = api_client.post(
            VERIFY, {"identifier": "ana@estudio.mx", "code": code}
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_an_expired_code_does_not_work(self, api_client, correo) -> None:
        """Caso de borde - Un código vencido es un código muerto."""
        api_client.post(REGISTER, {"email": "ana@estudio.mx", "password": "secret123"})
        code = codigo_enviado(correo)
        OtpCode.objects.update(
            expires_at=timezone.now() - timezone.timedelta(minutes=1)
        )

        response = api_client.post(
            VERIFY, {"identifier": "ana@estudio.mx", "code": code}
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_logging_in_with_the_email(self, api_client, correo) -> None:
        """Flujo principal - Se entra con el correo."""
        api_client.post(REGISTER, {"email": "ana@estudio.mx", "password": "secret123"})
        api_client.post(
            VERIFY, {"identifier": "ana@estudio.mx", "code": codigo_enviado(correo)}
        )

        response = api_client.post(
            LOGIN, {"identifier": "ANA@estudio.mx", "password": "secret123"}
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["access"]

    def test_logging_in_with_the_phone_still_works(
        self, api_client, user_factory
    ) -> None:
        """Flujo principal - Y se sigue entrando con el teléfono."""
        account = user_factory(is_phone_verified=True, password="testpass123")

        response = api_client.post(
            LOGIN, {"identifier": account.phone, "password": "testpass123"}
        )

        assert response.status_code == status.HTTP_200_OK

    def test_registering_without_any_identity_is_refused(self, api_client) -> None:
        """Caso de borde - Sin teléfono ni correo no hay cuenta."""
        response = api_client.post(REGISTER, {"password": "secret123"})

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "teléfono o tu correo" in str(response.data)

    def test_an_email_already_taken_is_refused(self, api_client, correo) -> None:
        """Caso alternativo - Un correo es de una sola cuenta."""
        api_client.post(REGISTER, {"email": "ana@estudio.mx", "password": "secret123"})

        response = api_client.post(
            REGISTER, {"email": "ana@estudio.mx", "password": "secret123"}
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Ese correo ya está registrado" in str(response.data)


@pytest.mark.django_db
class TestPerfilDeIdentidad:
    """Desde el perfil se cambia con qué se entra."""

    def test_adding_an_email_leaves_it_pending(
        self, authenticated_client, user, correo
    ) -> None:
        """Flujo principal - El correo nuevo entra sin verificar."""
        response = authenticated_client.patch(
            ME, {"email": "nuevo@estudio.mx"}, format="json"
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["email"] == "nuevo@estudio.mx"
        assert response.data["is_email_verified"] is False
        assert correo.called

    def test_changing_the_phone_leaves_it_pending(
        self, authenticated_client, user
    ) -> None:
        """Flujo alternativo - Cambiar el teléfono lo deja por verificar."""
        response = authenticated_client.patch(
            ME, {"phone": "5599887766"}, format="json"
        )

        assert response.data["phone"] == "5599887766"
        assert response.data["is_phone_verified"] is False

    def test_an_email_of_another_account_is_refused(
        self, authenticated_client, user_factory
    ) -> None:
        """Caso de borde - No se puede tomar el correo de otro."""
        user_factory(email="ocupado@estudio.mx")

        response = authenticated_client.patch(
            ME, {"email": "ocupado@estudio.mx"}, format="json"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_an_account_cannot_be_left_without_any_identity(
        self, authenticated_client, user
    ) -> None:
        """Caso de borde - Quedarse sin teléfono ni correo cerraría la puerta."""
        response = authenticated_client.patch(ME, {"phone": ""}, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "necesita un teléfono o un correo" in str(response.data)

    def test_without_a_session_nothing_changes(self, api_client) -> None:
        """Caso de borde - Sin sesión no se toca la cuenta."""
        response = api_client.patch(ME, {"email": "x@y.mx"}, format="json")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
