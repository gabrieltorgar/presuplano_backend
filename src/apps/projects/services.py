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
    """Start a project from a documented quote.

    Raises:
        ValidationError: quote not owned, still a draft, or already has a project.
    """
    if quote.owner_id != owner.id:
        raise ValidationError("Cotización no encontrada.")
    if quote.status == Quote.Status.DRAFT:
        raise ValidationError(
            "Genera el documento de la cotización antes de iniciar el proyecto"
        )
    if Project.objects.filter(quote=quote).exists():
        raise ValidationError("Esta cotización ya tiene un proyecto asociado")

    with transaction.atomic():
        project = Project.objects.create(owner=owner, quote=quote)
        quote.status = Quote.Status.IN_PROJECT
        quote.save(update_fields=["status", "updated_at"])
    logger.info("Project started", extra={"project_id": str(project.pk)})
    return project


def _normalize_advanced_quantity(
    *, quote_item: QuoteItem, quantity: Decimal | None, percentage: Decimal | None
) -> Decimal:
    """Turn a quantity or percentage into an advanced quantity for the item."""
    if quantity is not None:
        return quantity
    if percentage is not None:
        return (percentage / Decimal("100")) * quote_item.quantity
    raise ValidationError("Indica una cantidad o un porcentaje de avance.")


@transaction.atomic
def register_progress(
    *,
    project: Project,
    quote_item: QuoteItem,
    date,
    quantity: Decimal | None = None,
    percentage: Decimal | None = None,
) -> Progress:
    """Record an advance on a quote item, by quantity or percentage.

    Raises:
        ValidationError: item not in the project, non-positive advance, or an
            advance that would exceed the quoted quantity; also if the project is
            finished.
    """
    if project.status == Project.Status.FINISHED:
        raise ValidationError("El proyecto está finalizado")
    if quote_item.quote_id != project.quote_id:
        raise ValidationError("La partida no pertenece a este proyecto.")

    advanced = _normalize_advanced_quantity(
        quote_item=quote_item, quantity=quantity, percentage=percentage
    )
    if advanced <= 0:
        raise ValidationError("El avance debe ser mayor a 0")

    already = sum((p.quantity for p in quote_item.progresses.all()), Decimal("0"))
    if already + advanced > quote_item.quantity:
        raise ValidationError(
            f"El avance supera la cantidad cotizada ({quote_item.quantity})"
        )

    return Progress.objects.create(
        project=project, quote_item=quote_item, quantity=advanced, date=date
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
