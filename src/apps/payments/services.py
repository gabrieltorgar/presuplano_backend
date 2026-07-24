"""Payments business logic (all domain operations live here)."""

import logging
from decimal import Decimal

from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.payments.models import Payment
from apps.projects.models import Project
from apps.projects.selectors import advanced_value, quoted_value

logger = logging.getLogger("apps")


def total_paid(project: Project) -> Decimal:
    """Sum of all payments registered on the project."""
    return sum((payment.amount for payment in project.payments.all()), Decimal("0"))


def pending_balance(project: Project) -> Decimal:
    """Advanced-vs-paid balance (used by project closure). Can be negative when
    the client has paid ahead of the executed work."""
    return advanced_value(project) - total_paid(project)


def receivable_balance(project: Project) -> Decimal:
    """Amount still to collect on the whole quote: max(quoted − paid, 0)."""
    return max(quoted_value(project) - total_paid(project), Decimal("0"))


def credit_balance(project: Project) -> Decimal:
    """Overpayment credit (saldo a favor): max(paid − quoted, 0)."""
    return max(total_paid(project) - quoted_value(project), Decimal("0"))


@transaction.atomic
def register_payment(
    *,
    owner,
    project: Project,
    amount: Decimal,
    date,
    quote_item=None,
    method: str = Payment.Method.CASH,
) -> Payment:
    """Register a payment against the project (total, partial or advance).

    Payments are not capped by the advanced value: an advance (anticipo) may be
    registered before any work exists. If the accumulated paid exceeds the quoted
    total, the surplus is reflected as a credit balance (see selectors).

    Raises:
        ValidationError: project not owned/finished, or non-positive amount.
    """
    if project.owner_id != owner.id:
        raise ValidationError("Proyecto no encontrado.")
    if project.status == Project.Status.FINISHED:
        raise ValidationError("El proyecto está finalizado")
    if amount <= 0:
        raise ValidationError("El monto del pago debe ser mayor a 0")

    payment = Payment.objects.create(
        owner=owner,
        project=project,
        amount=amount,
        date=date,
        quote_item=quote_item,
        method=method,
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
