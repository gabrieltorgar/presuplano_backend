"""RED tests for US-82 — recuperar la contraseña.

Quien olvidaba su contraseña se quedaba fuera para siempre: no había pantalla ni
endpoint, y tampoco a quién escribirle. Se recupera con el mismo OTP que ya
verifica el correo, que es la identidad de la cuenta.
"""

import pytest
from rest_framework import status

REQUEST_URL = "/api/auth/password-reset/"
CONFIRM_URL = "/api/auth/password-reset/confirm/"


@pytest.mark.django_db
class TestPasswordReset:
    """US-82: volver a entrar cuando se olvidó la contraseña."""

    def test_asking_for_a_reset_accepts_a_known_email(self, api_client, user) -> None:
        """Flujo principal - Pedir recuperar con un correo de la casa."""
        response = api_client.post(REQUEST_URL, {"email": user.email}, format="json")

        assert response.status_code == status.HTTP_200_OK
        assert "detail" in response.data

    def test_an_unknown_email_answers_the_same(self, api_client) -> None:
        """Caso de borde - No se revela qué correos existen.

        Responder distinto convertiría esto en un detector de clientes: quien
        pregunta por mil correos sabría cuáles tienen cuenta.
        """
        conocido = api_client.post(
            REQUEST_URL, {"email": "otra@cuotreka.test"}, format="json"
        )
        desconocido = api_client.post(
            REQUEST_URL, {"email": "nadie@cuotreka.test"}, format="json"
        )

        assert conocido.status_code == desconocido.status_code == status.HTTP_200_OK
        assert conocido.data == desconocido.data

    def test_confirming_with_the_code_changes_the_password(
        self, api_client, user, settings
    ) -> None:
        """Flujo principal - Con el código, la contraseña queda cambiada."""
        response = api_client.post(
            CONFIRM_URL,
            {
                "email": user.email,
                "code": str(settings.OTP_UNIVERSAL_CODE),
                "password": "nuevaclave123",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        user.refresh_from_db()
        assert user.check_password("nuevaclave123")

    def test_the_new_password_lets_the_user_in(
        self, api_client, user, settings
    ) -> None:
        """Flujo principal - Y con ella se entra."""
        api_client.post(
            CONFIRM_URL,
            {
                "email": user.email,
                "code": str(settings.OTP_UNIVERSAL_CODE),
                "password": "nuevaclave123",
            },
            format="json",
        )

        entrada = api_client.post(
            "/api/auth/login/",
            {"email": user.email, "password": "nuevaclave123"},
            format="json",
        )

        assert entrada.status_code == status.HTTP_200_OK
        assert "access" in entrada.data

    def test_a_wrong_code_changes_nothing(self, api_client, user) -> None:
        """Caso alternativo - Un código inválido no cambia la contraseña."""
        response = api_client.post(
            CONFIRM_URL,
            {"email": user.email, "code": "000000", "password": "nuevaclave123"},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        user.refresh_from_db()
        assert not user.check_password("nuevaclave123")

    def test_an_unknown_email_cannot_be_confirmed(self, api_client, settings) -> None:
        """Caso alternativo - Sin cuenta no hay nada que recuperar."""
        response = api_client.post(
            CONFIRM_URL,
            {
                "email": "nadie@cuotreka.test",
                "code": str(settings.OTP_UNIVERSAL_CODE),
                "password": "nuevaclave123",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_a_short_password_is_rejected(self, api_client, user, settings) -> None:
        """Caso alternativo - La contraseña nueva cumple lo mismo que al alta."""
        response = api_client.post(
            CONFIRM_URL,
            {
                "email": user.email,
                "code": str(settings.OTP_UNIVERSAL_CODE),
                "password": "corta",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "password" in response.data

    def test_recovering_verifies_the_email(
        self, api_client, user_factory, settings
    ) -> None:
        """Caso de borde - Quien recupera, demuestra que el correo es suyo.

        Una cuenta que se quedó sin verificar podía registrarse y no entrar
        nunca; recuperar la contraseña prueba lo mismo que la verificación.
        """
        pendiente = user_factory(is_email_verified=False)

        api_client.post(
            CONFIRM_URL,
            {
                "email": pendiente.email,
                "code": str(settings.OTP_UNIVERSAL_CODE),
                "password": "nuevaclave123",
            },
            format="json",
        )

        pendiente.refresh_from_db()
        assert pendiente.is_email_verified is True
