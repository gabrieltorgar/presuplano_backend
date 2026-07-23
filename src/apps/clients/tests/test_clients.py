"""RED tests for EPIC-03 — clients (US-07, US-08, US-09).

Source: 4.0_Backlog_Producto.json → US-07/08/09 acceptance_criteria_gherkin.
"""

import pytest
from rest_framework import status

from apps.clients.models import Client
from apps.clients.tests.factories import ClientFactory

CLIENTS_URL = "/api/clients/"


def detail_url(client_id: str) -> str:
    return f"{CLIENTS_URL}{client_id}/"


@pytest.mark.django_db
class TestRegisterClient:
    """US-07: register a client in the account."""

    def test_register_valid_client_returns_201(
        self, authenticated_client, user
    ) -> None:
        """Flujo principal - Alta de cliente válido."""
        payload = {"name": "Constructora Reyes", "phone": "555-1234"}

        response = authenticated_client.post(CLIENTS_URL, payload)

        assert response.status_code == status.HTTP_201_CREATED
        client = Client.objects.get(name="Constructora Reyes")
        assert client.owner == user

    def test_register_with_invalid_email_returns_400(
        self, authenticated_client
    ) -> None:
        """Caso alternativo - Correo con formato inválido."""
        payload = {"name": "Reyes", "email": "correo-invalido"}

        response = authenticated_client.post(CLIENTS_URL, payload)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "El correo no tiene un formato válido" in str(response.data)

    def test_register_with_empty_name_returns_400(self, authenticated_client) -> None:
        """Caso de borde - Nombre vacío."""
        payload = {"name": "", "phone": "555-1234"}

        response = authenticated_client.post(CLIENTS_URL, payload)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "El nombre del cliente es obligatorio" in str(response.data)

    def test_register_without_auth_returns_401(self, api_client) -> None:
        response = api_client.post(CLIENTS_URL, {"name": "X"})
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestUpdateClient:
    """US-08: edit a client's data."""

    def test_update_phone_returns_200(self, authenticated_client, user) -> None:
        """Flujo principal - Actualizar datos del cliente."""
        client = ClientFactory(owner=user, name="Constructora Reyes", phone="555-1234")

        response = authenticated_client.patch(
            detail_url(client.id), {"phone": "555-9999"}
        )

        assert response.status_code == status.HTTP_200_OK
        client.refresh_from_db()
        assert client.phone == "555-9999"

    def test_update_with_empty_name_returns_400(
        self, authenticated_client, user
    ) -> None:
        """Caso alternativo - Nombre borrado al editar."""
        client = ClientFactory(owner=user, name="Constructora Reyes")

        response = authenticated_client.patch(detail_url(client.id), {"name": ""})

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "El nombre del cliente es obligatorio" in str(response.data)
        client.refresh_from_db()
        assert client.name == "Constructora Reyes"


@pytest.mark.django_db
class TestListClients:
    """US-09: list the account's clients (isolated per account)."""

    def test_list_returns_only_own_clients(self, authenticated_client, user) -> None:
        """Flujo principal - Listar clientes de la cuenta."""
        ClientFactory(owner=user, name="Constructora Reyes")

        response = authenticated_client.get(CLIENTS_URL)

        assert response.status_code == status.HTTP_200_OK
        names = {c["name"] for c in response.data}
        assert names == {"Constructora Reyes"}

    def test_list_excludes_other_accounts_clients(
        self, authenticated_client, user, user_factory
    ) -> None:
        """Caso alternativo - Aislamiento entre cuentas."""
        other = user_factory()
        ClientFactory(owner=other, name="Obras del Sur")
        ClientFactory(owner=user, name="Constructora Reyes")

        response = authenticated_client.get(CLIENTS_URL)

        names = {c["name"] for c in response.data}
        assert names == {"Constructora Reyes"}
