"""US-98: los pagos de una persona del personal, por páginas (iteracion-28 #18).

``GET /api/worker-payments/summary/?worker=`` devolvía sus cifras y, con ellas,
la lista entera de pagos de esa persona, que la pantalla cortaba de cinco en
cinco. Ahora el resumen trae solo sus cifras y los pagos se piden por páginas a
``GET /api/worker-payments/?worker=`` (y ``&project=`` cuando el panel es de
una obra).

Fuente: backlog 5.6 → US-98 list_spec y su cambio «iteracion-28».
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.staff.models import WorkerPayment
from apps.staff.tests.factories import WorkerFactory
from apps.staff.tests.test_staff import WORKER_PAYMENTS_URL, make_project
from apps.staff.views import WorkerPaymentViewSet

URL = WORKER_PAYMENTS_URL
SUMMARY_URL = f"{WORKER_PAYMENTS_URL}summary/"

#: Lo que muestra cada pago hecho (monto, fecha y nota) y lo que piden su
#: comprobante (folio, a quién, de qué obra y el método).
LIST_ROW_FIELDS = {
    "id",
    "folio",
    "worker",
    "worker_name",
    "project",
    "amount",
    "method",
    "date",
    "note",
    "created_at",
}
#: Las cifras del panel de la persona: repartido, ejecutado, pagado, saldo y
#: anticipo, con su nombre.
SUMMARY_FIELDS = {
    "worker_name",
    "committed_value",
    "accrued_value",
    "total_paid",
    "balance",
    "advance_balance",
}


def ids(body) -> set[str]:
    return {row["id"] for row in body["results"]}


def in_order(body) -> list[str]:
    return [row["id"] for row in body["results"]]


def paid(user, worker, n: int, *, start=date(2026, 1, 1), project=None, note=""):
    """``n`` pagos de 100 a ``worker``, uno por día desde ``start``."""
    return WorkerPayment.objects.bulk_create(
        WorkerPayment(
            owner=user,
            worker=worker,
            project=project,
            amount=Decimal("100"),
            date=start + timedelta(days=k),
            note=note,
        )
        for k in range(n)
    )


@pytest.mark.django_db
class TestTheSummaryBringsOnlyItsFigures:
    """US-98: el resumen de una persona, sin la lista de pagos."""

    def test_the_summary_has_its_figures_and_no_payments(
        self, authenticated_client, user
    ) -> None:
        """Cambio iteracion-28 - El resumen trae solo sus cifras."""
        juan = WorkerFactory(owner=user, name="Juan Pérez")
        paid(user, juan, 3)

        response = authenticated_client.get(SUMMARY_URL, {"worker": str(juan.id)})

        assert response.status_code == 200
        assert set(response.data) == SUMMARY_FIELDS
        assert response.data["worker_name"] == "Juan Pérez"
        assert Decimal(response.data["total_paid"]) == Decimal("300.00")
        assert Decimal(response.data["advance_balance"]) == Decimal("300.00")

    def test_the_summary_of_a_project_counts_only_that_project(
        self, authenticated_client, user
    ) -> None:
        project, _, _, _ = make_project(user)
        juan = WorkerFactory(owner=user, name="Juan Pérez")
        paid(user, juan, 2, project=project)
        paid(user, juan, 1)

        response = authenticated_client.get(
            SUMMARY_URL, {"worker": str(juan.id), "project": str(project.id)}
        )

        assert set(response.data) == SUMMARY_FIELDS
        assert Decimal(response.data["total_paid"]) == Decimal("200.00")


@pytest.mark.django_db
class TestWorkerPaymentList:
    """US-98 · set listado"""

    def test_view_declares_explicit_list_contract(self) -> None:
        assert WorkerPaymentViewSet.pagination_class is not None
        assert WorkerPaymentViewSet.filterset_class is not None
        assert WorkerPaymentViewSet.search_fields
        assert WorkerPaymentViewSet.ordering_fields
        assert WorkerPaymentViewSet.ordering_fields != "__all__"
        assert WorkerPaymentViewSet.ordering[-1].lstrip("-") in {"id", "pk"}

    def test_list_returns_20_per_page_in_drf_shape(
        self, authenticated_client, user
    ) -> None:
        juan = WorkerFactory(owner=user)
        paid(user, juan, 25)

        body = authenticated_client.get(URL, {"worker": str(juan.id)}).json()
        small = authenticated_client.get(
            URL, {"worker": str(juan.id), "page_size": 5}
        ).json()

        assert set(body) == {"count", "next", "previous", "results"}
        assert (body["count"], len(body["results"]), body["previous"]) == (25, 20, None)
        assert "page=2" in body["next"]
        assert len(small["results"]) == 5

    def test_list_caps_page_size_at_max_page_size(
        self, authenticated_client, user
    ) -> None:
        juan = WorkerFactory(owner=user)
        paid(user, juan, 101)

        body = authenticated_client.get(
            URL, {"worker": str(juan.id), "page_size": 1000}
        ).json()

        assert len(body["results"]) == 100

    def test_list_filters_by_worker_and_project(
        self, authenticated_client, user
    ) -> None:
        """Los pagos de esa persona: los de una obra, o también los de la semana."""
        project, _, _, _ = make_project(user)
        juan = WorkerFactory(owner=user, name="Juan")
        luis = WorkerFactory(owner=user, name="Luis")
        [of_the_project] = paid(user, juan, 1, project=project)
        [general] = paid(user, juan, 1)
        paid(user, luis, 1, project=project)

        of_juan = authenticated_client.get(URL, {"worker": str(juan.id)}).json()
        of_juan_here = authenticated_client.get(
            URL, {"worker": str(juan.id), "project": str(project.id)}
        ).json()

        assert ids(of_juan) == {str(of_the_project.id), str(general.id)}
        assert ids(of_juan_here) == {str(of_the_project.id)}

    @pytest.mark.parametrize("field", ["worker", "project"])
    def test_list_with_invalid_filter_value_returns_400_on_the_field(
        self, authenticated_client, field
    ) -> None:
        response = authenticated_client.get(URL, {field: "no-es-un-id"})

        assert response.status_code == 400
        assert field in response.json()

    def test_list_search_matches_each_search_field(
        self, authenticated_client, user
    ) -> None:
        juan = WorkerFactory(owner=user, name="Juan Pérez")
        luis = WorkerFactory(owner=user, name="Luis")
        [of_juan] = paid(user, juan, 1)
        [weekly] = paid(user, luis, 1, note="Semana de aplanados")

        by_name = authenticated_client.get(URL, {"search": "perez"}).json()
        by_note = authenticated_client.get(URL, {"search": "aplanados"}).json()

        assert ids(by_name) == {str(of_juan.id)}
        assert ids(by_note) == {str(weekly.id)}

    def test_list_ordering_follows_whitelist_and_ignores_unknown_fields(
        self, authenticated_client, user
    ) -> None:
        juan = WorkerFactory(owner=user)
        first, second = paid(user, juan, 2)
        WorkerPayment.objects.filter(pk=first.pk).update(amount=Decimal("900"))
        # bulk_create puede darles el mismo instante: el segundo, un minuto después.
        WorkerPayment.objects.filter(pk=second.pk).update(
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

    @pytest.mark.parametrize("params", [{}, {"ordering": "-date"}])
    def test_list_pages_never_repeat_or_skip_rows_with_equal_sort_keys(
        self, authenticated_client, user, params
    ) -> None:
        juan = WorkerFactory(owner=user)
        rows = paid(user, juan, 25)
        WorkerPayment.objects.filter(pk__in=[r.pk for r in rows]).update(
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
        juan = WorkerFactory(owner=user)
        luis = WorkerFactory(owner=user)
        rows = paid(user, juan, 25)
        paid(user, luis, 3, start=date(2027, 1, 1))
        params = {"worker": str(juan.id), "ordering": "-date"}

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
        juan = WorkerFactory(owner=user, name="Juan Pérez")
        paid(user, juan, 1, note="Semana 7")

        [row] = authenticated_client.get(URL).json()["results"]

        assert set(row) == LIST_ROW_FIELDS
        assert (row["worker_name"], row["amount"], row["note"]) == (
            "Juan Pérez",
            "100.00",
            "Semana 7",
        )

    def test_list_never_returns_other_scope_rows_even_when_filters_match(
        self, authenticated_client, user_factory
    ) -> None:
        intruder = user_factory()
        theirs = WorkerFactory(owner=intruder, name="Juan Pérez")
        paid(intruder, theirs, 2)

        body = authenticated_client.get(
            URL, {"worker": str(theirs.id), "search": "perez"}
        ).json()

        assert body["count"] == 0
        assert body["results"] == []

    def test_list_query_count_does_not_grow_with_the_page(
        self, authenticated_client, user, django_assert_max_num_queries
    ) -> None:
        project, _, _, _ = make_project(user)
        juan = WorkerFactory(owner=user)
        paid(user, juan, 1, project=project)
        with CaptureQueriesContext(connection) as single:
            authenticated_client.get(URL, {"worker": str(juan.id)})
        paid(user, juan, 19, start=date(2026, 2, 1), project=project)

        with django_assert_max_num_queries(len(single)):
            body = authenticated_client.get(URL, {"worker": str(juan.id)}).json()

        assert len(body["results"]) == 20
