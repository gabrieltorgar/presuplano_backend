"""RED tests for US-03 — login with phone and password.

Source: 4.0_Backlog_Producto.json → US-03 acceptance_criteria_gherkin.
"""

import pytest
from rest_framework import status

LOGIN_URL = "/api/auth/login/"


@pytest.mark.django_db
class TestLogin:
    """US-03: an active, verified account logs in and receives tokens."""

    def test_login_with_valid_credentials_returns_200_with_tokens(
        self, api_client, user_factory
    ) -> None:
        """Flujo principal - Acceso con credenciales válidas."""
        account = user_factory(is_phone_verified=True, password="testpass123")
        payload = {"phone": account.phone, "password": "testpass123"}

        response = api_client.post(LOGIN_URL, payload)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["access"]
        assert response.data["refresh"]
        assert response.data["user"]["phone"] == account.phone

    def test_login_with_wrong_password_returns_401(
        self, api_client, user_factory
    ) -> None:
        """Caso alternativo - Contraseña incorrecta."""
        account = user_factory(is_phone_verified=True, password="testpass123")
        payload = {"phone": account.phone, "password": "wrongpass1"}

        response = api_client.post(LOGIN_URL, payload)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Credenciales inválidas" in str(response.data)

    def test_login_with_unverified_phone_returns_403(
        self, api_client, user_factory
    ) -> None:
        """Caso de borde - Cuenta sin teléfono verificado."""
        account = user_factory(is_phone_verified=False, password="testpass123")
        payload = {"phone": account.phone, "password": "testpass123"}

        response = api_client.post(LOGIN_URL, payload)

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "Debes verificar tu teléfono antes de iniciar sesión" in str(
            response.data
        )
