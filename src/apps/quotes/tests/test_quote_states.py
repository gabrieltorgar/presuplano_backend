"""El estado de una cotización y sus campos protegidos (iteracion-26 #20).

Una cotización es borrador hasta que se vuelve proyecto, y ahí se queda: el
estado lo cambia sólo ese paso (``POST /api/projects/``), nunca un PATCH. Lo que
se edita se revisa sobre la fila bloqueada y releída, no sobre la que la
petición leyó antes: si mientras tanto se volvió proyecto, ya no cambia.
"""

from decimal import Decimal

import pytest
from rest_framework import status
from rest_framework.exceptions import ValidationError

from apps.accounts.tests.factories import UserFactory
from apps.planner.models import Plan
from apps.quotes.models import Quote
from apps.quotes.serializers import QuoteSerializer
from apps.quotes.services import (
    QUOTE_TRANSITIONS,
    create_quote,
    sync_quote_with_plan,
    update_quote,
)
from apps.quotes.tests.test_quotes import QUOTES_URL, build_catalog, detail_url
from common.state_machine import REGISTRY


def test_a_quote_ends_as_a_project_and_never_leaves_it() -> None:
    """SEC-03.1 - La tabla de la cotización y su estado final."""
    assert REGISTRY[Quote] is QUOTE_TRANSITIONS
    assert QUOTE_TRANSITIONS.allowed == {
        Quote.Status.DRAFT: frozenset({Quote.Status.IN_PROJECT}),
        Quote.Status.IN_PROJECT: frozenset(),
    }
    assert QUOTE_TRANSITIONS.terminal == {Quote.Status.IN_PROJECT}


def test_the_read_shape_never_writes_the_status() -> None:
    """SEC-03 - También la forma de lectura lo tiene de solo lectura."""
    fields = QuoteSerializer().fields

    assert fields["status"].read_only
    assert fields["total"].read_only


def _draft(user) -> tuple[Quote, dict]:
    client, muro, _zocalo = build_catalog(user)
    quote = create_quote(
        owner=user,
        client=client,
        items_data=[{"tariff": muro, "quantity": Decimal("10")}],
    )
    payload = {
        "client": str(client.id),
        "items": [{"tariff": str(muro.id), "quantity": "12"}],
    }
    return quote, payload


def _already_a_project(quote: Quote) -> None:
    """Otra petición la volvió proyecto después de que ésta la leyó."""
    Quote.objects.filter(pk=quote.pk).update(status=Quote.Status.IN_PROJECT)


@pytest.mark.django_db
class TestProtectedFieldsOfAQuote:
    """SEC-03 · SEC-03.3 - Estado y dueño no se escriben por PATCH ni PUT."""

    @pytest.mark.parametrize("method", ["patch", "put"])
    def test_status_and_owner_sent_by_the_client_are_ignored(
        self, authenticated_client, user, method
    ) -> None:
        quote, payload = _draft(user)
        other = UserFactory()
        forged = {
            **payload,
            "notes": "Sin material",
            "status": Quote.Status.IN_PROJECT,
            "owner": str(other.id),
        }

        response = getattr(authenticated_client, method)(
            detail_url(quote.id), forged, format="json"
        )

        # Control positivo: la edición se procesó y sólo lo protegido se ignoró.
        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == Quote.Status.DRAFT
        quote.refresh_from_db()
        assert quote.notes == "Sin material"
        assert quote.status == Quote.Status.DRAFT
        assert quote.owner_id == user.id


@pytest.mark.django_db
class TestAQuoteInAProjectIsClosed:
    """SEC-03.1 - Revisado sobre la fila bloqueada, no sobre la que se leyó."""

    def test_an_edit_read_before_it_became_a_project_changes_nothing(
        self, user
    ) -> None:
        quote, _payload = _draft(user)
        client = quote.client
        muro = quote.items.get().tariff
        _already_a_project(quote)

        with pytest.raises(ValidationError, match="proyecto"):
            update_quote(
                quote=quote,
                client=client,
                items_data=[{"tariff": muro, "quantity": Decimal("99")}],
            )

        assert quote.items.get().quantity == Decimal("10")

    def test_a_plan_sync_read_before_it_became_a_project_changes_nothing(
        self, user
    ) -> None:
        quote, _payload = _draft(user)
        muro = quote.items.get().tariff
        plan = Plan.objects.create(owner=user, name="Casa", document={})
        _already_a_project(quote)

        with pytest.raises(ValidationError, match="proyecto"):
            sync_quote_with_plan(
                quote=quote,
                plan=plan,
                items_data=[{"tariff": muro, "quantity": Decimal("99")}],
            )

        quote.refresh_from_db()
        assert quote.plan_id is None

    def test_a_quote_in_a_project_is_not_deleted(
        self, authenticated_client, user
    ) -> None:
        quote, _payload = _draft(user)
        _already_a_project(quote)

        response = authenticated_client.delete(detail_url(quote.id))

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "proyecto" in str(response.data)
        assert Quote.objects.filter(pk=quote.pk).exists()

    def test_the_list_still_shows_it(self, authenticated_client, user) -> None:
        """Control: cerrarla no la esconde."""
        quote, _payload = _draft(user)
        _already_a_project(quote)

        response = authenticated_client.get(QUOTES_URL)

        [row] = response.data["results"]
        assert row["id"] == str(quote.id)
        assert row["status"] == Quote.Status.IN_PROJECT
