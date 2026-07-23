"""RED tests for EPIC-07 — finalize project + summary document (US-21)."""

from datetime import date
from decimal import Decimal

import pytest
from rest_framework import status

from apps.catalog.tests.factories import TariffFactory
from apps.clients.tests.factories import ClientFactory
from apps.payments.services import register_payment
from apps.projects.models import Project
from apps.projects.services import register_progress, start_project
from apps.quotes.services import create_quote, generate_quote_document

PROJECTS_URL = "/api/projects/"


def build_project(user, paid=None):
    """Project quoted 5100, advanced 2100 (muro 6 m²), optionally `paid`."""
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
    project = start_project(owner=user, quote=quote)
    muro_item = quote.items.get(tariff=muro)
    register_progress(
        project=project,
        quote_item=muro_item,
        quantity=Decimal("6"),
        date=date(2026, 1, 10),
    )
    if paid is not None:
        register_payment(
            owner=user, project=project, amount=paid, date=date(2026, 1, 15)
        )
    return project, muro_item


@pytest.mark.django_db
class TestFinalizeProject:
    """US-21: finalize the project and generate its summary."""

    def test_finalize_with_no_pending_returns_summary(
        self, authenticated_client, user
    ) -> None:
        """Flujo principal - Cierre con documento resumen."""
        project, _item = build_project(user, paid=Decimal("2100"))  # pending 0

        response = authenticated_client.post(f"{PROJECTS_URL}{project.id}/finalize/")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == Project.Status.FINISHED
        assert Decimal(response.data["quoted_value"]) == Decimal("5100.00")
        assert Decimal(response.data["total_paid"]) == Decimal("2100.00")
        assert len(response.data["progresses"]) == 1
        assert len(response.data["payments"]) == 1
        project.refresh_from_db()
        assert project.status == Project.Status.FINISHED

    def test_finalize_with_pending_requires_confirmation(
        self, authenticated_client, user
    ) -> None:
        """Caso alternativo - Cierre con saldo pendiente."""
        project, _item = build_project(user, paid=Decimal("1000"))  # pending 1100

        response = authenticated_client.post(f"{PROJECTS_URL}{project.id}/finalize/")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "saldo pendiente de cobro de 1100" in str(response.data)
        project.refresh_from_db()
        assert project.status == Project.Status.IN_PROGRESS

        confirmed = authenticated_client.post(
            f"{PROJECTS_URL}{project.id}/finalize/", {"confirm": True}
        )
        assert confirmed.status_code == status.HTTP_200_OK
        project.refresh_from_db()
        assert project.status == Project.Status.FINISHED

    def test_finished_project_blocks_new_progress(
        self, authenticated_client, user
    ) -> None:
        """Caso de borde - Proyecto ya finalizado."""
        project, muro_item = build_project(user, paid=Decimal("2100"))
        authenticated_client.post(f"{PROJECTS_URL}{project.id}/finalize/")

        response = authenticated_client.post(
            f"{PROJECTS_URL}{project.id}/progress/",
            {"quote_item": str(muro_item.id), "quantity": "1", "date": "2026-02-01"},
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "El proyecto está finalizado" in str(response.data)
