"""RED tests for EPIC-06 — payments (US-18, US-19, US-20)."""

from datetime import date
from decimal import Decimal

import pytest
from rest_framework import status

from apps.catalog.tests.factories import TariffFactory
from apps.clients.tests.factories import ClientFactory
from apps.payments.services import register_payment
from apps.projects.services import register_progress, start_project
from apps.quotes.services import create_quote, generate_quote_document

PAYMENTS_URL = "/api/payments/"


def make_project_with_advance(user, advance=Decimal("6")):
    """Project (quoted 5100) with `advance` m² of muro advanced (earned 2100)."""
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
        quantity=advance,
        date=date(2026, 1, 10),
    )
    return project


@pytest.mark.django_db
class TestRegisterPayment:
    """US-18: register a total or partial payment (with pending balance)."""

    def test_partial_payment_leaves_pending(self, authenticated_client, user) -> None:
        """Flujo principal - Pago parcial deja saldo pendiente."""
        project = make_project_with_advance(user)  # advanced 2100
        payload = {"project": str(project.id), "amount": "1000", "date": "2026-01-15"}

        response = authenticated_client.post(PAYMENTS_URL, payload)

        assert response.status_code == status.HTTP_201_CREATED
        summary = authenticated_client.get(
            f"{PAYMENTS_URL}summary/", {"project": str(project.id)}
        )
        assert Decimal(summary.data["total_paid"]) == Decimal("1000.00")
        assert Decimal(summary.data["pending_balance"]) == Decimal("1100.00")

    def test_payment_exceeding_pending_returns_400(
        self, authenticated_client, user
    ) -> None:
        """Caso alternativo - Pago supera el saldo pendiente."""
        project = make_project_with_advance(user)  # advanced 2100
        register_payment(
            owner=user, project=project, amount=Decimal("1000"), date=date(2026, 1, 15)
        )
        payload = {"project": str(project.id), "amount": "1500", "date": "2026-01-16"}

        response = authenticated_client.post(PAYMENTS_URL, payload)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "El pago supera el saldo pendiente (1100" in str(response.data)

    def test_zero_amount_returns_400(self, authenticated_client, user) -> None:
        """Caso de borde - Monto de pago en cero."""
        project = make_project_with_advance(user)
        payload = {"project": str(project.id), "amount": "0", "date": "2026-01-15"}

        response = authenticated_client.post(PAYMENTS_URL, payload)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "El monto del pago debe ser mayor a 0" in str(response.data)


@pytest.mark.django_db
class TestVoucher:
    """US-19: generate the payment voucher."""

    def test_voucher_with_amount_and_balance(self, authenticated_client, user) -> None:
        """Flujo principal - Comprobante con monto y saldo."""
        project = make_project_with_advance(user)
        register_payment(
            owner=user, project=project, amount=Decimal("1000"), date=date(2026, 1, 15)
        )

        response = authenticated_client.get(
            f"{PAYMENTS_URL}voucher/", {"project": str(project.id)}
        )

        assert response.status_code == status.HTTP_200_OK
        assert Decimal(response.data["amount"]) == Decimal("1000.00")
        assert Decimal(response.data["pending_balance"]) == Decimal("1100.00")
        assert response.data["client_name"] == "Constructora Reyes"

    def test_voucher_without_payments_returns_400(
        self, authenticated_client, user
    ) -> None:
        """Caso alternativo - Proyecto sin pagos."""
        project = make_project_with_advance(user)

        response = authenticated_client.get(
            f"{PAYMENTS_URL}voucher/", {"project": str(project.id)}
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "No hay pagos para generar un comprobante" in str(response.data)

    def test_regenerate_voucher_is_stable(self, authenticated_client, user) -> None:
        """Caso de borde - Regenerar el comprobante."""
        project = make_project_with_advance(user)
        register_payment(
            owner=user, project=project, amount=Decimal("1000"), date=date(2026, 1, 15)
        )
        url = f"{PAYMENTS_URL}voucher/"

        first = authenticated_client.get(url, {"project": str(project.id)})
        second = authenticated_client.get(url, {"project": str(project.id)})

        assert Decimal(first.data["amount"]) == Decimal("1000.00")
        assert Decimal(second.data["amount"]) == Decimal("1000.00")
        assert project.payments.count() == 1


@pytest.mark.django_db
class TestPaymentSummary:
    """US-20: consult payments and pending balance."""

    def test_summary_with_payments(self, authenticated_client, user) -> None:
        """Flujo principal - Estado de cobros con saldo."""
        project = make_project_with_advance(user)  # advanced 2100
        register_payment(
            owner=user, project=project, amount=Decimal("1000"), date=date(2026, 1, 15)
        )

        response = authenticated_client.get(
            f"{PAYMENTS_URL}summary/", {"project": str(project.id)}
        )

        assert Decimal(response.data["total_paid"]) == Decimal("1000.00")
        assert Decimal(response.data["pending_balance"]) == Decimal("1100.00")
        assert len(response.data["payments"]) == 1

    def test_summary_without_payments(self, authenticated_client, user) -> None:
        """Caso alternativo - Proyecto sin pagos."""
        project = make_project_with_advance(user)  # advanced 2100

        response = authenticated_client.get(
            f"{PAYMENTS_URL}summary/", {"project": str(project.id)}
        )

        assert Decimal(response.data["total_paid"]) == Decimal("0")
        assert Decimal(response.data["pending_balance"]) == Decimal("2100.00")

    def test_summary_fully_paid(self, authenticated_client, user) -> None:
        """Caso de borde - Proyecto totalmente pagado."""
        project = make_project_with_advance(user)  # advanced 2100
        register_payment(
            owner=user, project=project, amount=Decimal("2100"), date=date(2026, 1, 15)
        )

        response = authenticated_client.get(
            f"{PAYMENTS_URL}summary/", {"project": str(project.id)}
        )

        assert Decimal(response.data["pending_balance"]) == Decimal("0")
