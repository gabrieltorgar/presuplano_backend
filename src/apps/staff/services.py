"""Staff business logic: who gets what, what it accrues and what is paid."""

import logging
from decimal import Decimal

from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.quotes.models import QuoteItem
from apps.staff.models import Assignment, Worker, WorkerPayment, WorkerService

logger = logging.getLogger("apps")

ZERO = Decimal("0.00")


@transaction.atomic
def set_worker_services(*, worker: Worker, services: list[dict]) -> Worker:
    """Replace what a worker does, with what each of those services pays them.

    Raises:
        ValidationError: a service from another account.
    """
    for entry in services:
        tariff = entry["tariff"]
        if tariff.owner_id != worker.owner_id:
            raise ValidationError("Servicio no encontrado.")

    worker.services.all().delete()
    WorkerService.objects.bulk_create(
        [
            WorkerService(
                worker=worker,
                tariff=entry["tariff"],
                unit_price=entry.get("unit_price"),
            )
            for entry in services
        ]
    )
    return worker


def labor_unit_price_for(*, quote_item: QuoteItem, worker: Worker) -> Decimal | None:
    """Lo que se le paga a esa persona por una unidad de esa partida.

    First what was agreed when the work was handed out —the assignment carries
    its own price—, then what that person charges for the service in general.
    `None` means nobody has said yet, and the caller decides whether that is an
    error or simply work that owes nothing.
    """
    assignment = Assignment.objects.filter(quote_item=quote_item, worker=worker).first()
    if assignment is not None:
        return assignment.unit_price

    service = worker.services.filter(tariff_id=quote_item.tariff_id).first()
    if service is not None and service.unit_price is not None:
        return service.unit_price
    return ZERO if worker.is_self else None


@transaction.atomic
def assign_service(
    *,
    project,
    quote_item: QuoteItem,
    worker: Worker,
    quantity: Decimal,
    unit_price: Decimal | None = None,
    note: str = "",
) -> Assignment:
    """Hand part of a line item to a worker, at an agreed unit price.

    Handing the same item to the same person twice REPLACES the first share:
    the natural reading of «ahora le tocan 80» is a correction, not a second
    helping.

    Raises:
        ValidationError: item outside the project, worker from another account,
            non-positive quantity, no price agreed, or more than the item holds.
    """
    if quote_item.quote_id != project.quote_id:
        raise ValidationError("La partida no pertenece a este proyecto.")
    if worker.owner_id != project.owner_id:
        raise ValidationError("Personal no encontrado.")
    if quantity is None or quantity <= 0:
        raise ValidationError("La cantidad repartida debe ser mayor a 0")

    if unit_price is None:
        unit_price = labor_unit_price_for(quote_item=quote_item, worker=worker)
    if unit_price is None:
        raise ValidationError(
            f"Falta decir cuánto se le paga a {worker.name} por {quote_item.name}"
        )

    handed = sum(
        (
            a.quantity
            for a in Assignment.objects.filter(quote_item=quote_item).exclude(
                worker=worker
            )
        ),
        ZERO,
    )
    free = quote_item.quantity - handed
    if quantity > free:
        raise ValidationError(f"Sólo quedan {free} por repartir de {quote_item.name}")

    assignment, _ = Assignment.objects.update_or_create(
        quote_item=quote_item,
        worker=worker,
        defaults={
            "project": project,
            "quantity": quantity,
            "unit_price": unit_price,
            "note": note,
        },
    )
    logger.info(
        "Service handed out",
        extra={"assignment_id": str(assignment.pk), "worker_id": str(worker.pk)},
    )
    return assignment


def pay_worker(
    *,
    owner,
    worker: Worker,
    amount: Decimal,
    date,
    method: str = WorkerPayment.Method.CASH,
    project=None,
    note: str = "",
) -> WorkerPayment:
    """Register a payment to a worker, for a project or for the week.

    Raises:
        ValidationError: worker from another account, paying yourself, or a
            non-positive amount.
    """
    if worker.owner_id != owner.id:
        raise ValidationError("Personal no encontrado.")
    if worker.is_self:
        raise ValidationError("A ti mismo no te pagas: eso es lo que te queda")
    if amount is None or amount <= 0:
        raise ValidationError("El monto debe ser mayor a 0")
    if project is not None and project.owner_id != owner.id:
        raise ValidationError("Proyecto no encontrado.")

    payment = WorkerPayment.objects.create(
        owner=owner,
        worker=worker,
        project=project,
        amount=amount,
        method=method,
        date=date,
        note=note,
    )
    logger.info(
        "Worker paid",
        extra={"payment_id": str(payment.pk), "worker_id": str(worker.pk)},
    )
    return payment
