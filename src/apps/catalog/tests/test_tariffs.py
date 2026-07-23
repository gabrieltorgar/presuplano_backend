"""RED tests for EPIC-02 — tariff catalog (US-04, US-05, US-06).

Source: 4.0_Backlog_Producto.json → US-04/05/06 acceptance_criteria_gherkin.
"""

from decimal import Decimal

import pytest
from rest_framework import status

from apps.catalog.models import Tariff
from apps.catalog.tests.factories import TariffFactory

TARIFFS_URL = "/api/tariffs/"


def detail_url(tariff_id: str) -> str:
    return f"{TARIFFS_URL}{tariff_id}/"


@pytest.mark.django_db
class TestRegisterTariff:
    """US-04: register a tariff in the account's catalog."""

    def test_register_valid_tariff_returns_201(
        self, authenticated_client, user
    ) -> None:
        """Flujo principal - Alta de tarifa válida."""
        payload = {
            "name": "Muro de tablaroca",
            "unit_type": Tariff.UnitType.SQUARE_METER,
            "unit_price": "350.00",
        }

        response = authenticated_client.post(TARIFFS_URL, payload)

        assert response.status_code == status.HTTP_201_CREATED
        tariff = Tariff.objects.get(name="Muro de tablaroca")
        assert tariff.owner == user
        assert tariff.unit_price == Decimal("350.00")

    def test_register_with_zero_price_returns_400(self, authenticated_client) -> None:
        """Caso alternativo - Precio no válido."""
        payload = {
            "name": "Muro",
            "unit_type": Tariff.UnitType.SQUARE_METER,
            "unit_price": "0",
        }

        response = authenticated_client.post(TARIFFS_URL, payload)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "El precio debe ser mayor a 0" in str(response.data)

    def test_register_with_empty_name_returns_400(self, authenticated_client) -> None:
        """Caso de borde - Nombre vacío."""
        payload = {
            "name": "",
            "unit_type": Tariff.UnitType.SQUARE_METER,
            "unit_price": "350",
        }

        response = authenticated_client.post(TARIFFS_URL, payload)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "El nombre es obligatorio" in str(response.data)

    def test_register_without_auth_returns_401(self, api_client) -> None:
        payload = {"name": "X", "unit_type": "square_meter", "unit_price": "10"}
        response = api_client.post(TARIFFS_URL, payload)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestUpdateTariff:
    """US-05: edit a tariff's price without altering issued quotes."""

    def test_update_price_returns_200(self, authenticated_client, user) -> None:
        """Flujo principal - Actualizar precio de una tarifa."""
        tariff = TariffFactory(owner=user, name="Muro de tablaroca", unit_price="350")

        response = authenticated_client.patch(
            detail_url(tariff.id), {"unit_price": "400"}
        )

        assert response.status_code == status.HTTP_200_OK
        tariff.refresh_from_db()
        assert tariff.unit_price == Decimal("400.00")

    def test_update_with_non_numeric_price_returns_400(
        self, authenticated_client, user
    ) -> None:
        """Caso alternativo - Precio no numérico."""
        tariff = TariffFactory(owner=user, unit_price="350")

        response = authenticated_client.patch(
            detail_url(tariff.id), {"unit_price": "abc"}
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "El precio debe ser un número mayor a 0" in str(response.data)
        tariff.refresh_from_db()
        assert tariff.unit_price == Decimal("350.00")


@pytest.mark.django_db
class TestListTariffs:
    """US-06: list the account's tariffs (isolated per account)."""

    def test_list_returns_only_own_tariffs(self, authenticated_client, user) -> None:
        """Flujo principal - Listar tarifas de la cuenta."""
        TariffFactory(owner=user, name="Muro de tablaroca")
        TariffFactory(owner=user, name="Zócalo")

        response = authenticated_client.get(TARIFFS_URL)

        assert response.status_code == status.HTTP_200_OK
        names = {t["name"] for t in response.data}
        assert names == {"Muro de tablaroca", "Zócalo"}

    def test_list_excludes_other_accounts_tariffs(
        self, authenticated_client, user, user_factory
    ) -> None:
        """Caso alternativo - Aislamiento entre cuentas."""
        other = user_factory()
        TariffFactory(owner=other, name="Piso porcelanato")
        TariffFactory(owner=user, name="Muro de tablaroca")

        response = authenticated_client.get(TARIFFS_URL)

        names = {t["name"] for t in response.data}
        assert names == {"Muro de tablaroca"}
        assert "Piso porcelanato" not in names
