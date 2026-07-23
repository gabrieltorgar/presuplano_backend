"""RED tests for US-02 — phone verification by OTP (universal MVP code).

Source: 4.0_Backlog_Producto.json → US-02 acceptance_criteria_gherkin.
"""

import pytest
from django.conf import settings
from rest_framework import status

VERIFY_URL = "/api/auth/verify-otp/"


@pytest.mark.django_db
class TestVerifyOtp:
    """US-02: the universal OTP activates a pending account."""

    def test_verify_with_valid_universal_code_activates_account(
        self, api_client, user_factory
    ) -> None:
        """Flujo principal - Verificación con OTP válido activa la cuenta."""
        account = user_factory(is_phone_verified=False)
        payload = {"phone": account.phone, "code": settings.OTP_UNIVERSAL_CODE}

        response = api_client.post(VERIFY_URL, payload)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["is_phone_verified"] is True
        account.refresh_from_db()
        assert account.is_phone_verified is True

    def test_verify_with_wrong_code_returns_400_and_stays_pending(
        self, api_client, user_factory
    ) -> None:
        """Caso alternativo - Código OTP incorrecto."""
        account = user_factory(is_phone_verified=False)
        payload = {"phone": account.phone, "code": "000000"}

        response = api_client.post(VERIFY_URL, payload)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Código de verificación inválido" in str(response.data)
        account.refresh_from_db()
        assert account.is_phone_verified is False

    def test_verify_already_verified_returns_400(
        self, api_client, user_factory
    ) -> None:
        """Caso de borde - Teléfono ya verificado."""
        account = user_factory(is_phone_verified=True)
        payload = {"phone": account.phone, "code": settings.OTP_UNIVERSAL_CODE}

        response = api_client.post(VERIFY_URL, payload)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "El teléfono ya está verificado" in str(response.data)
        account.refresh_from_db()
        assert account.is_phone_verified is True
