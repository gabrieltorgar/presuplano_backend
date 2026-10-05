"""RED tests for US-01 — account registration (email + password).

Source: 4.0_Backlog_Producto.json → US-01 acceptance_criteria_gherkin.
"""

import pytest
from rest_framework import status

from apps.accounts.models import Organization, Subscription, User
from apps.legal.tests.consent import accepted

REGISTER_URL = "/api/auth/register/"


@pytest.mark.django_db
class TestRegistration:
    """US-01: registering a valid account creates the user and a subscription."""

    def test_register_with_valid_data_creates_pending_account_and_subscription(
        self, api_client
    ) -> None:
        """Flujo principal - Registro crea cuenta, suscripción y membrete."""
        payload = {"email": "ana@estudio.mx", "password": "secret123", **accepted()}

        response = api_client.post(REGISTER_URL, payload)

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["email"] == "ana@estudio.mx"
        assert response.data["is_email_verified"] is False

        user = User.objects.get(email="ana@estudio.mx")
        assert user.is_email_verified is False
        assert user.check_password("secret123") is True

        subscription = Subscription.objects.get(user=user)
        assert subscription.status == Subscription.Status.ACTIVE
        assert subscription.plan == Subscription.Plan.INITIAL
        assert Organization.objects.filter(user=user).exists()

    def test_register_with_existing_email_returns_400(self, api_client, user) -> None:
        """Caso alternativo - Correo ya registrado."""
        payload = {"email": user.email, "password": "secret123", **accepted()}

        response = api_client.post(REGISTER_URL, payload)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Ese correo ya está registrado" in str(response.data)
        assert User.objects.filter(email=user.email).count() == 1

    def test_register_with_an_invalid_email_returns_400(self, api_client) -> None:
        """Caso alternativo - Lo escrito no es un correo."""
        payload = {"email": "5512345678", "password": "secret123", **accepted()}

        response = api_client.post(REGISTER_URL, payload)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Escribe un correo válido" in str(response.data)
        assert User.objects.count() == 0

    def test_register_with_short_password_returns_400(self, api_client) -> None:
        """Caso de borde - Contraseña demasiado corta."""
        payload = {"email": "corta@estudio.mx", "password": "short", **accepted()}

        response = api_client.post(REGISTER_URL, payload)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "La contraseña debe tener al menos 8 caracteres" in str(response.data)
        assert User.objects.filter(email="corta@estudio.mx").exists() is False
