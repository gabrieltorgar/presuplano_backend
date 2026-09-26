"""Observaciones y días de vigencia de cada cotización.

La vigencia estaba fija en 20 días para todas, y lo que el arquitecto quería
aclarar —qué incluye, qué no, cómo se paga— no tenía dónde escribirse. Las dos
cosas son ahora de cada cotización y salen en su documento.
"""

import pytest
from rest_framework import status

from apps.catalog.models import Tariff
from apps.catalog.tests.factories import TariffFactory
from apps.clients.tests.factories import ClientFactory
from apps.quotes.models import DEFAULT_VALIDITY_DAYS, NOTES_MAX_LENGTH, Quote

QUOTES_URL = "/api/quotes/"


def payload(client, tariff, **extra) -> dict:
    return {
        "client": str(client.id),
        "items": [{"tariff": str(tariff.id), "quantity": "2"}],
        **extra,
    }


@pytest.fixture
def catalog(user):
    return ClientFactory(owner=user), TariffFactory(owner=user, unit_price="100")


@pytest.mark.django_db
class TestObservaciones:
    """US-115: notas de la cotización que salen en su documento."""

    def test_a_quote_keeps_its_notes(self, authenticated_client, catalog) -> None:
        """Flujo principal - Las observaciones se guardan con la cotización."""
        client, tariff = catalog

        response = authenticated_client.post(
            QUOTES_URL,
            payload(client, tariff, notes="  Incluye material.\nNo incluye flete.  "),
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["notes"] == "Incluye material.\nNo incluye flete."

    def test_without_notes_it_has_none(self, authenticated_client, catalog) -> None:
        """Caso alternativo - Sin observaciones, el campo queda vacío."""
        client, tariff = catalog

        response = authenticated_client.post(
            QUOTES_URL, payload(client, tariff), format="json"
        )

        assert response.data["notes"] == ""

    def test_notes_can_be_corrected_and_cleared(
        self, authenticated_client, catalog
    ) -> None:
        """Flujo alternativo - Se corrigen al editar, y se pueden quitar."""
        client, tariff = catalog
        quote_id = authenticated_client.post(
            QUOTES_URL, payload(client, tariff, notes="Anticipo 50 %"), format="json"
        ).data["id"]

        response = authenticated_client.put(
            f"{QUOTES_URL}{quote_id}/", payload(client, tariff, notes=""), format="json"
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["notes"] == ""

    def test_notes_too_long_are_refused(self, authenticated_client, catalog) -> None:
        """Caso de borde - Son observaciones, no un contrato."""
        client, tariff = catalog

        response = authenticated_client.post(
            QUOTES_URL,
            payload(client, tariff, notes="x" * (NOTES_MAX_LENGTH + 1)),
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "no pueden pasar de" in str(response.data["notes"])


@pytest.mark.django_db
class TestVigencia:
    """US-116: los días de vigencia se eligen por cotización."""

    def test_a_new_quote_is_valid_for_20_days(
        self, authenticated_client, catalog
    ) -> None:
        """Flujo principal - Sin decir nada, valen los 20 días de siempre."""
        client, tariff = catalog

        response = authenticated_client.post(
            QUOTES_URL, payload(client, tariff), format="json"
        )

        assert response.data["validity_days"] == DEFAULT_VALIDITY_DAYS == 20

    def test_the_validity_can_be_chosen(self, authenticated_client, catalog) -> None:
        """Flujo principal - Una cotización puede valer 45 días."""
        client, tariff = catalog

        response = authenticated_client.post(
            QUOTES_URL, payload(client, tariff, validity_days=45), format="json"
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["validity_days"] == 45

    @pytest.mark.parametrize(
        ("days", "message"),
        [(0, "al menos 1 día"), (366, "no puede pasar de 365"), ("x", "número")],
    )
    def test_an_impossible_validity_is_refused(
        self, authenticated_client, catalog, days, message
    ) -> None:
        """Caso de borde - Ni cero días ni más de un año."""
        client, tariff = catalog

        response = authenticated_client.post(
            QUOTES_URL, payload(client, tariff, validity_days=days), format="json"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert message in str(response.data["validity_days"])

    def test_a_screen_that_does_not_send_them_keeps_them(
        self, authenticated_client, catalog
    ) -> None:
        """Caso alternativo - Una pantalla vieja no borra lo que no conoce."""
        client, tariff = catalog
        quote_id = authenticated_client.post(
            QUOTES_URL,
            payload(client, tariff, notes="Anticipo 50 %", validity_days=30),
            format="json",
        ).data["id"]

        authenticated_client.put(
            f"{QUOTES_URL}{quote_id}/", payload(client, tariff), format="json"
        )

        quote = Quote.objects.get(pk=quote_id)
        assert quote.notes == "Anticipo 50 %"
        assert quote.validity_days == 30


@pytest.mark.django_db
def test_the_single_unit_reads_as_a_lot() -> None:
    """US-117: «Unidad» se lee «Por lote (único)»; el valor guardado no cambia."""
    assert Tariff.UnitType.UNIT.value == "unit"
    assert Tariff.UnitType.UNIT.label == "Por lote (único)"
