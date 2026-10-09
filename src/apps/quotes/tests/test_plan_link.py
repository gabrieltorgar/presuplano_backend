"""RED tests for iteracion-5 — la cotización recuerda su plano (US-95, US-133).

Una cotización hecha desde un plano quedaba suelta: al cambiar el plano había
que cotizar de nuevo y la anterior seguía ahí, sin saber de dónde salió. Ahora
la cotización guarda su plano y cuáles de sus partidas vienen de él, y volver a
cotizar actualiza el borrador sin tocar lo que el arquitecto agregó a mano.
"""

from decimal import Decimal

import pytest
from rest_framework import status

from apps.catalog.tests.factories import TariffFactory
from apps.clients.tests.factories import ClientFactory
from apps.planner.models import Plan
from apps.quotes.models import Quote
from apps.quotes.services import create_quote

QUOTES_URL = "/api/quotes/"


def sync_url(quote_id) -> str:
    return f"{QUOTES_URL}{quote_id}/plan-sync/"


@pytest.fixture
def obra(user):
    """Un cliente, tres servicios y un plano de la cuenta."""
    return {
        "client": ClientFactory(owner=user, name="Constructora Reyes"),
        "muro": TariffFactory(owner=user, name="Muro de block", unit_price="350"),
        "piso": TariffFactory(owner=user, name="Piso cerámico", unit_price="420"),
        "limpieza": TariffFactory(
            owner=user, name="Limpieza final", unit_type="unit", unit_price="1500"
        ),
        "plan": Plan.objects.create(owner=user, name="Casa Pérez", document={}),
    }


def payload(obra, **lines):
    """Las partidas que mide el plano: servicio → cantidad."""
    return {
        "client": str(obra["client"].id),
        "plan": str(obra["plan"].id),
        "items": [
            {"tariff": str(obra[name].id), "quantity": str(qty), "from_plan": True}
            for name, qty in lines.items()
        ],
    }


@pytest.mark.django_db
class TestTheQuoteRemembersItsPlan:
    """Cambio iteracion-5 - La cotización recuerda su plano."""

    def test_a_quote_made_from_a_plan_is_linked_to_it(
        self, authenticated_client, obra
    ) -> None:
        response = authenticated_client.post(
            QUOTES_URL, payload(obra, muro="10", piso="20"), format="json"
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["plan"] == obra["plan"].id
        assert response.data["plan_name"] == "Casa Pérez"
        assert [item["from_plan"] for item in response.data["items"]] == [True, True]

    def test_a_quote_made_by_hand_has_no_plan(self, authenticated_client, obra) -> None:
        body = payload(obra, muro="10")
        del body["plan"]
        body["items"][0].pop("from_plan")

        response = authenticated_client.post(QUOTES_URL, body, format="json")

        assert response.data["plan"] is None
        assert response.data["plan_name"] is None
        assert response.data["items"][0]["from_plan"] is False

    def test_another_accounts_plan_is_not_found(
        self, authenticated_client, obra, user_factory
    ) -> None:
        otra = user_factory()
        ajeno = Plan.objects.create(owner=otra, name="Ajeno", document={})
        body = payload(obra, muro="10")
        body["plan"] = str(ajeno.id)

        response = authenticated_client.post(QUOTES_URL, body, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert Quote.objects.count() == 0

    def test_deleting_the_plan_keeps_the_quote_without_the_link(
        self, authenticated_client, obra
    ) -> None:
        response = authenticated_client.post(
            QUOTES_URL, payload(obra, muro="10"), format="json"
        )

        obra["plan"].delete()

        quote = Quote.objects.get(pk=response.data["id"])
        assert quote.plan is None
        assert quote.items.count() == 1

    def test_editing_the_quote_by_hand_keeps_what_came_from_the_plan(
        self, authenticated_client, obra
    ) -> None:
        created = authenticated_client.post(
            QUOTES_URL, payload(obra, muro="10"), format="json"
        ).data
        # La pantalla de la cotización no sabe de planos: manda sus partidas.
        edit = {
            "client": str(obra["client"].id),
            "items": [
                {"tariff": str(obra["muro"].id), "quantity": "10"},
                {"tariff": str(obra["limpieza"].id), "quantity": "1"},
            ],
        }

        response = authenticated_client.put(
            f"{QUOTES_URL}{created['id']}/", edit, format="json"
        )

        assert response.data["plan"] == obra["plan"].id
        assert [(i["name"], i["from_plan"]) for i in response.data["items"]] == [
            ("Muro de block", True),
            ("Limpieza final", False),
        ]


@pytest.mark.django_db
class TestRequotingUpdatesTheDraft:
    """Cambio iteracion-5 - Recotizar actualiza el borrador."""

    def _linked_draft(self, authenticated_client, obra):
        created = authenticated_client.post(
            QUOTES_URL, payload(obra, muro="10", piso="20"), format="json"
        ).data
        quote = Quote.objects.get(pk=created["id"])
        # A mano: una limpieza, y el muro a precio negociado.
        quote.items.create(
            tariff=obra["limpieza"],
            name="Limpieza final",
            unit_type="unit",
            unit_price=Decimal("1500"),
            quantity=Decimal("1"),
        )
        quote.items.filter(tariff=obra["muro"]).update(unit_price=Decimal("300"))
        return quote

    def test_the_plan_lines_take_the_new_quantities(
        self, authenticated_client, obra
    ) -> None:
        quote = self._linked_draft(authenticated_client, obra)

        response = authenticated_client.post(
            sync_url(quote.id),
            {
                k: v
                for k, v in payload(obra, muro="12", piso="25").items()
                if k != "client"
            },
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        lines = {i["name"]: i for i in response.data["items"]}
        assert Decimal(lines["Muro de block"]["quantity"]) == Decimal("12")
        assert Decimal(lines["Piso cerámico"]["quantity"]) == Decimal("25")
        # Lo negociado se queda: cambia cuánto, no a cuánto.
        assert Decimal(lines["Muro de block"]["unit_price"]) == Decimal("300")
        # Lo agregado a mano se conserva.
        assert Decimal(lines["Limpieza final"]["quantity"]) == Decimal("1")
        assert lines["Limpieza final"]["from_plan"] is False
        # Y el total se recalcula: 12 × 300 + 25 × 420 + 1500.
        assert Decimal(response.data["total"]) == Decimal("15600")

    def test_a_line_whose_element_is_gone_leaves_the_quote(
        self, authenticated_client, obra
    ) -> None:
        """Cambio iteracion-5 - Una partida que ya no está."""
        quote = self._linked_draft(authenticated_client, obra)

        response = authenticated_client.post(
            sync_url(quote.id),
            {k: v for k, v in payload(obra, muro="12").items() if k != "client"},
            format="json",
        )

        names = [i["name"] for i in response.data["items"]]
        assert names == ["Muro de block", "Limpieza final"]

    def test_a_new_service_in_the_plan_enters_the_quote(
        self, authenticated_client, obra
    ) -> None:
        created = authenticated_client.post(
            QUOTES_URL, payload(obra, muro="10"), format="json"
        ).data

        response = authenticated_client.post(
            sync_url(created["id"]),
            {
                k: v
                for k, v in payload(obra, muro="10", piso="8").items()
                if k != "client"
            },
            format="json",
        )

        assert [(i["name"], i["from_plan"]) for i in response.data["items"]] == [
            ("Muro de block", True),
            ("Piso cerámico", True),
        ]

    def test_what_is_already_a_project_is_not_touched(
        self, authenticated_client, obra
    ) -> None:
        """Cambio iteracion-5 - Lo que ya es proyecto no se toca."""
        quote = self._linked_draft(authenticated_client, obra)
        Quote.objects.filter(pk=quote.pk).update(status=Quote.Status.IN_PROJECT)

        response = authenticated_client.post(
            sync_url(quote.id),
            {k: v for k, v in payload(obra, muro="99").items() if k != "client"},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert quote.items.get(tariff=obra["muro"]).quantity == Decimal("10")

    def test_another_accounts_quote_is_not_found(
        self, authenticated_client, obra, user_factory
    ) -> None:
        otra = user_factory()
        ajena = create_quote(
            owner=otra,
            client=ClientFactory(owner=otra),
            items_data=[
                {"tariff": TariffFactory(owner=otra), "quantity": Decimal("1")}
            ],
        )

        response = authenticated_client.post(
            sync_url(ajena.id),
            {k: v for k, v in payload(obra, muro="1").items() if k != "client"},
            format="json",
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
