"""RED tests for US-71 — la organización que firma los documentos.

Los documentos salían firmados por «presuplano» y por un teléfono. El
arquitecto necesita que salgan con el nombre de su despacho y su color, así que
la cuenta guarda esa identidad y la API la deja leer y editar.
"""

import pytest
from rest_framework import status

from apps.accounts.models import DEFAULT_ORGANIZATION_COLOR, Organization

ORGANIZATION_URL = "/api/auth/organization/"
ME_URL = "/api/auth/me/"


@pytest.mark.django_db
class TestMyOrganization:
    """US-71: consultar y editar la identidad que llevan los documentos."""

    def test_returns_an_empty_organization_when_never_configured(
        self, authenticated_client, user
    ) -> None:
        """Flujo principal - Una cuenta recién creada ya puede preguntar."""
        assert not Organization.objects.filter(user=user).exists()

        response = authenticated_client.get(ORGANIZATION_URL)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["name"] == ""
        assert response.data["color"] == DEFAULT_ORGANIZATION_COLOR

    def test_saves_the_name_and_the_color(self, authenticated_client, user) -> None:
        """Flujo principal - El despacho pone su nombre y su color."""
        response = authenticated_client.patch(
            ORGANIZATION_URL,
            {"name": "Taller Reyes Arquitectos", "color": "#0F766E"},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["name"] == "Taller Reyes Arquitectos"
        assert response.data["color"] == "#0F766E"
        organization = Organization.objects.get(user=user)
        assert organization.name == "Taller Reyes Arquitectos"
        assert organization.color == "#0F766E"

    def test_the_account_carries_its_organization(
        self, authenticated_client, user
    ) -> None:
        """Flujo principal - Quien lee su cuenta ya lee con qué firma."""
        Organization.objects.create(user=user, name="Estudio Vega", color="#B91C1C")

        response = authenticated_client.get(ME_URL)

        assert response.data["organization"]["name"] == "Estudio Vega"
        assert response.data["organization"]["color"] == "#B91C1C"

    def test_editing_twice_keeps_one_organization(
        self, authenticated_client, user
    ) -> None:
        """Caso de borde - Guardar dos veces no crea dos organizaciones."""
        authenticated_client.patch(ORGANIZATION_URL, {"name": "Uno"}, format="json")
        authenticated_client.patch(ORGANIZATION_URL, {"name": "Dos"}, format="json")

        assert Organization.objects.filter(user=user).count() == 1
        assert Organization.objects.get(user=user).name == "Dos"

    @pytest.mark.parametrize("color", ["rojo", "#12345", "1E56D6", "#1E56D6X"])
    def test_rejects_a_color_that_is_not_a_hex(
        self, authenticated_client, color
    ) -> None:
        """Caso alternativo - El color tiene que servir para pintar el papel."""
        response = authenticated_client.patch(
            ORGANIZATION_URL, {"color": color}, format="json"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "color" in response.data

    def test_normalizes_the_color_to_uppercase(self, authenticated_client) -> None:
        """Caso de borde - El mismo color escrito de dos formas se guarda igual."""
        response = authenticated_client.patch(
            ORGANIZATION_URL, {"color": "#0f766e"}, format="json"
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["color"] == "#0F766E"

    def test_trims_the_name(self, authenticated_client) -> None:
        """Caso de borde - Los espacios de sobra no llegan al documento."""
        response = authenticated_client.patch(
            ORGANIZATION_URL, {"name": "  Taller Reyes  "}, format="json"
        )

        assert response.data["name"] == "Taller Reyes"

    def test_without_a_session_returns_401(self, api_client) -> None:
        """Caso alternativo - Sin sesión no hay organización que mostrar."""
        assert api_client.get(ORGANIZATION_URL).status_code == (
            status.HTTP_401_UNAUTHORIZED
        )
        assert api_client.patch(ORGANIZATION_URL, {"name": "x"}).status_code == (
            status.HTTP_401_UNAUTHORIZED
        )

    def test_one_account_does_not_see_another_organization(
        self, authenticated_client, user_factory
    ) -> None:
        """Caso alternativo - La identidad es de cada cuenta."""
        other = user_factory()
        Organization.objects.create(user=other, name="Ajena", color="#111111")

        response = authenticated_client.get(ORGANIZATION_URL)

        assert response.data["name"] == ""

    def test_registration_leaves_the_organization_ready(self, api_client) -> None:
        """Flujo principal - Registrarse ya crea la organización vacía."""
        response = api_client.post(
            "/api/auth/register/",
            {"phone": "5599887766", "password": "secreta123"},
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        organization = Organization.objects.get(user__phone="5599887766")
        assert organization.name == ""
        assert organization.color == DEFAULT_ORGANIZATION_COLOR
