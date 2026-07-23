"""RED tests for EPIC-05 — projects, progress and evidence (US-14..17)."""

from datetime import date
from decimal import Decimal
from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from rest_framework import status

from apps.catalog.tests.factories import TariffFactory
from apps.clients.tests.factories import ClientFactory
from apps.projects.models import Project
from apps.projects.services import register_progress, start_project
from apps.quotes.services import create_quote, generate_quote_document

PROJECTS_URL = "/api/projects/"


def make_documented_quote(user):
    client = ClientFactory(owner=user, name="Constructora Reyes")
    muro = TariffFactory(owner=user, name="Muro de tablaroca", unit_price="350")
    zocalo = TariffFactory(
        owner=user, name="Zócalo", unit_type="linear_meter", unit_price="80"
    )
    quote = create_quote(
        owner=user,
        client=client,
        items_data=[
            {"tariff": muro, "quantity": Decimal("10")},
            {"tariff": zocalo, "quantity": Decimal("20")},
        ],
    )
    generate_quote_document(quote=quote)
    return quote, muro, zocalo


def make_project(user):
    quote, muro, zocalo = make_documented_quote(user)
    project = start_project(owner=user, quote=quote)
    muro_item = quote.items.get(tariff=muro)
    zocalo_item = quote.items.get(tariff=zocalo)
    return project, muro_item, zocalo_item


def png_file(name="e.png") -> SimpleUploadedFile:
    buffer = BytesIO()
    Image.new("RGB", (10, 10), "blue").save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


@pytest.mark.django_db
class TestStartProject:
    """US-14: start a project from a documented quote."""

    def test_start_from_documented_quote_returns_201(
        self, authenticated_client, user
    ) -> None:
        """Flujo principal - Proyecto creado desde cotización con documento."""
        quote, _muro, _zocalo = make_documented_quote(user)

        response = authenticated_client.post(PROJECTS_URL, {"quote": str(quote.id)})

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["status"] == Project.Status.IN_PROGRESS
        assert Decimal(response.data["quoted_value"]) == Decimal("5100.00")

    def test_start_from_draft_quote_returns_400(
        self, authenticated_client, user
    ) -> None:
        """Caso alternativo - Cotización aún en borrador."""
        client = ClientFactory(owner=user)
        muro = TariffFactory(owner=user, unit_price="350")
        quote = create_quote(
            owner=user,
            client=client,
            items_data=[{"tariff": muro, "quantity": Decimal("10")}],
        )  # still DRAFT

        response = authenticated_client.post(PROJECTS_URL, {"quote": str(quote.id)})

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Genera el documento de la cotización" in str(response.data)

    def test_start_twice_returns_400(self, authenticated_client, user) -> None:
        """Caso de borde - Cotización ya con proyecto."""
        quote, _muro, _zocalo = make_documented_quote(user)
        start_project(owner=user, quote=quote)

        response = authenticated_client.post(PROJECTS_URL, {"quote": str(quote.id)})

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "ya tiene un proyecto asociado" in str(response.data)


@pytest.mark.django_db
class TestRegisterProgress:
    """US-15: register progress by quantity or percentage."""

    def _url(self, project) -> str:
        return f"{PROJECTS_URL}{project.id}/progress/"

    def test_progress_by_quantity(self, authenticated_client, user) -> None:
        """Flujo principal - Avance por cantidad."""
        project, muro_item, _z = make_project(user)
        payload = {
            "quote_item": str(muro_item.id),
            "quantity": "6",
            "date": "2026-01-10",
        }

        response = authenticated_client.post(self._url(project), payload)

        assert response.status_code == status.HTTP_201_CREATED
        assert Decimal(response.data["earned_value"]) == Decimal("2100.00")

    def test_progress_by_percentage(self, authenticated_client, user) -> None:
        """Flujo principal - Avance por porcentaje."""
        project, muro_item, _z = make_project(user)
        payload = {
            "quote_item": str(muro_item.id),
            "percentage": "60",
            "date": "2026-01-10",
        }

        response = authenticated_client.post(self._url(project), payload)

        assert response.status_code == status.HTTP_201_CREATED
        assert Decimal(response.data["earned_value"]) == Decimal("2100.00")

    def test_progress_exceeding_quoted_returns_400(
        self, authenticated_client, user
    ) -> None:
        """Caso alternativo - Avance supera lo cotizado."""
        project, muro_item, _z = make_project(user)
        register_progress(
            project=project,
            quote_item=muro_item,
            quantity=Decimal("6"),
            date=date(2026, 1, 10),
        )
        payload = {
            "quote_item": str(muro_item.id),
            "quantity": "6",
            "date": "2026-01-11",
        }

        response = authenticated_client.post(self._url(project), payload)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "supera la cantidad cotizada" in str(response.data)

    def test_progress_zero_returns_400(self, authenticated_client, user) -> None:
        """Caso de borde - Avance en cero."""
        project, muro_item, _z = make_project(user)
        payload = {
            "quote_item": str(muro_item.id),
            "quantity": "0",
            "date": "2026-01-10",
        }

        response = authenticated_client.post(self._url(project), payload)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "El avance debe ser mayor a 0" in str(response.data)


@pytest.mark.django_db
class TestEvidence:
    """US-16: attach photographic evidence to a progress entry."""

    def _register(self, user):
        project, muro_item, _z = make_project(user)
        progress = register_progress(
            project=project,
            quote_item=muro_item,
            quantity=Decimal("6"),
            date=date(2026, 1, 10),
        )
        return progress

    def test_attach_image_returns_201(
        self, authenticated_client, user, settings, tmp_path
    ) -> None:
        """Flujo principal - Adjuntar imágenes a un avance."""
        settings.MEDIA_ROOT = str(tmp_path)
        progress = self._register(user)
        url = f"/api/progresses/{progress.id}/evidence/"

        response = authenticated_client.post(
            url, {"image": png_file()}, format="multipart"
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert progress.evidences.count() == 1

    def test_reject_non_image(self, authenticated_client, user) -> None:
        """Caso alternativo - Archivo que no es imagen."""
        progress = self._register(user)
        url = f"/api/progresses/{progress.id}/evidence/"
        not_image = SimpleUploadedFile("doc.txt", b"hello", content_type="text/plain")

        response = authenticated_client.post(
            url, {"image": not_image}, format="multipart"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Solo se permiten archivos de imagen" in str(response.data)

    def test_reject_oversized_image(self, authenticated_client, user) -> None:
        """Caso de borde - Imagen supera el tamaño máximo."""
        progress = self._register(user)
        url = f"/api/progresses/{progress.id}/evidence/"
        big = SimpleUploadedFile(
            "big.png", b"0" * (5 * 1024 * 1024 + 1), content_type="image/png"
        )

        response = authenticated_client.post(url, {"image": big}, format="multipart")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "La imagen supera el tamaño máximo permitido" in str(response.data)


@pytest.mark.django_db
class TestProjectProgressSummary:
    """US-17: consult the project's progress."""

    def test_summary_with_progress(self, authenticated_client, user) -> None:
        """Flujo principal - Resumen de avance con porcentaje."""
        project, muro_item, _z = make_project(user)
        register_progress(
            project=project,
            quote_item=muro_item,
            quantity=Decimal("6"),
            date=date(2026, 1, 10),
        )

        response = authenticated_client.get(f"{PROJECTS_URL}{project.id}/")

        assert Decimal(response.data["quoted_value"]) == Decimal("5100.00")
        assert Decimal(response.data["advanced_value"]) == Decimal("2100.00")
        assert 40 < float(response.data["progress_percentage"]) < 42

    def test_summary_without_progress(self, authenticated_client, user) -> None:
        """Caso alternativo - Proyecto sin avances."""
        project, _m, _z = make_project(user)

        response = authenticated_client.get(f"{PROJECTS_URL}{project.id}/")

        assert Decimal(response.data["advanced_value"]) == Decimal("0")
        assert float(response.data["progress_percentage"]) == 0.0

    def test_summary_fully_advanced(self, authenticated_client, user) -> None:
        """Caso de borde - Proyecto totalmente avanzado."""
        project, muro_item, zocalo_item = make_project(user)
        register_progress(
            project=project,
            quote_item=muro_item,
            quantity=Decimal("10"),
            date=date(2026, 1, 10),
        )
        register_progress(
            project=project,
            quote_item=zocalo_item,
            quantity=Decimal("20"),
            date=date(2026, 1, 10),
        )

        response = authenticated_client.get(f"{PROJECTS_URL}{project.id}/")

        assert Decimal(response.data["advanced_value"]) == Decimal("5100.00")
        assert float(response.data["progress_percentage"]) == 100.0
