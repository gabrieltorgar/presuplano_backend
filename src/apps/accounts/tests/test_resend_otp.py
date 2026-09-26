"""RED tests for US-89 — reenviar el código de verificación.

Quien no recibía el código se quedaba mirando la pantalla: no había forma de
pedirlo otra vez sin volver a registrarse, que además falla porque el correo
ya existe.
"""

import logging

import pytest
from rest_framework import status

URL = "/api/auth/resend-otp/"


@pytest.mark.django_db
class TestResendOtp:
    """US-89: pedir el código de verificación otra vez."""

    def test_a_pending_account_can_ask_for_the_code_again(
        self, api_client, user_factory, caplog
    ) -> None:
        """Flujo principal - Una cuenta sin verificar pide el código otra vez."""
        pendiente = user_factory(is_email_verified=False)

        with caplog.at_level(logging.INFO, logger="apps"):
            response = api_client.post(URL, {"email": pendiente.email}, format="json")

        assert response.status_code == status.HTTP_200_OK
        assert "detail" in response.data
        assert any(
            "Verification code requested" in record.message for record in caplog.records
        )

    def test_an_unknown_email_answers_the_same(self, api_client, user_factory) -> None:
        """Caso de borde - No se revela qué correos existen.

        Responder distinto convertiría esto en un detector de clientes: quien
        pregunta por mil correos sabría cuáles tienen cuenta.
        """
        pendiente = user_factory(is_email_verified=False)

        conocido = api_client.post(URL, {"email": pendiente.email}, format="json")
        desconocido = api_client.post(
            URL, {"email": "nadie@presuplano.test"}, format="json"
        )

        assert conocido.status_code == desconocido.status_code == status.HTTP_200_OK
        assert conocido.data == desconocido.data

    def test_an_already_verified_email_answers_the_same(self, api_client, user) -> None:
        """Caso alternativo - Una cuenta ya verificada tampoco se distingue."""
        response = api_client.post(URL, {"email": user.email}, format="json")

        assert response.status_code == status.HTTP_200_OK
        assert "detail" in response.data

    def test_an_email_is_required(self, api_client) -> None:
        """Caso de borde - Sin correo no hay nada que reenviar."""
        response = api_client.post(URL, {}, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Escribe tu correo" in str(response.data)

    def test_only_post_is_allowed(self, api_client) -> None:
        """Caso de borde - Pedirlo por GET no reenvía nada."""
        response = api_client.get(URL)

        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED
