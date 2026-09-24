"""Projects business logic (all domain operations live here)."""

import logging
from decimal import Decimal

from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.projects.models import Evidence, Progress, Project
from apps.quotes.models import Quote, QuoteItem

logger = logging.getLogger("apps")

MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5 MB


def start_project(*, owner, quote: Quote) -> Project:
    """Start a project from a quote.

    Any quote of the account can become a project: its document exists from the
    moment it does, so there is nothing to generate first.

    Raises:
        ValidationError: quote not owned, or it already has a project.
    """
    if quote.owner_id != owner.id:
        raise ValidationError("Cotización no encontrada.")
    if Project.objects.filter(quote=quote).exists():
        raise ValidationError("Esta cotización ya tiene un proyecto asociado")

    with transaction.atomic():
        project = Project.objects.create(owner=owner, quote=quote)
        quote.status = Quote.Status.IN_PROJECT
        quote.save(update_fields=["status", "updated_at"])
    logger.info("Project started", extra={"project_id": str(project.pk)})
    return project


@transaction.atomic
def register_progress(
    *,
    project: Project,
    quote_item: QuoteItem,
    date,
    quantity: Decimal | None = None,
    worker=None,
) -> Progress:
    """Record an advance on a quote item, by quantity.

    The advance may say WHO did it. When it does, it carries the labour price
    agreed with that person —copied here, not looked up later— because that is
    what turns work done into money owed.

    Raises:
        ValidationError: item not in the project, non-positive advance, an
            advance that would exceed the pending quantity, a worker from another
            account or one with no agreed price; also if the project is finished.
    """
    if project.status == Project.Status.FINISHED:
        raise ValidationError("El proyecto está finalizado")
    if quote_item.quote_id != project.quote_id:
        raise ValidationError("La partida no pertenece a este proyecto.")

    if quantity is None or quantity <= 0:
        raise ValidationError("El avance debe ser mayor a 0")

    already = sum((p.quantity for p in quote_item.progresses.all()), Decimal("0"))
    pending = quote_item.quantity - already
    if quantity > pending:
        raise ValidationError(f"El avance supera la cantidad pendiente ({pending})")

    labor_unit_price = None
    if worker is not None:
        # Import local: el personal conoce los proyectos, y al revés sólo aquí.
        from apps.staff.services import labor_unit_price_for

        if worker.owner_id != project.owner_id:
            raise ValidationError("Personal no encontrado.")
        labor_unit_price = labor_unit_price_for(quote_item=quote_item, worker=worker)
        if labor_unit_price is None:
            raise ValidationError(
                f"Falta decir cuánto se le paga a {worker.name} por {quote_item.name}"
            )

    return Progress.objects.create(
        project=project,
        quote_item=quote_item,
        quantity=quantity,
        date=date,
        worker=worker,
        labor_unit_price=labor_unit_price,
    )


def add_evidence(*, progress: Progress, image) -> Evidence:
    """Attach an image to a progress entry.

    Raises:
        ValidationError: the file is not an image or exceeds the size limit.
    """
    content_type = getattr(image, "content_type", "") or ""
    if not content_type.startswith("image/"):
        raise ValidationError("Solo se permiten archivos de imagen")
    if image.size > MAX_IMAGE_BYTES:
        raise ValidationError("La imagen supera el tamaño máximo permitido")
    return Evidence.objects.create(progress=progress, image=image)


def build_project_summary(*, project: Project) -> dict:
    """Build the closing summary document (work, dates, payments, totals)."""
    # Local import avoids a circular import with the payments app.
    from apps.payments.services import pending_balance, total_paid
    from apps.projects.selectors import advanced_value, quoted_value

    progresses = [
        {
            "date": progress.date,
            "item": progress.quote_item.name,
            "quantity": progress.quantity,
            "earned_value": progress.earned_value,
        }
        for progress in project.progresses.all()
    ]
    payments = [
        {"date": payment.date, "amount": payment.amount}
        for payment in project.payments.all()
    ]
    return {
        "status": project.status,
        "client_name": project.quote.client.name,
        "quoted_value": quoted_value(project),
        "advanced_value": advanced_value(project),
        "total_paid": total_paid(project),
        "pending_balance": pending_balance(project),
        "progresses": progresses,
        "payments": payments,
    }


def finalize_project(*, project: Project, confirm: bool = False) -> dict:
    """Finalize a project and produce its summary document.

    If a pending balance remains and the caller has not confirmed, the project is
    left open and a warning is raised (the client must confirm explicitly).

    Raises:
        ValidationError: project already finished, or pending balance without
            explicit confirmation.
    """
    from apps.payments.services import pending_balance

    if project.status == Project.Status.FINISHED:
        raise ValidationError("El proyecto ya está finalizado")

    pending = pending_balance(project)
    if pending > 0 and not confirm:
        raise ValidationError(
            f"El proyecto tiene un saldo pendiente de cobro de {pending}"
        )

    project.status = Project.Status.FINISHED
    project.save(update_fields=["status", "updated_at"])
    logger.info("Project finalized", extra={"project_id": str(project.pk)})
    return build_project_summary(project=project)
