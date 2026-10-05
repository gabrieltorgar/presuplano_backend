"""US-113 y US-16 (v3.1): el historial de avances y sus fotos.

Lo registrado en obra tiene que poder revisarse y corregirse —un dedo
equivocado en la cantidad no puede quedarse dentro del cálculo para siempre— y
las fotos que respaldan cada avance tienen que poder volver a verse.
"""

from datetime import date
from decimal import Decimal

import pytest
from rest_framework import status

from apps.projects.models import Evidence, Progress, Project
from apps.projects.services import add_evidence, register_progress
from apps.projects.tests.test_projects import PROJECTS_URL, make_project, png_file
from apps.staff.models import WorkerService
from apps.staff.tests.factories import WorkerFactory

PROGRESSES_URL = "/api/progresses/"


def progress_url(progress_id) -> str:
    return f"{PROGRESSES_URL}{progress_id}/"


def advance(project, item, quantity: str, *, worker=None, day: int = 10) -> Progress:
    return register_progress(
        project=project,
        quote_item=item,
        quantity=Decimal(quantity),
        date=date(2026, 1, day),
        worker=worker,
    )


def worker_who_does(user, item, price: str, name: str = "Juan Pérez"):
    worker = WorkerFactory(owner=user, name=name)
    WorkerService.objects.create(worker=worker, tariff=item.tariff, unit_price=price)
    return worker


@pytest.mark.django_db
class TestProgressHistoryIsReadable:
    """US-113: el proyecto trae cada avance con lo necesario para mostrarlo."""

    def test_each_progress_says_what_who_and_how_much(
        self, authenticated_client, user
    ) -> None:
        """Flujo principal - Lista de avances en la pantalla del proyecto."""
        project, muro, _zocalo = make_project(user)
        worker = worker_who_does(user, muro, "90")
        entry = advance(project, muro, "4", worker=worker)

        response = authenticated_client.get(f"{PROJECTS_URL}{project.id}/")

        [row] = response.data["progresses"]
        assert row["id"] == str(entry.id)
        assert row["quote_item"] == str(muro.id)
        assert row["item"] == "Muro de tablaroca"
        assert row["unit_type"] == muro.unit_type
        assert Decimal(row["quantity"]) == Decimal("4")
        assert Decimal(row["earned_value"]) == Decimal("1400.00")
        assert row["worker"] == str(worker.id)
        assert row["worker_name"] == "Juan Pérez"
        assert row["evidence"] == []

    def test_each_progress_brings_its_photos(
        self, authenticated_client, user, settings, tmp_path
    ) -> None:
        """US-16 - Las fotos de un avance vuelven con el proyecto."""
        settings.MEDIA_ROOT = str(tmp_path)
        project, muro, _zocalo = make_project(user)
        entry = advance(project, muro, "4")
        photo = add_evidence(progress=entry, image=png_file("obra.png"))

        response = authenticated_client.get(f"{PROJECTS_URL}{project.id}/")

        [shot] = response.data["progresses"][0]["evidence"]
        assert shot["id"] == str(photo.id)
        assert shot["image"].startswith("http")
        assert shot["image"].endswith(".png")


@pytest.mark.django_db
class TestCorrectProgress:
    """US-113: corregir un avance registrado."""

    def test_quantity_and_date_can_be_corrected(
        self, authenticated_client, user
    ) -> None:
        """Flujo principal - Se capturó 40 en vez de 4."""
        project, muro, _zocalo = make_project(user)
        entry = advance(project, muro, "8")

        response = authenticated_client.patch(
            progress_url(entry.id),
            {"quantity": "4", "date": "2026-01-12"},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        entry.refresh_from_db()
        assert entry.quantity == Decimal("4")
        assert entry.date == date(2026, 1, 12)

    def test_it_can_use_what_it_already_had(self, authenticated_client, user) -> None:
        """Caso de borde - Subir el propio avance hasta lo cotizado."""
        project, muro, _zocalo = make_project(user)
        advance(project, muro, "3")
        entry = advance(project, muro, "5")

        response = authenticated_client.patch(
            progress_url(entry.id), {"quantity": "7"}, format="json"
        )

        assert response.status_code == status.HTTP_200_OK

    def test_it_cannot_go_past_what_was_quoted(
        self, authenticated_client, user
    ) -> None:
        """Caso alternativo - La corrección supera lo que queda de la partida."""
        project, muro, _zocalo = make_project(user)
        advance(project, muro, "3")
        entry = advance(project, muro, "5")

        response = authenticated_client.patch(
            progress_url(entry.id), {"quantity": "7.5"}, format="json"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "supera la cantidad pendiente (7" in str(response.data)

    def test_quantity_must_stay_positive(self, authenticated_client, user) -> None:
        project, muro, _zocalo = make_project(user)
        entry = advance(project, muro, "5")

        response = authenticated_client.patch(
            progress_url(entry.id), {"quantity": "0"}, format="json"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "mayor a 0" in str(response.data)

    def test_changing_who_did_it_takes_that_persons_price(
        self, authenticated_client, user
    ) -> None:
        """El trato de quien lo hizo de verdad es el que cuenta."""
        project, muro, _zocalo = make_project(user)
        juan = worker_who_does(user, muro, "90", name="Juan")
        ana = worker_who_does(user, muro, "110", name="Ana")
        entry = advance(project, muro, "5", worker=juan)

        response = authenticated_client.patch(
            progress_url(entry.id), {"worker": str(ana.id)}, format="json"
        )

        assert response.status_code == status.HTTP_200_OK
        entry.refresh_from_db()
        assert entry.worker == ana
        assert entry.labor_unit_price == Decimal("110")

    def test_correcting_the_quantity_keeps_the_agreed_price(
        self, authenticated_client, user
    ) -> None:
        """Cambiar hoy el precio del trabajador no reescribe lo ya trabajado."""
        project, muro, _zocalo = make_project(user)
        juan = worker_who_does(user, muro, "90")
        entry = advance(project, muro, "5", worker=juan)
        juan.services.update(unit_price="150")

        authenticated_client.patch(
            progress_url(entry.id), {"quantity": "6"}, format="json"
        )

        entry.refresh_from_db()
        assert entry.labor_unit_price == Decimal("90")

    def test_it_can_become_work_of_the_house(self, authenticated_client, user) -> None:
        """Quitar a quien lo hizo deja el avance sin nada que pagar."""
        project, muro, _zocalo = make_project(user)
        juan = worker_who_does(user, muro, "90")
        entry = advance(project, muro, "5", worker=juan)

        authenticated_client.patch(
            progress_url(entry.id), {"worker": None}, format="json"
        )

        entry.refresh_from_db()
        assert entry.worker is None
        assert entry.labor_unit_price is None

    def test_a_worker_with_no_price_is_rejected(
        self, authenticated_client, user
    ) -> None:
        project, muro, _zocalo = make_project(user)
        entry = advance(project, muro, "5")
        nadie = WorkerFactory(owner=user, name="Sin trato")

        response = authenticated_client.patch(
            progress_url(entry.id), {"worker": str(nadie.id)}, format="json"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Falta decir cuánto se le paga a Sin trato" in str(response.data)

    def test_a_finished_project_is_closed(self, authenticated_client, user) -> None:
        """Caso alternativo - El proyecto ya se cerró."""
        project, muro, _zocalo = make_project(user)
        entry = advance(project, muro, "5")
        Project.objects.filter(id=project.id).update(status=Project.Status.FINISHED)

        response = authenticated_client.patch(
            progress_url(entry.id), {"quantity": "4"}, format="json"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "finalizado" in str(response.data)

    def test_another_accounts_progress_is_not_found(
        self, authenticated_client, user_factory
    ) -> None:
        other = user_factory()
        project, muro, _zocalo = make_project(other)
        entry = advance(project, muro, "5")

        response = authenticated_client.patch(
            progress_url(entry.id), {"quantity": "4"}, format="json"
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
class TestDeleteProgress:
    """US-113: borrar un avance que no ocurrió."""

    def test_the_progress_goes_and_the_advance_goes_down(
        self, authenticated_client, user
    ) -> None:
        """Flujo principal - Avance registrado dos veces."""
        project, muro, _zocalo = make_project(user)
        advance(project, muro, "4")
        duplicado = advance(project, muro, "4")

        response = authenticated_client.delete(progress_url(duplicado.id))

        assert response.status_code == status.HTTP_204_NO_CONTENT
        detail = authenticated_client.get(f"{PROJECTS_URL}{project.id}/").data
        assert Decimal(detail["advanced_value"]) == Decimal("1400.00")

    def test_its_photos_go_with_it(
        self,
        authenticated_client,
        user,
        settings,
        tmp_path,
        django_capture_on_commit_callbacks,
    ) -> None:
        settings.MEDIA_ROOT = str(tmp_path)
        project, muro, _zocalo = make_project(user)
        entry = advance(project, muro, "4")
        photo = add_evidence(progress=entry, image=png_file())
        stored = tmp_path / photo.image.name
        assert stored.exists()

        with django_capture_on_commit_callbacks(execute=True):
            authenticated_client.delete(progress_url(entry.id))

        assert not Evidence.objects.filter(id=photo.id).exists()
        assert not stored.exists()

    def test_a_finished_project_is_closed(self, authenticated_client, user) -> None:
        project, muro, _zocalo = make_project(user)
        entry = advance(project, muro, "4")
        Project.objects.filter(id=project.id).update(status=Project.Status.FINISHED)

        response = authenticated_client.delete(progress_url(entry.id))

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert Progress.objects.filter(id=entry.id).exists()


@pytest.mark.django_db
class TestEvidenceAnyTime:
    """US-16 (v3.1): adjuntar y quitar fotos de cualquier avance."""

    def test_an_old_progress_takes_a_photo(
        self, authenticated_client, user, settings, tmp_path
    ) -> None:
        """Flujo principal - La foto llega días después del avance."""
        settings.MEDIA_ROOT = str(tmp_path)
        project, muro, _zocalo = make_project(user)
        viejo = advance(project, muro, "2", day=3)
        advance(project, muro, "2", day=9)

        response = authenticated_client.post(
            f"{progress_url(viejo.id)}evidence/",
            {"image": png_file()},
            format="multipart",
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["image"].startswith("http")
        assert viejo.evidences.count() == 1

    def test_a_photo_can_be_removed(
        self,
        authenticated_client,
        user,
        settings,
        tmp_path,
        django_capture_on_commit_callbacks,
    ) -> None:
        """Caso alternativo - Se subió la foto equivocada."""
        settings.MEDIA_ROOT = str(tmp_path)
        project, muro, _zocalo = make_project(user)
        entry = advance(project, muro, "2")
        photo = add_evidence(progress=entry, image=png_file())
        stored = tmp_path / photo.image.name
        assert stored.exists()

        with django_capture_on_commit_callbacks(execute=True):
            response = authenticated_client.delete(f"/api/evidences/{photo.id}/")

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not Evidence.objects.filter(id=photo.id).exists()
        assert not stored.exists()

    def test_another_accounts_photo_is_not_found(
        self, authenticated_client, user_factory, settings, tmp_path
    ) -> None:
        settings.MEDIA_ROOT = str(tmp_path)
        project, muro, _zocalo = make_project(user_factory())
        entry = advance(project, muro, "2")
        photo = add_evidence(progress=entry, image=png_file())

        response = authenticated_client.delete(f"/api/evidences/{photo.id}/")

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert Evidence.objects.filter(id=photo.id).exists()

    def test_a_finished_project_takes_no_more_photos(
        self, authenticated_client, user, settings, tmp_path
    ) -> None:
        """Caso de borde - El proyecto cerrado ya no cambia."""
        settings.MEDIA_ROOT = str(tmp_path)
        project, muro, _zocalo = make_project(user)
        entry = advance(project, muro, "2")
        Project.objects.filter(id=project.id).update(status=Project.Status.FINISHED)

        response = authenticated_client.post(
            f"{progress_url(entry.id)}evidence/",
            {"image": png_file()},
            format="multipart",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "finalizado" in str(response.data)
