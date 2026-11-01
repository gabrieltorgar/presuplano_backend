"""US-20 · US-23: los cobros de un proyecto, por páginas (iteracion-28 #17).

``GET /api/payments/summary/?project=`` devolvía sus cifras y, con ellas, la
lista entera de pagos, que la pantalla cortaba de cinco en cinco. Ahora el
resumen trae solo sus cifras y los pagos se piden por páginas a
``GET /api/payments/?project=``; el documento de estado recorre esa misma lista.

Fuente: backlog 5.6 → US-20 list_spec y su cambio «iteracion-28».
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.payments.models import Payment
from apps.payments.services import register_payment
from apps.payments.tests.test_payments import PAYMENTS_URL, make_project_with_advance
from apps.payments.views import PaymentViewSet

URL = PAYMENTS_URL
SUMMARY_URL = f"{PAYMENTS_URL}summary/"

#: Lo que muestra cada cobro (monto, fecha y método) y lo que piden su
#: comprobante (folio) y el registro del pago (proyecto y partida).
LIST_ROW_FIELDS = {
    "id",
    "folio",
    "project",
    "quote_item",
    "amount",
    "method",
    "date",
    "created_at",
}
#: Las cifras de «Cobros» y el nombre del cliente que firman los comprobantes.
SUMMARY_FIELDS = {
    "advanced_value",
    "quoted_value",
    "total_paid",
    "pending_balance",
    "credit_balance",
    "client_name",
}


def ids(body) -> set[str]:
    return {row["id"] for row in body["results"]}


def in_order(body) -> list[str]:
    return [row["id"] for row in body["results"]]


def payments(user, project, n: int, *, start=date(2026, 1, 1), amount="100"):
    """``n`` pagos de ``amount``, uno por día desde ``start``."""
    return Payment.objects.bulk_create(
        Payment(
            owner=user,
            project=project,
            amount=Decimal(amount),
            date=start + timedelta(days=k),
        )
        for k in range(n)
    )


@pytest.mark.django_db
class TestTheSummaryBringsOnlyItsFigures:
    """US-20: el resumen de cobros, sin la lista de pagos."""

    def test_the_summary_has_its_figures_and_no_payments(
        self, authenticated_client, user
    ) -> None:
        """Cambio iteracion-28 - El resumen trae solo sus cifras."""
        project = make_project_with_advance(user)  # cotizado 5100
        payments(user, project, 3)

        response = authenticated_client.get(SUMMARY_URL, {"project": str(project.id)})

        assert response.status_code == 200
        assert set(response.data) == SUMMARY_FIELDS
        assert Decimal(response.data["total_paid"]) == Decimal("300.00")
        assert Decimal(response.data["pending_balance"]) == Decimal("4800.00")


@pytest.mark.django_db
class TestPaymentList:
    """US-20 · set listado"""

    def test_view_declares_explicit_list_contract(self) -> None:
        assert PaymentViewSet.pagination_class is not None
        assert PaymentViewSet.filterset_class is not None
        # Se piden los de un proyecto, no se buscan: vacía y escrita.
        assert PaymentViewSet.search_fields == ()
        assert PaymentViewSet.ordering_fields
        assert PaymentViewSet.ordering_fields != "__all__"
        assert PaymentViewSet.ordering[-1].lstrip("-") in {"id", "pk"}

    def test_list_returns_20_per_page_in_drf_shape(
        self, authenticated_client, user
    ) -> None:
        project = make_project_with_advance(user)
        payments(user, project, 25)

        body = authenticated_client.get(URL, {"project": str(project.id)}).json()
        small = authenticated_client.get(
            URL, {"project": str(project.id), "page_size": 5}
        ).json()

        assert set(body) == {"count", "next", "previous", "results"}
        assert (body["count"], len(body["results"]), body["previous"]) == (25, 20, None)
        assert "page=2" in body["next"]
        assert len(small["results"]) == 5

    def test_list_caps_page_size_at_max_page_size(
        self, authenticated_client, user
    ) -> None:
        project = make_project_with_advance(user)
        payments(user, project, 101)

        body = authenticated_client.get(
            URL, {"project": str(project.id), "page_size": 1000}
        ).json()

        assert len(body["results"]) == 100

    def test_list_filters_by_project(self, authenticated_client, user) -> None:
        project = make_project_with_advance(user)
        other = make_project_with_advance(user)
        mine = payments(user, project, 2)
        payments(user, other, 1)

        body = authenticated_client.get(URL, {"project": str(project.id)}).json()

        assert ids(body) == {str(p.id) for p in mine}
        assert body["count"] == 2

    def test_list_with_invalid_filter_value_returns_400_on_the_field(
        self, authenticated_client
    ) -> None:
        response = authenticated_client.get(URL, {"project": "no-es-un-id"})

        assert response.status_code == 400
        assert "project" in response.json()

    def test_list_ignores_search_because_it_declares_none(
        self, authenticated_client, user
    ) -> None:
        project = make_project_with_advance(user)
        payments(user, project, 2)

        body = authenticated_client.get(
            URL, {"project": str(project.id), "search": "zzz"}
        ).json()

        assert body["count"] == 2

    def test_list_ordering_follows_whitelist_and_ignores_unknown_fields(
        self, authenticated_client, user
    ) -> None:
        project = make_project_with_advance(user)
        first, second = payments(user, project, 2)
        Payment.objects.filter(pk=first.pk).update(amount=Decimal("900"))
        # bulk_create puede darles el mismo instante: el segundo, un minuto después.
        Payment.objects.filter(pk=second.pk).update(
            created_at=first.created_at + timedelta(minutes=1)
        )

        def order(ordering):
            body = authenticated_client.get(URL, {"ordering": ordering}).json()
            return in_order(body)

        assert order("date") == [str(first.id), str(second.id)]
        assert order("-date") == [str(second.id), str(first.id)]
        assert order("amount") == [str(second.id), str(first.id)]
        assert order("-amount") == [str(first.id), str(second.id)]
        assert order("created_at") == [str(first.id), str(second.id)]
        assert order("-created_at") == [str(second.id), str(first.id)]
        assert order("owner__password") == order("date")

    def test_by_default_in_the_order_they_were_received(
        self, authenticated_client, user
    ) -> None:
        """Flujo principal - Estado de cobros: los pagos por fecha, como hasta hoy."""
        project = make_project_with_advance(user)
        later = payments(user, project, 1, start=date(2026, 3, 1))
        earlier = payments(user, project, 1, start=date(2026, 2, 1))

        body = authenticated_client.get(URL, {"project": str(project.id)}).json()

        assert in_order(body) == [str(earlier[0].id), str(later[0].id)]

    @pytest.mark.parametrize("params", [{}, {"ordering": "-date"}])
    def test_list_pages_never_repeat_or_skip_rows_with_equal_sort_keys(
        self, authenticated_client, user, params
    ) -> None:
        project = make_project_with_advance(user)
        rows = payments(user, project, 25)
        Payment.objects.filter(pk__in=[r.pk for r in rows]).update(
            date=date(2026, 1, 1), created_at=rows[0].created_at
        )

        seen = [
            row["id"]
            for page in (1, 2, 3)
            for row in authenticated_client.get(
                URL, {**params, "page": page, "page_size": 10}
            ).json()["results"]
        ]

        assert len(seen) == len(set(seen)) == 25

    def test_list_sorts_and_counts_every_row_not_the_page(
        self, authenticated_client, user
    ) -> None:
        project = make_project_with_advance(user)
        other = make_project_with_advance(user)
        rows = payments(user, project, 25)
        payments(user, other, 3, start=date(2027, 1, 1))
        params = {"project": str(project.id), "ordering": "-date"}

        pages = [
            authenticated_client.get(URL, {**params, "page": page}).json()
            for page in (1, 2)
        ]

        assert [row["id"] for p in pages for row in p["results"]] == [
            str(r.id) for r in reversed(rows)
        ]
        assert (pages[0]["count"], len(pages[0]["results"])) == (25, 20)

    def test_list_rows_carry_only_the_list_columns(
        self, authenticated_client, user
    ) -> None:
        project = make_project_with_advance(user)
        register_payment(
            owner=user, project=project, amount=Decimal("1000"), date=date(2026, 1, 15)
        )

        [row] = authenticated_client.get(URL).json()["results"]

        assert set(row) == LIST_ROW_FIELDS
        assert (row["amount"], row["date"], row["method"]) == (
            "1000.00",
            "2026-01-15",
            "cash",
        )

    def test_list_never_returns_other_scope_rows_even_when_filters_match(
        self, authenticated_client, user_factory
    ) -> None:
        intruder = user_factory()
        their_project = make_project_with_advance(intruder)
        payments(intruder, their_project, 2)

        body = authenticated_client.get(URL, {"project": str(their_project.id)}).json()

        assert body["count"] == 0
        assert body["results"] == []

    def test_list_query_count_does_not_grow_with_the_page(
        self, authenticated_client, user, django_assert_max_num_queries
    ) -> None:
        project = make_project_with_advance(user)
        payments(user, project, 1)
        with CaptureQueriesContext(connection) as single:
            authenticated_client.get(URL, {"project": str(project.id)})
        payments(user, project, 19, start=date(2026, 2, 1))

        with django_assert_max_num_queries(len(single)):
            body = authenticated_client.get(URL, {"project": str(project.id)}).json()

        assert len(body["results"]) == 20


@pytest.mark.django_db
class TestTheStatusDocumentWalksThePayments:
    """US-23: el documento de estado trae todos los pagos, página por página."""

    def test_every_payment_with_date_amount_and_method(
        self, authenticated_client, user
    ) -> None:
        """Caso de borde - Más pagos de los que caben en una página."""
        project = make_project_with_advance(user)
        rows = payments(user, project, 45, amount="10")

        walked, url = [], f"{URL}?project={project.id}&page_size=20"
        while url:
            page = authenticated_client.get(url).json()
            walked += page["results"]
            url = page["next"]

        assert [row["id"] for row in walked] == [str(r.id) for r in rows]
        assert sum(Decimal(row["amount"]) for row in walked) == Decimal("450.00")
        assert {row["method"] for row in walked} == {"cash"}
