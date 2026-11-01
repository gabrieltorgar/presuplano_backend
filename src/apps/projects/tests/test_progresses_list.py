"""US-113 · US-23: los avances de un proyecto, por páginas (iteracion-28 #16).

Antes llegaban todos, cada uno con todas sus fotos, dentro de
``GET /api/projects/{id}/``, y la pantalla mostraba cinco: el detalle crecía con
la obra. Ahora la pantalla pide su página a ``GET /api/progresses/?project=``
(el más reciente arriba, con ``?ordering=-date,-created_at``) y el documento de
estado recorre esa misma lista página por página, en el orden en que se
trabajó.

Fuente: backlog 5.6 → US-113 list_spec y su cambio «iteracion-28».
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from apps.projects.models import Evidence, Progress
from apps.projects.tests.test_projects import PROJECTS_URL, make_project
from apps.projects.views import ProgressViewSet
from apps.staff.tests.factories import WorkerFactory

URL = "/api/progresses/"

#: Lo que muestra cada fila de «Avances registrados» (servicio, cantidad,
#: unidad, fecha, quién y lo que vale, con sus fotos), lo que piden corregirla
#: (la partida y quién) y el precio de mano de obra que la fila ya publicaba.
LIST_ROW_FIELDS = {
    "id",
    "quote_item",
    "item",
    "unit_type",
    "quantity",
    "date",
    "earned_value",
    "worker",
    "worker_name",
    "labor_unit_price",
    "evidence",
}


def ids(body) -> set[str]:
    return {row["id"] for row in body["results"]}


def in_order(body) -> list[str]:
    return [row["id"] for row in body["results"]]


def advances(project, item, n: int, *, start=date(2026, 1, 1), worker=None):
    """``n`` avances de una unidad, uno por día desde ``start``."""
    return Progress.objects.bulk_create(
        Progress(
            project=project,
            quote_item=item,
            quantity=Decimal("1"),
            date=start + timedelta(days=k),
            worker=worker,
        )
        for k in range(n)
    )


@pytest.mark.django_db
class TestProgressList:
    """US-113 · set listado"""

    def test_view_declares_explicit_list_contract(self) -> None:
        assert ProgressViewSet.pagination_class is not None
        assert ProgressViewSet.filterset_class is not None
        assert ProgressViewSet.search_fields
        assert ProgressViewSet.ordering_fields
        assert ProgressViewSet.ordering_fields != "__all__"
        assert ProgressViewSet.ordering[-1].lstrip("-") in {"id", "pk"}

    def test_list_returns_20_per_page_in_drf_shape(
        self, authenticated_client, user
    ) -> None:
        project, muro, _ = make_project(user)
        advances(project, muro, 25)

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
        project, muro, _ = make_project(user)
        advances(project, muro, 101)

        body = authenticated_client.get(
            URL, {"project": str(project.id), "page_size": 1000}
        ).json()

        assert len(body["results"]) == 100

    def test_list_filters_by_project_item_and_worker(
        self, authenticated_client, user
    ) -> None:
        project, muro, zocalo = make_project(user)
        other, other_muro, _ = make_project(user)
        juan = WorkerFactory(owner=user, name="Juan Pérez")
        [of_juan] = advances(project, muro, 1, worker=juan)
        [of_zocalo] = advances(project, zocalo, 1)
        advances(other, other_muro, 1)

        by_project = authenticated_client.get(URL, {"project": str(project.id)})
        by_item = authenticated_client.get(URL, {"quote_item": str(zocalo.id)})
        by_worker = authenticated_client.get(URL, {"worker": str(juan.id)})

        assert ids(by_project.json()) == {str(of_juan.id), str(of_zocalo.id)}
        assert ids(by_item.json()) == {str(of_zocalo.id)}
        assert ids(by_worker.json()) == {str(of_juan.id)}

    @pytest.mark.parametrize("field", ["project", "quote_item", "worker"])
    def test_list_with_invalid_filter_value_returns_400_on_the_field(
        self, authenticated_client, field
    ) -> None:
        response = authenticated_client.get(URL, {field: "no-es-un-id"})

        assert response.status_code == 400
        assert field in response.json()

    def test_list_search_matches_each_search_field(
        self, authenticated_client, user
    ) -> None:
        project, muro, zocalo = make_project(user)
        juan = WorkerFactory(owner=user, name="Juan Pérez")
        [of_juan] = advances(project, muro, 1, worker=juan)
        [of_zocalo] = advances(project, zocalo, 1)

        by_service = authenticated_client.get(URL, {"search": "zocalo"})
        by_worker = authenticated_client.get(URL, {"search": "perez"})

        assert ids(by_service.json()) == {str(of_zocalo.id)}
        assert ids(by_worker.json()) == {str(of_juan.id)}

    def test_list_ordering_follows_whitelist_and_ignores_unknown_fields(
        self, authenticated_client, user
    ) -> None:
        project, muro, _ = make_project(user)
        first, second = advances(project, muro, 2)
        Progress.objects.filter(pk=first.pk).update(quantity=Decimal("3"))
        # bulk_create puede darles el mismo instante: el segundo, un minuto después.
        Progress.objects.filter(pk=second.pk).update(
            created_at=first.created_at + timedelta(minutes=1)
        )

        def order(ordering):
            body = authenticated_client.get(URL, {"ordering": ordering}).json()
            return in_order(body)

        assert order("date") == [str(first.id), str(second.id)]
        assert order("-date") == [str(second.id), str(first.id)]
        assert order("quantity") == [str(second.id), str(first.id)]
        assert order("-quantity") == [str(first.id), str(second.id)]
        assert order("created_at") == [str(first.id), str(second.id)]
        assert order("-created_at") == [str(second.id), str(first.id)]
        assert order("project__owner__password") == order("date")

    def test_the_screen_gets_the_most_recent_first(
        self, authenticated_client, user
    ) -> None:
        """Flujo principal - Ver los avances: el más reciente arriba."""
        project, muro, _ = make_project(user)
        older, newer = advances(project, muro, 2)

        body = authenticated_client.get(
            URL, {"project": str(project.id), "ordering": "-date,-created_at"}
        ).json()

        assert in_order(body) == [str(newer.id), str(older.id)]

    @pytest.mark.parametrize("params", [{}, {"ordering": "-date,-created_at"}])
    def test_list_pages_never_repeat_or_skip_rows_with_equal_sort_keys(
        self, authenticated_client, user, params
    ) -> None:
        project, muro, _ = make_project(user)
        rows = advances(project, muro, 25)
        Progress.objects.filter(pk__in=[r.pk for r in rows]).update(
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
        project, muro, _ = make_project(user)
        other, other_muro, _ = make_project(user)
        rows = advances(project, muro, 25)
        advances(other, other_muro, 3, start=date(2027, 1, 1))
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
        project, muro, _ = make_project(user)
        advances(project, muro, 1)

        [row] = authenticated_client.get(URL).json()["results"]

        assert set(row) == LIST_ROW_FIELDS

    def test_list_never_returns_other_scope_rows_even_when_filters_match(
        self, authenticated_client, user_factory
    ) -> None:
        intruder_project, muro, _ = make_project(user_factory())
        advances(intruder_project, muro, 2)

        body = authenticated_client.get(
            URL, {"project": str(intruder_project.id), "search": "muro"}
        ).json()

        assert body["count"] == 0
        assert body["results"] == []

    def test_list_query_count_does_not_grow_with_the_page(
        self, authenticated_client, user, django_assert_max_num_queries
    ) -> None:
        project, muro, _ = make_project(user)
        juan = WorkerFactory(owner=user, name="Juan Pérez")
        [one] = advances(project, muro, 1, worker=juan)
        Evidence.objects.create(progress=one, image="evidence/una.png")
        with CaptureQueriesContext(connection) as single:
            authenticated_client.get(URL, {"project": str(project.id)})
        for row in advances(project, muro, 19, start=date(2026, 2, 1), worker=juan):
            Evidence.objects.create(progress=row, image="evidence/a.png")
            Evidence.objects.create(progress=row, image="evidence/b.png")

        with django_assert_max_num_queries(len(single)):
            body = authenticated_client.get(URL, {"project": str(project.id)}).json()

        assert len(body["results"]) == 20


@pytest.mark.django_db
class TestEachRowShowsWhatTheScreenShows:
    """US-113 · US-16: cada fila de la lista trae lo que la pantalla pinta."""

    def test_a_row_without_a_worker_is_work_of_the_house(
        self, authenticated_client, user
    ) -> None:
        project, muro, _ = make_project(user)
        advances(project, muro, 1)

        [row] = authenticated_client.get(URL).json()["results"]

        assert row["worker"] is None
        assert row["worker_name"] == ""
        assert row["evidence"] == []


@pytest.mark.django_db
class TestTheStatusDocumentWalksThePages:
    """US-23: el documento de estado trae todos los avances, página por página."""

    def test_every_progress_in_the_order_it_was_worked(
        self, authenticated_client, user
    ) -> None:
        """Caso de borde - Más avances de los que caben en una página."""
        project, muro, _ = make_project(user)
        rows = advances(project, muro, 45)

        walked, url = [], f"{URL}?project={project.id}&page_size=20"
        while url:
            page = authenticated_client.get(url).json()
            walked += page["results"]
            url = page["next"]

        assert [row["id"] for row in walked] == [str(r.id) for r in rows]
        assert walked[0]["item"] == "Muro de tablaroca"
        assert walked[0]["date"] == "2026-01-01"
        assert Decimal(walked[0]["quantity"]) == Decimal("1.00")


@pytest.mark.django_db
class TestTheProjectDetailNoLongerCarriesItsProgresses:
    """US-113 · US-17: el detalle trae el proyecto; sus avances, su lista."""

    def test_the_detail_has_no_progresses(self, authenticated_client, user) -> None:
        """Cambio iteracion-28 - El proyecto ya no trae todos sus avances."""
        project, muro, _ = make_project(user)
        advances(project, muro, 3)

        response = authenticated_client.get(f"{PROJECTS_URL}{project.id}/")

        assert response.status_code == 200
        assert "progresses" not in response.data
        assert Decimal(response.data["advanced_value"]) == Decimal("1050.00")
        assert len(response.data["items"]) == 2

    def test_a_new_project_answers_without_progresses_too(self, user) -> None:
        """Lo que responde ``POST /api/projects/`` es el mismo detalle."""
        from apps.projects.tests.test_projects import make_quote

        quote, _muro, _zocalo = make_quote(user)
        client = APIClient()
        client.force_authenticate(user=user)

        response = client.post(PROJECTS_URL, {"quote": str(quote.id)})

        assert response.status_code == 201
        assert "progresses" not in response.data
