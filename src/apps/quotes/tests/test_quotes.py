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

    def test_update_a_quote_already_in_a_project_returns_400(
        self, authenticated_client, user
    ) -> None:
        """Caso alternativo - La cotización ya es un proyecto en marcha."""
        quote, client, muro, _zocalo = self._draft(user)
        quote.status = Quote.Status.IN_PROJECT
        quote.save(update_fields=["status"])

        payload = {
            "client": str(client.id),
            "items": [{"tariff": str(muro.id), "quantity": "5"}],
        }
        response = authenticated_client.patch(
            detail_url(quote.id), payload, format="json"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "proyecto" in str(response.data)

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
class TestTheDocumentIsNotAState:
    """US-12: el documento existe desde que existe la cotización."""

    def _quote(self, user):
        client, muro, _zocalo = build_catalog(user)
        quote = create_quote(
            owner=user,
            client=client,
            items_data=[{"tariff": muro, "quantity": Decimal("10")}],
        )
        return quote, client, muro

    def test_a_new_quote_is_a_draft(self, authenticated_client, user) -> None:
        """Flujo principal - Nace en borrador, con su documento ya disponible."""
        client, muro, _zocalo = build_catalog(user)
        payload = {
            "client": str(client.id),
            "items": [{"tariff": str(muro.id), "quantity": "10"}],
        }

        response = authenticated_client.post(QUOTES_URL, payload, format="json")

        assert response.data["status"] == Quote.Status.DRAFT

    def test_it_stays_a_draft_however_many_times_it_is_edited(
        self, authenticated_client, user
    ) -> None:
        """Flujo principal - Editar no cambia el estado; el documento se rehace."""
        quote, client, muro = self._quote(user)
        payload = {
            "client": str(client.id),
            "items": [{"tariff": str(muro.id), "quantity": "12"}],
        }

        for _ in range(2):
            response = authenticated_client.patch(
                detail_url(quote.id), payload, format="json"
            )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == Quote.Status.DRAFT
        assert Decimal(response.data["total"]) == Decimal("4200.00")

    def test_there_is_no_generate_document_endpoint(
        self, authenticated_client, user
    ) -> None:
        """Caso de borde - Generar el documento ya no es una operación."""
        quote, _client, _muro = self._quote(user)

        response = authenticated_client.post(
            f"{detail_url(quote.id)}generate-document/"
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND


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


@pytest.mark.django_db
class TestCustomUnitPrice:
    """US-63: el precio de una partida se puede ajustar sin tocar el servicio."""

    def test_custom_unit_price_overrides_the_catalog_price(
        self, authenticated_client, user
    ) -> None:
        """Flujo principal - Precio ajustado para esta cotización."""
        client, muro, _zocalo = build_catalog(user)
        payload = {
            "client": str(client.id),
            "items": [
                {"tariff": str(muro.id), "quantity": "2", "unit_price": "150"},
            ],
        }

        response = authenticated_client.post(QUOTES_URL, payload, format="json")

        assert response.status_code == status.HTTP_201_CREATED
        assert Decimal(response.data["items"][0]["unit_price"]) == Decimal("150.00")
        assert Decimal(response.data["total"]) == Decimal("300.00")

    def test_the_service_keeps_its_own_price(self, authenticated_client, user) -> None:
        """Caso de borde - El catálogo no se altera al ajustar una partida."""
        client, muro, _zocalo = build_catalog(user)
        payload = {
            "client": str(client.id),
            "items": [
                {"tariff": str(muro.id), "quantity": "1", "unit_price": "150"},
            ],
        }

        authenticated_client.post(QUOTES_URL, payload, format="json")

        muro.refresh_from_db()
        assert muro.unit_price == Decimal("350.00")

    def test_without_unit_price_takes_the_one_from_the_service(
        self, authenticated_client, user
    ) -> None:
        """Caso de borde - Sin precio propio se toma el del servicio."""
        client, muro, _zocalo = build_catalog(user)
        payload = {
            "client": str(client.id),
            "items": [{"tariff": str(muro.id), "quantity": "2"}],
        }

        response = authenticated_client.post(QUOTES_URL, payload, format="json")

        assert Decimal(response.data["items"][0]["unit_price"]) == Decimal("350.00")

    def test_unit_price_of_zero_returns_400(self, authenticated_client, user) -> None:
        """Caso alternativo - Un precio de cero no es un precio."""
        client, muro, _zocalo = build_catalog(user)
        payload = {
            "client": str(client.id),
            "items": [
                {"tariff": str(muro.id), "quantity": "2", "unit_price": "0"},
            ],
        }

        response = authenticated_client.post(QUOTES_URL, payload, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_update_changes_the_custom_price(self, authenticated_client, user) -> None:
        """Flujo principal - Ajustar el precio al editar el borrador."""
        client, muro, _zocalo = build_catalog(user)
        quote = create_quote(
            owner=user,
            client=client,
            items_data=[{"tariff": muro, "quantity": Decimal("2")}],
        )
        payload = {
            "client": str(client.id),
            "items": [
                {"tariff": str(muro.id), "quantity": "2", "unit_price": "75"},
            ],
        }

        response = authenticated_client.patch(
            detail_url(quote.id), payload, format="json"
        )

        assert response.status_code == status.HTTP_200_OK
        assert Decimal(response.data["total"]) == Decimal("150.00")


@pytest.mark.django_db
class TestAgreedTotalSurvives:
    """US-63: el total acordado es el total, aunque no se reparta en centavos."""

    def test_a_total_that_does_not_divide_in_cents_is_respected(
        self, authenticated_client, user
    ) -> None:
        """Flujo principal - 32 000 entre 15 siguen siendo 32 000."""
        client, muro, _zocalo = build_catalog(user)
        payload = {
            "client": str(client.id),
            "items": [
                {
                    "tariff": str(muro.id),
                    "quantity": "15",
                    "unit_price": "2133.333333",
                },
            ],
        }

        response = authenticated_client.post(QUOTES_URL, payload, format="json")

        assert response.status_code == status.HTTP_201_CREATED
        assert Decimal(response.data["items"][0]["subtotal"]) == Decimal("32000.00")
        assert Decimal(response.data["total"]) == Decimal("32000.00")

    def test_the_line_is_charged_in_whole_cents(
        self, authenticated_client, user
    ) -> None:
        """Caso de borde - Lo que se cobra son centavos, no millonésimas."""
        client, muro, _zocalo = build_catalog(user)
        payload = {
            "client": str(client.id),
            "items": [
                {"tariff": str(muro.id), "quantity": "3", "unit_price": "33.333333"},
            ],
        }

        response = authenticated_client.post(QUOTES_URL, payload, format="json")

        # 3 × 33,333333 = 99,999999, que se cobra como 100,00
        assert Decimal(response.data["items"][0]["subtotal"]) == Decimal("100.00")

    def test_a_price_with_cents_keeps_working_as_before(
        self, authenticated_client, user
    ) -> None:
        """Caso de borde - El precio de siempre no cambia de comportamiento."""
        client, muro, _zocalo = build_catalog(user)
        payload = {
            "client": str(client.id),
            "items": [{"tariff": str(muro.id), "quantity": "10"}],
        }

        response = authenticated_client.post(QUOTES_URL, payload, format="json")

        assert Decimal(response.data["total"]) == Decimal("3500.00")
