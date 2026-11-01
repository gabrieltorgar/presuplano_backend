"""El estado de un proyecto y la conversión desde su cotización (iteracion-26 #20).

Un proyecto nace de una cotización una sola vez y termina cuando se finaliza:
de ahí ya no sale, y nada suyo cambia. El estado lo cambian sólo sus acciones
(``POST /api/projects/`` y ``POST /api/projects/{id}/finalize/``), revisadas
sobre la fila bloqueada y releída, así que dos clics, un reintento o dos
peticiones a la vez no hacen dos proyectos ni escriben en uno ya cerrado.
"""

from datetime import date
from decimal import Decimal

import pytest
from rest_framework import status
from rest_framework.exceptions import ValidationError

from apps.projects.models import Progress, Project
from apps.projects.serializers import (
    ProgressSerializer,
    ProjectListSerializer,
    ProjectSerializer,
)
from apps.projects.services import (
    PROJECT_TRANSITIONS,
    add_evidence,
    delete_progress,
    finalize_project,
    register_progress,
    start_project,
    update_progress,
)
from apps.projects.tests.test_projects import (
    PROJECTS_URL,
    make_project,
    make_quote,
    png_file,
)
from apps.quotes.models import Quote
from common.state_machine import REGISTRY
from common.tests.concurrency import POSTGRES_ONLY, at_the_same_time


def test_a_project_ends_finished_and_never_leaves_it() -> None:
    """SEC-03.1 - La tabla del proyecto y su estado final."""
    assert REGISTRY[Project] is PROJECT_TRANSITIONS
    assert PROJECT_TRANSITIONS.allowed == {
        Project.Status.IN_PROGRESS: frozenset({Project.Status.FINISHED}),
        Project.Status.FINISHED: frozenset(),
    }
    assert PROJECT_TRANSITIONS.terminal == {Project.Status.FINISHED}


@pytest.mark.parametrize("serializer", [ProjectSerializer, ProjectListSerializer])
def test_the_read_shapes_never_write_the_status_nor_the_quote(serializer) -> None:
    """SEC-03 - El estado y la cotización de origen, de solo lectura."""
    fields = serializer().fields

    assert fields["status"].read_only
    assert fields["quote"].read_only


def test_the_labor_price_of_a_progress_is_read_only() -> None:
    """VAL-05 - Lo copia el servicio del reparto: nunca lo escribe el cliente."""
    assert ProgressSerializer().fields["labor_unit_price"].read_only


def _finished_meanwhile(project: Project) -> None:
    """Otra petición lo finalizó después de que ésta lo leyó."""
    Project.objects.filter(pk=project.pk).update(status=Project.Status.FINISHED)


@pytest.mark.django_db
class TestOnlyItsActionsChangeAProject:
    """SEC-03.3 - La ruta del proyecto no tiene PUT, PATCH ni DELETE."""

    @pytest.mark.parametrize("method", ["put", "patch", "delete"])
    def test_a_project_is_not_written_by_the_generic_routes(
        self, authenticated_client, user, method
    ) -> None:
        project, _muro, _zocalo = make_project(user)

        response = getattr(authenticated_client, method)(
            f"{PROJECTS_URL}{project.id}/",
            {"status": Project.Status.FINISHED},
            format="json",
        )

        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED
        project.refresh_from_db()
        assert project.status == Project.Status.IN_PROGRESS

    def test_a_status_sent_when_starting_it_is_ignored(
        self, authenticated_client, user
    ) -> None:
        quote, _muro, _zocalo = make_quote(user)

        response = authenticated_client.post(
            PROJECTS_URL,
            {"quote": str(quote.id), "status": Project.Status.FINISHED},
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["status"] == Project.Status.IN_PROGRESS


@pytest.mark.django_db
class TestTheConversionHappensOnce:
    """SEC-03.2 - Una cotización da un solo proyecto."""

    def test_converting_twice_creates_one_project(
        self, authenticated_client, user
    ) -> None:
        quote, _muro, _zocalo = make_quote(user)

        first = authenticated_client.post(PROJECTS_URL, {"quote": str(quote.id)})
        second = authenticated_client.post(PROJECTS_URL, {"quote": str(quote.id)})

        assert first.status_code == status.HTTP_201_CREATED
        assert second.status_code == status.HTTP_400_BAD_REQUEST
        assert Project.objects.filter(quote=quote).count() == 1

    def test_a_quote_already_in_a_project_is_not_converted_again(self, user) -> None:
        """Revisado en la fila releída: su estado final no tiene salida."""
        quote, _muro, _zocalo = make_quote(user)
        Quote.objects.filter(pk=quote.pk).update(status=Quote.Status.IN_PROJECT)

        with pytest.raises(ValidationError, match="ya tiene un proyecto"):
            start_project(owner=user, quote=quote)

        assert not Project.objects.filter(quote=quote).exists()

    def test_a_quote_of_another_account_is_not_found(self, user, user_factory) -> None:
        quote, _muro, _zocalo = make_quote(user_factory())

        with pytest.raises(ValidationError, match="Cotización no encontrada"):
            start_project(owner=user, quote=quote)


@pytest.mark.django_db
class TestAFinishedProjectIsClosed:
    """SEC-03.1 - Lo que se revisa es la fila bloqueada, no la que se leyó."""

    def test_it_is_not_finished_twice(self, user) -> None:
        project, _muro, _zocalo = make_project(user)
        _finished_meanwhile(project)

        with pytest.raises(ValidationError, match="ya está finalizado"):
            finalize_project(project=project, confirm=True)

    def test_no_progress_enters_it(self, user) -> None:
        project, muro, _zocalo = make_project(user)
        _finished_meanwhile(project)

        with pytest.raises(ValidationError, match="finalizado"):
            register_progress(
                project=project,
                quote_item=muro,
                quantity=Decimal("1"),
                date=date(2026, 2, 1),
            )

        assert not Progress.objects.filter(project=project).exists()

    def test_its_progress_is_not_corrected_nor_deleted(self, user) -> None:
        project, muro, _zocalo = make_project(user)
        entry = register_progress(
            project=project, quote_item=muro, quantity=Decimal("4"), date=date.today()
        )
        _finished_meanwhile(project)

        with pytest.raises(ValidationError, match="finalizado"):
            update_progress(progress=entry, quantity=Decimal("5"))
        with pytest.raises(ValidationError, match="finalizado"):
            delete_progress(progress=entry)

        entry.refresh_from_db()
        assert entry.quantity == Decimal("4")

    def test_no_photo_enters_it(self, user, settings, tmp_path) -> None:
        settings.MEDIA_ROOT = str(tmp_path)
        project, muro, _zocalo = make_project(user)
        entry = register_progress(
            project=project, quote_item=muro, quantity=Decimal("4"), date=date.today()
        )
        _finished_meanwhile(project)

        with pytest.raises(ValidationError, match="finalizado"):
            add_evidence(progress=entry, image=png_file())

        assert not entry.evidences.exists()


@POSTGRES_ONLY
@pytest.mark.django_db(transaction=True)
class TestAtTheSameTime:
    """SEC-03.2 - Con bloqueo de fila, también bajo concurrencia real."""

    def test_concurrent_conversion_creates_one_project(self, user) -> None:
        quote, _muro, _zocalo = make_quote(user)

        def convert(client):
            return client.post(PROJECTS_URL, {"quote": str(quote.id)}).status_code

        codes = at_the_same_time(user, convert, convert)

        assert sorted(codes) in ([201, 400], [201, 409])
        assert Project.objects.filter(quote=quote).count() == 1

    def test_concurrent_progresses_never_exceed_the_item(self, user) -> None:
        project, muro, _zocalo = make_project(user)  # 10 m² cotizados

        def advance(client):
            return client.post(
                f"{PROJECTS_URL}{project.id}/progress/",
                {"quote_item": str(muro.id), "quantity": "6", "date": "2026-01-10"},
            ).status_code

        codes = at_the_same_time(user, advance, advance)

        assert sorted(codes) == [201, 400]
        assert Progress.objects.filter(quote_item=muro).count() == 1

    def test_a_progress_never_enters_a_project_being_finished(self, user) -> None:
        project, muro, _zocalo = make_project(user)

        def finalize(client):
            return client.post(
                f"{PROJECTS_URL}{project.id}/finalize/", {"confirm": True}
            ).status_code

        def advance(client):
            return client.post(
                f"{PROJECTS_URL}{project.id}/progress/",
                {"quote_item": str(muro.id), "quantity": "1", "date": "2026-01-10"},
            ).status_code

        finalized, advanced = at_the_same_time(user, finalize, advance)

        assert finalized == 200
        project.refresh_from_db()
        assert project.status == Project.Status.FINISHED
        # O entró antes de cerrarse (y se cuenta), o no entró.
        assert (advanced, Progress.objects.filter(project=project).count()) in (
            (201, 1),
            (400, 0),
        )
