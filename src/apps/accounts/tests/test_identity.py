"""El correo es la cuenta: por ahí se entra y por ahí llega el código.

Al principio la identidad era el teléfono; después se pudo entrar con uno u
otro. No había cómo mandarle un código a un teléfono, así que ahora sólo se
entra con correo, y el teléfono que sale en los documentos es el de la
organización, no el de la cuenta.
"""

import pytest
from django.utils import timezone
from rest_framework import status

from apps.accounts.models import OtpCode, User

REGISTER = "/api/auth/register/"
LOGIN = "/api/auth/login/"
VERIFY = "/api/auth/verify-otp/"
ME = "/api/auth/me/"


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
    """Una cuenta es su correo."""

    def test_registering_with_an_email_creates_the_account(
        self, api_client, correo
    ) -> None:
        """Flujo principal - Alta con correo."""
        response = api_client.post(
            REGISTER, {"email": "Ana@Estudio.mx", "password": "secret123"}
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["email"] == "ana@estudio.mx"
        assert "phone" not in response.data
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
            VERIFY, {"email": "ana@estudio.mx", "code": codigo_enviado(correo)}
        )

        assert response.status_code == status.HTTP_200_OK
        assert User.objects.get(email="ana@estudio.mx").is_email_verified is True

    def test_the_universal_code_does_not_open_an_account_once_mail_works(
        self, api_client, correo, settings
    ) -> None:
        """Caso de borde - Quien puede recibir el suyo necesita el suyo."""
        api_client.post(REGISTER, {"email": "ana@estudio.mx", "password": "secret123"})

        response = api_client.post(
            VERIFY, {"email": "ana@estudio.mx", "code": settings.OTP_UNIVERSAL_CODE}
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_a_code_is_spent_when_used(self, api_client, correo) -> None:
        """Caso de borde - El mismo código no sirve dos veces."""
        api_client.post(REGISTER, {"email": "ana@estudio.mx", "password": "secret123"})
        code = codigo_enviado(correo)
        api_client.post(VERIFY, {"email": "ana@estudio.mx", "code": code})
        User.objects.filter(email="ana@estudio.mx").update(is_email_verified=False)

        response = api_client.post(VERIFY, {"email": "ana@estudio.mx", "code": code})

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_an_expired_code_does_not_work(self, api_client, correo) -> None:
        """Caso de borde - Un código vencido es un código muerto."""
        api_client.post(REGISTER, {"email": "ana@estudio.mx", "password": "secret123"})
        code = codigo_enviado(correo)
        OtpCode.objects.update(
            expires_at=timezone.now() - timezone.timedelta(minutes=1)
        )

        response = api_client.post(VERIFY, {"email": "ana@estudio.mx", "code": code})

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_logging_in_with_the_email_ignores_capitals(
        self, api_client, correo
    ) -> None:
        """Flujo principal - Se entra con el correo, como sea que se escriba."""
        api_client.post(REGISTER, {"email": "ana@estudio.mx", "password": "secret123"})
        api_client.post(
            VERIFY, {"email": "ana@estudio.mx", "code": codigo_enviado(correo)}
        )

        response = api_client.post(
            LOGIN, {"email": " ANA@estudio.mx ", "password": "secret123"}
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["access"]

    def test_a_screen_that_still_sends_identifier_can_log_in(
        self, api_client, user_factory
    ) -> None:
        """Caso alternativo - Una pantalla vieja todavía abierta no se queda fuera."""
        cuenta = user_factory(password="testpass123")

        response = api_client.post(
            LOGIN, {"identifier": cuenta.email, "password": "testpass123"}
        )

        assert response.status_code == status.HTTP_200_OK

    def test_a_phone_is_no_longer_a_way_in(self, api_client, user_factory) -> None:
        """Caso de borde - Un teléfono no es un correo."""
        user_factory(password="testpass123")

        response = api_client.post(
            LOGIN, {"identifier": "5512345678", "password": "testpass123"}
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Escribe un correo válido" in str(response.data)

    def test_registering_without_an_email_is_refused(self, api_client) -> None:
        """Caso de borde - Sin correo no hay cuenta."""
        response = api_client.post(
            REGISTER, {"phone": "5512345678", "password": "secret123"}
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Escribe tu correo para registrarte" in str(response.data["email"])
        assert User.objects.count() == 0

    def test_an_email_already_taken_is_refused(self, api_client, correo) -> None:
        """Caso alternativo - Un correo es de una sola cuenta."""
        api_client.post(REGISTER, {"email": "ana@estudio.mx", "password": "secret123"})

        response = api_client.post(
            REGISTER, {"email": "ANA@estudio.mx", "password": "secret123"}
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Ese correo ya está registrado" in str(response.data)


@pytest.mark.django_db
class TestPerfilDeIdentidad:
    """Desde el perfil se cambia el correo con el que se entra."""

    def test_changing_the_email_leaves_it_pending(
        self, authenticated_client, user, correo
    ) -> None:
        """Flujo principal - El correo nuevo entra sin verificar."""
        response = authenticated_client.patch(
            ME, {"email": "nuevo@estudio.mx"}, format="json"
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["email"] == "nuevo@estudio.mx"
        assert response.data["is_email_verified"] is False
        assert "phone" not in response.data
        assert correo.called

    def test_the_same_email_changes_nothing(
        self, authenticated_client, user, correo
    ) -> None:
        """Caso alternativo - Guardar el mismo correo no lo deja pendiente."""
        response = authenticated_client.patch(
            ME, {"email": user.email.upper()}, format="json"
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["is_email_verified"] is True
        assert not correo.called

    def test_an_email_of_another_account_is_refused(
        self, authenticated_client, user_factory
    ) -> None:
        """Caso de borde - No se puede tomar el correo de otro."""
        user_factory(email="ocupado@estudio.mx")

        response = authenticated_client.patch(
            ME, {"email": "ocupado@estudio.mx"}, format="json"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Ese correo ya está registrado" in str(response.data)

    def test_an_account_cannot_be_left_without_an_email(
        self, authenticated_client, user
    ) -> None:
        """Caso de borde - Quedarse sin correo cerraría la puerta."""
        response = authenticated_client.patch(ME, {"email": ""}, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Tu cuenta necesita un correo" in str(response.data)

    def test_without_a_session_nothing_changes(self, api_client) -> None:
        """Caso de borde - Sin sesión no se toca la cuenta."""
        response = api_client.patch(ME, {"email": "x@y.mx"}, format="json")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestCorreoSinVerificar:
    """Una cuenta entra cuando su correo está verificado."""

    def test_an_unverified_email_does_not_open_the_account(
        self, api_client, user_factory, correo
    ) -> None:
        """Flujo principal - Con el correo sin verificar no se entra."""
        cuenta = user_factory(is_email_verified=False, password="testpass123")

        response = api_client.post(
            LOGIN, {"email": cuenta.email, "password": "testpass123"}
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert response.data["code"] == "phone_not_verified"
        assert response.data["identity"] == cuenta.email

    def test_the_code_goes_out_by_itself(
        self, api_client, user_factory, correo
    ) -> None:
        """Flujo principal - El código sale solo al intentar entrar."""
        cuenta = user_factory(is_email_verified=False, password="testpass123")

        api_client.post(LOGIN, {"email": cuenta.email, "password": "testpass123"})

        assert correo.called

    def test_changing_the_email_closes_the_door_until_it_is_verified(
        self, authenticated_client, api_client, user, correo
    ) -> None:
        """Caso de borde - Cambiar el correo obliga a confirmarlo."""
        user.set_password("testpass123")
        user.save(update_fields=["password"])
        authenticated_client.patch(ME, {"email": "nuevo@estudio.mx"}, format="json")

        response = api_client.post(
            LOGIN, {"email": "nuevo@estudio.mx", "password": "testpass123"}
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert response.data["identity"] == "nuevo@estudio.mx"
