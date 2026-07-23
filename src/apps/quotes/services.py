"""Quotes business logic (all domain operations live here)."""

import logging
from decimal import Decimal

from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.catalog.models import Tariff
from apps.clients.models import Client
from apps.quotes.models import Quote, QuoteItem

logger = logging.getLogger("apps")


def _ensure_owned(*, owner, client: Client, items_data: list[dict]) -> None:
    """Reject a payload referencing another account's client or tariffs."""
    if client.owner_id != owner.id:
        raise ValidationError("Cliente no encontrado.")
    for item in items_data:
        if item["tariff"].owner_id != owner.id:
            raise ValidationError("Tarifa no encontrada.")


def _create_item(*, quote: Quote, tariff: Tariff, quantity: Decimal) -> QuoteItem:
    """Create a line item snapshotting the tariff's name, unit and price."""
    return QuoteItem.objects.create(
        quote=quote,
        tariff=tariff,
        name=tariff.name,
        unit_type=tariff.unit_type,
        unit_price=tariff.unit_price,
        quantity=quantity,
    )


@transaction.atomic
def create_quote(*, owner, client: Client, items_data: list[dict]) -> Quote:
    """Create a draft quote for ``client`` with the given line items."""
    _ensure_owned(owner=owner, client=client, items_data=items_data)
    quote = Quote.objects.create(owner=owner, client=client)
    for item in items_data:
        _create_item(quote=quote, tariff=item["tariff"], quantity=item["quantity"])
    logger.info("Quote created", extra={"quote_id": str(quote.pk)})
    return quote


@transaction.atomic
def update_quote(*, quote: Quote, client: Client, items_data: list[dict]) -> Quote:
    """Replace a draft quote's client and items; blocked once documented.

    Raises:
        ValidationError: the quote already has a generated document.
    """
    if quote.status != Quote.Status.DRAFT:
        raise ValidationError(
            "La cotización ya tiene documento generado; crea una nueva versión "
            "para modificarla"
        )
    _ensure_owned(owner=quote.owner, client=client, items_data=items_data)
    quote.client = client
    quote.save(update_fields=["client", "updated_at"])
    quote.items.all().delete()
    for item in items_data:
        _create_item(quote=quote, tariff=item["tariff"], quantity=item["quantity"])
    return quote


def generate_quote_document(*, quote: Quote) -> Quote:
    """Mark the quote as documented. Idempotent (regenerating is a no-op).

    Raises:
        ValidationError: the quote has no line items.
    """
    if not quote.items.exists():
        raise ValidationError(
            "No se puede generar el documento de una cotización sin partidas"
        )
    if quote.status == Quote.Status.DRAFT:
        quote.status = Quote.Status.DOCUMENT_GENERATED
        quote.save(update_fields=["status", "updated_at"])
        logger.info("Quote document generated", extra={"quote_id": str(quote.pk)})
    return quote
