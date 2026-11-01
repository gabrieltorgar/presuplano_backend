"""RED tests for US-02 — email verification by OTP.

Each account verifies with the code it was sent; the universal code is only for
the E2E accounts on local/develop (iteracion-26 #15, test_universal_otp.py).

Source: 4.0_Backlog_Producto.json → US-02 acceptance_criteria_gherkin.
"""

import pytest
from rest_framework import status

from apps.accounts.models import OtpCode
from apps.accounts.services import issue_otp

VERIFY_URL = "/api/auth/verify-otp/"


@pytest.mark.django_db
class TestVerifyOtp:
    """US-02: the code that was sent activates a pending account."""

    def test_verify_with_valid_code_activates_account(
        self, api_client, user_factory
    ) -> None:
        """Flujo principal - Verificación con OTP válido activa la cuenta."""
        account = user_factory(is_email_verified=False)
        code = issue_otp(user=account, purpose=OtpCode.Purpose.SIGNUP)
        payload = {"email": account.email, "code": code}

        response = api_client.post(VERIFY_URL, payload)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["is_email_verified"] is True
        account.refresh_from_db()
        assert account.is_email_verified is True

    def test_verify_with_wrong_code_returns_400_and_stays_pending(
        self, api_client, user_factory
    ) -> None:
        """Caso alternativo - Código OTP incorrecto."""
        account = user_factory(is_email_verified=False)
        payload = {"email": account.email, "code": "000000"}

        response = api_client.post(VERIFY_URL, payload)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Código de verificación inválido" in str(response.data)
        account.refresh_from_db()
        assert account.is_email_verified is False

    def test_verify_already_verified_returns_400(
        self, api_client, user_factory
    ) -> None:
        """Caso de borde - Correo ya verificado.

        Responde lo mismo que un código equivocado (iteracion-26 #14 · CRD-04.2):
        «ya está verificado» decía que el correo es de un cliente.
        """
        account = user_factory(is_email_verified=True)
        payload = {"email": account.email, "code": "123456"}

        response = api_client.post(VERIFY_URL, payload)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data == {"code": ["Código de verificación inválido"]}
        account.refresh_from_db()
        assert account.is_email_verified is True
