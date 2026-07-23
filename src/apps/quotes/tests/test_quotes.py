"""RED tests for EPIC-04 — quotes (US-10, US-11, US-12, US-13).

Also validates US-05 edge: editing a tariff does not change issued quotes.
Source: 4.0_Backlog_Producto.json.
"""

from decimal import Decimal

import pytest
from rest_framework import status

from apps.catalog.tests.factories import TariffFactory
from apps.clients.tests.factories import ClientFactory
from apps.quotes.models import Quote
from apps.quotes.services import create_quote

QUOTES_URL = "/api/quotes/"


def detail_url(quote_id: str) -> str:
    return f"{QUOTES_URL}{quote_id}/"


def build_catalog(user):
    """A client and two tariffs owned by ``user``."""
    client = ClientFactory(owner=user, name="Constructora Reyes")
    muro = TariffFactory(owner=user, name="Muro de tablaroca", unit_price="350")
    zocalo = TariffFactory(
        owner=user, name="Zócalo", unit_type="linear_meter", unit_price="80"
    )
    return client, muro, zocalo


@pytest.mark.django_db
class TestCreateQuote:
    """US-10: create a quote with an automatic total."""

    def test_create_computes_total_from_items(self, authenticated_client, user) -> None:
        """Flujo principal - Total calculado a partir de las partidas."""
        client, muro, zocalo = build_catalog(user)
        payload = {
            "client": str(client.id),
            "items": [
                {"tariff": str(muro.id), "quantity": "10"},
                {"tariff": str(zocalo.id), "quantity": "20"},
            ],
        }

        response = authenticated_client.post(QUOTES_URL, payload, format="json")

        assert response.status_code == status.HTTP_201_CREATED
        assert Decimal(response.data["total"]) == Decimal("5100.00")
        subtotals = {Decimal(i["subtotal"]) for i in response.data["items"]}
        assert subtotals == {Decimal("3500.00"), Decimal("1600.00")}

    def test_create_without_items_returns_400(self, authenticated_client, user) -> None:
        """Caso alternativo - Cotización sin partidas."""
        client, _muro, _zocalo = build_catalog(user)
        payload = {"client": str(client.id), "items": []}

        response = authenticated_client.post(QUOTES_URL, payload, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Agrega al menos una partida a la cotización" in str(response.data)

    def test_create_with_zero_quantity_returns_400(
        self, authenticated_client, user
    ) -> None:
        """Caso de borde - Cantidad no válida en una partida."""
        client, muro, _zocalo = build_catalog(user)
        payload = {
            "client": str(client.id),
            "items": [{"tariff": str(muro.id), "quantity": "0"}],
        }

        response = authenticated_client.post(QUOTES_URL, payload, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "La cantidad debe ser mayor a 0" in str(response.data)


@pytest.mark.django_db
class TestUpdateQuote:
    """US-11: edit a draft quote; recalculates total; blocked once documented."""

    def _draft(self, user):
        client, muro, zocalo = build_catalog(user)
        quote = create_quote(
            owner=user,
            client=client,
            items_data=[
                {"tariff": muro, "quantity": Decimal("10")},
                {"tariff": zocalo, "quantity": Decimal("20")},
            ],
        )
        return quote, client, muro, zocalo

    def test_update_quantity_recalculates_total(
        self, authenticated_client, user
    ) -> None:
        """Flujo principal - Recalcular total al cambiar una cantidad."""
        quote, client, muro, zocalo = self._draft(user)
        payload = {
            "client": str(client.id),
            "items": [
                {"tariff": str(muro.id), "quantity": "12"},
                {"tariff": str(zocalo.id), "quantity": "20"},
            ],
        }

        response = authenticated_client.patch(
            detail_url(quote.id), payload, format="json"
        )

        assert response.status_code == status.HTTP_200_OK
        assert Decimal(response.data["total"]) == Decimal("5800.00")

    def test_update_documented_quote_returns_400(
        self, authenticated_client, user
    ) -> None:
        """Caso alternativo - Cotización con documento ya generado."""
        quote, client, muro, _zocalo = self._draft(user)
        quote.status = Quote.Status.DOCUMENT_GENERATED
        quote.save(update_fields=["status"])

        payload = {
            "client": str(client.id),
            "items": [{"tariff": str(muro.id), "quantity": "5"}],
        }
        response = authenticated_client.patch(
            detail_url(quote.id), payload, format="json"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "ya tiene documento generado" in str(response.data)

    def test_remove_item_recalculates_total(self, authenticated_client, user) -> None:
        """Caso de borde - Eliminar una partida recalcula el total."""
        quote, client, muro, _zocalo = self._draft(user)
        payload = {
            "client": str(client.id),
            "items": [{"tariff": str(muro.id), "quantity": "10"}],
        }

        response = authenticated_client.patch(
            detail_url(quote.id), payload, format="json"
        )

        assert response.status_code == status.HTTP_200_OK
        assert Decimal(response.data["total"]) == Decimal("3500.00")


@pytest.mark.django_db
class TestGenerateDocument:
    """US-12: generate the quote document."""

    def test_generate_marks_document_generated(
        self, authenticated_client, user
    ) -> None:
        """Flujo principal - Documento con detalle y total."""
        client, muro, zocalo = build_catalog(user)
        quote = create_quote(
            owner=user,
            client=client,
            items_data=[
                {"tariff": muro, "quantity": Decimal("10")},
                {"tariff": zocalo, "quantity": Decimal("20")},
            ],
        )

        response = authenticated_client.post(
            f"{detail_url(quote.id)}generate-document/"
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == Quote.Status.DOCUMENT_GENERATED
        assert Decimal(response.data["total"]) == Decimal("5100.00")
        assert response.data["client_name"] == "Constructora Reyes"

    def test_generate_without_items_returns_400(
        self, authenticated_client, user
    ) -> None:
        """Caso alternativo - Cotización sin partidas."""
        client, _muro, _zocalo = build_catalog(user)
        quote = Quote.objects.create(owner=user, client=client)

        response = authenticated_client.post(
            f"{detail_url(quote.id)}generate-document/"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "sin partidas" in str(response.data)

    def test_regenerate_does_not_duplicate(self, authenticated_client, user) -> None:
        """Caso de borde - Regenerar no duplica la cotización."""
        client, muro, _zocalo = build_catalog(user)
        quote = create_quote(
            owner=user,
            client=client,
            items_data=[{"tariff": muro, "quantity": Decimal("10")}],
        )
        url = f"{detail_url(quote.id)}generate-document/"

        authenticated_client.post(url)
        response = authenticated_client.post(url)

        assert response.status_code == status.HTTP_200_OK
        assert Quote.objects.filter(owner=user).count() == 1
        assert Decimal(response.data["total"]) == Decimal("3500.00")


@pytest.mark.django_db
class TestListQuotes:
    """US-13: list the account's quotes (isolated)."""

    def test_list_shows_client_total_status(self, authenticated_client, user) -> None:
        """Flujo principal - Listar cotizaciones con su estado."""
        client, muro, _zocalo = build_catalog(user)
        create_quote(
            owner=user,
            client=client,
            items_data=[{"tariff": muro, "quantity": Decimal("10")}],
        )

        response = authenticated_client.get(QUOTES_URL)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        row = response.data[0]
        assert row["client_name"] == "Constructora Reyes"
        assert Decimal(row["total"]) == Decimal("3500.00")
        assert row["status"] == Quote.Status.DRAFT

    def test_list_excludes_other_accounts_quotes(
        self, authenticated_client, user, user_factory
    ) -> None:
        """Caso alternativo - Aislamiento entre cuentas."""
        other = user_factory()
        other_client, other_muro, _ = build_catalog(other)
        create_quote(
            owner=other,
            client=other_client,
            items_data=[{"tariff": other_muro, "quantity": Decimal("1")}],
        )

        response = authenticated_client.get(QUOTES_URL)

        assert response.data == []


@pytest.mark.django_db
class TestQuotePriceSnapshot:
    """US-05 edge: editing a tariff does not change already-issued quotes."""

    def test_tariff_price_change_does_not_affect_existing_quote(
        self, authenticated_client, user
    ) -> None:
        client, muro, _zocalo = build_catalog(user)
        quote = create_quote(
            owner=user,
            client=client,
            items_data=[{"tariff": muro, "quantity": Decimal("10")}],
        )
        # Tariff price rises after quoting.
        muro.unit_price = Decimal("400")
        muro.save(update_fields=["unit_price"])

        response = authenticated_client.get(detail_url(quote.id))

        # Quote keeps the price it was quoted at (350 × 10 = 3500).
        assert Decimal(response.data["total"]) == Decimal("3500.00")
        assert Decimal(response.data["items"][0]["unit_price"]) == Decimal("350.00")
