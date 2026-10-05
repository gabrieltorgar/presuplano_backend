"""Quotes business logic (all domain operations live here)."""

import logging
from decimal import Decimal

from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.catalog.models import Tariff
from apps.clients.models import Client
from apps.quotes.models import DEFAULT_VALIDITY_DAYS, Quote, QuoteItem

logger = logging.getLogger("apps")


def _ensure_owned(*, owner, client: Client, items_data: list[dict]) -> None:
    """Reject a payload referencing another account's client or services."""
    if client.owner_id != owner.id:
        raise ValidationError("Cliente no encontrado.")
    for item in items_data:
        if item["tariff"].owner_id != owner.id:
            raise ValidationError("Servicio no encontrado.")


def _create_item(
    *,
    quote: Quote,
    tariff: Tariff,
    quantity: Decimal,
    unit_price: Decimal | None = None,
) -> QuoteItem:
    """Create a line item snapshotting the service's name, unit and price.

    ``unit_price`` overrides the catalogue price for this quote only — the price
    agreed with this client — and the service keeps its own.
    """
    return QuoteItem.objects.create(
        quote=quote,
        tariff=tariff,
        name=tariff.name,
        unit_type=tariff.unit_type,
        unit_price=tariff.unit_price if unit_price is None else unit_price,
        quantity=quantity,
    )


@transaction.atomic
def create_quote(
    *,
    owner,
    client: Client,
    items_data: list[dict],
    notes: str | None = None,
    validity_days: int | None = None,
) -> Quote:
    """Create a draft quote for ``client`` with the given line items.

    Without a validity it gets the house one (20 days), which is what every
    quote had before it could be changed.
    """
    _ensure_owned(owner=owner, client=client, items_data=items_data)
    quote = Quote.objects.create(
        owner=owner,
        client=client,
        notes=(notes or "").strip(),
        validity_days=validity_days or DEFAULT_VALIDITY_DAYS,
    )
    for item in items_data:
        _create_item(
            quote=quote,
            tariff=item["tariff"],
            quantity=item["quantity"],
            unit_price=item.get("unit_price"),
        )
    logger.info("Quote created", extra={"quote_id": str(quote.pk)})
    return quote


@transaction.atomic
def update_quote(
    *,
    quote: Quote,
    client: Client,
    items_data: list[dict],
    notes: str | None = None,
    validity_days: int | None = None,
) -> Quote:
    """Replace a quote's client and items; blocked once it is a project.

    A quote can be corrected as many times as the negotiation takes — its
    document is rebuilt from it every time — and stops changing when work has
    started on it, because from then on there are advances measured against it.
    ``notes`` and ``validity_days`` left out (``None``) keep what it had.

    Raises:
        ValidationError: the quote is already a project.
    """
    if quote.status == Quote.Status.IN_PROJECT:
        raise ValidationError(
            "La cotización ya es un proyecto en marcha; no se puede modificar"
        )
    _ensure_owned(owner=quote.owner, client=client, items_data=items_data)
    quote.client = client
    fields = ["client", "updated_at"]
    if notes is not None:
        quote.notes = notes.strip()
        fields.append("notes")
    if validity_days is not None:
        quote.validity_days = validity_days
        fields.append("validity_days")
    quote.save(update_fields=fields)
    quote.items.all().delete()
    for item in items_data:
        _create_item(
            quote=quote,
            tariff=item["tariff"],
            quantity=item["quantity"],
            unit_price=item.get("unit_price"),
        )
    return quote


@transaction.atomic
def delete_quote(*, quote: Quote) -> None:
    """Borra una cotización que todavía no es proyecto, con sus partidas.

    Los servicios que se dieron de alta sólo para ella —los que no están en el
    catálogo— se van con ella si ninguna otra cotización ni nadie del personal
    los usa: nadie más puede verlos ni elegirlos, así que quedarían huérfanos.

    Raises:
        ValidationError: la cotización ya es un proyecto.
    """
    # Import local: los proyectos conocen las cotizaciones, no al revés.
    from apps.projects.models import Project

    if Project.objects.filter(quote=quote).exists():
        raise ValidationError("No se puede borrar: la cotización ya es un proyecto.")

    unique_ids = list(
        quote.items.filter(tariff__in_catalog=False).values_list("tariff_id", flat=True)
    )
    quote_id = str(quote.pk)
    quote.delete()
    Tariff.objects.filter(
        id__in=unique_ids, quote_items__isnull=True, worker_services__isnull=True
    ).delete()
    logger.info("Quote deleted", extra={"quote_id": quote_id})
