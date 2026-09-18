"""RED tests for US-69 — los datos de mi cuenta.

La pantalla de perfil necesita algo más que el teléfono que ya guarda la sesión:
desde cuándo existe la cuenta y en qué plan está.
"""

import pytest
from rest_framework import status

from apps.accounts.models import Subscription

ME_URL = "/api/auth/me/"


@pytest.mark.django_db
class TestMyAccount:
    """US-69: consultar los datos de la propia cuenta."""

    def test_returns_the_account_of_whoever_asks(
        self, authenticated_client, user
    ) -> None:
        """Flujo principal - Los datos básicos de mi cuenta."""
        response = authenticated_client.get(ME_URL)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["phone"] == user.phone
        assert response.data["is_phone_verified"] is True
        assert response.data["created_at"] is not None

    def test_includes_the_subscription(self, authenticated_client, user) -> None:
        """Flujo principal - El plan y su estado."""
        subscription = Subscription.objects.create(user=user)

        response = authenticated_client.get(ME_URL)

        assert response.data["subscription"]["plan"] == subscription.plan
        assert response.data["subscription"]["status"] == subscription.status

    def test_without_a_session_returns_401(self, api_client) -> None:
        """Caso alternativo - Sin sesión no hay cuenta que mostrar."""
        response = api_client.get(ME_URL)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_an_account_without_subscription_says_so(
        self, authenticated_client, user
    ) -> None:
        """Caso de borde - Una cuenta sin suscripción no rompe la pantalla."""
        assert not Subscription.objects.filter(user=user).exists()

        response = authenticated_client.get(ME_URL)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["subscription"] is None
