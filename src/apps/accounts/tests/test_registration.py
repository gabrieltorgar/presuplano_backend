"""RED tests for US-01 — account registration (phone + password).

Source: 4.0_Backlog_Producto.json → US-01 acceptance_criteria_gherkin.
"""

import pytest
from rest_framework import status

from apps.accounts.models import Subscription, User

REGISTER_URL = "/api/auth/register/"


@pytest.mark.django_db
class TestRegistration:
    """US-01: registering a valid account creates the user and a subscription."""

    def test_register_with_valid_data_creates_pending_account_and_subscription(
        self, api_client
    ) -> None:
        """Flujo principal - Registro crea cuenta y suscripción."""
        payload = {"phone": "5512345678", "password": "secret123"}

        response = api_client.post(REGISTER_URL, payload)

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["phone"] == "5512345678"
        assert response.data["is_phone_verified"] is False

        user = User.objects.get(phone="5512345678")
        assert user.is_phone_verified is False
        assert user.check_password("secret123") is True

        subscription = Subscription.objects.get(user=user)
        assert subscription.status == Subscription.Status.ACTIVE
        assert subscription.plan == Subscription.Plan.INITIAL

    def test_register_with_existing_phone_returns_400(self, api_client, user) -> None:
        """Caso alternativo - Teléfono ya registrado."""
        payload = {"phone": user.phone, "password": "secret123"}

        response = api_client.post(REGISTER_URL, payload)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Ese teléfono ya está registrado" in str(response.data)
        assert User.objects.filter(phone=user.phone).count() == 1

    def test_register_with_short_password_returns_400(self, api_client) -> None:
        """Caso de borde - Contraseña demasiado corta."""
        payload = {"phone": "5599999999", "password": "short"}

        response = api_client.post(REGISTER_URL, payload)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "La contraseña debe tener al menos 8 caracteres" in str(response.data)
        assert User.objects.filter(phone="5599999999").exists() is False
