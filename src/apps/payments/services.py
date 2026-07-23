"""Payments business logic (all domain operations live here)."""

import logging
from decimal import Decimal

from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.payments.models import Payment
from apps.projects.models import Project
from apps.projects.selectors import advanced_value

logger = logging.getLogger("apps")


def total_paid(project: Project) -> Decimal:
    """Sum of all payments registered on the project."""
    return sum((payment.amount for payment in project.payments.all()), Decimal("0"))


def pending_balance(project: Project) -> Decimal:
    """Pending balance = advanced (earned) value − total paid."""
    return advanced_value(project) - total_paid(project)


@transaction.atomic
def register_payment(
    *, owner, project: Project, amount: Decimal, date, quote_item=None
) -> Payment:
    """Register a total or partial payment against the project.

    Raises:
        ValidationError: project not owned/finished, non-positive amount, or an
            amount exceeding the pending balance.
    """
    if project.owner_id != owner.id:
        raise ValidationError("Proyecto no encontrado.")
    if project.status == Project.Status.FINISHED:
        raise ValidationError("El proyecto está finalizado")
    if amount <= 0:
        raise ValidationError("El monto del pago debe ser mayor a 0")

    pending = pending_balance(project)
    if amount > pending:
        raise ValidationError(f"El pago supera el saldo pendiente ({pending})")

    payment = Payment.objects.create(
        owner=owner, project=project, amount=amount, date=date, quote_item=quote_item
    )
    logger.info("Payment registered", extra={"payment_id": str(payment.pk)})
    return payment


def build_voucher(*, project: Project) -> dict:
    """Build the voucher for the project's latest payment.

    Raises:
        ValidationError: the project has no payments.
    """
    payment = project.payments.order_by("-date", "-created_at").first()
    if payment is None:
        raise ValidationError("No hay pagos para generar un comprobante")
    return {
        "client_name": project.quote.client.name,
        "date": payment.date,
        "amount": payment.amount,
        "pending_balance": pending_balance(project),
    }
