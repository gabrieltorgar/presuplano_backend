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
def create_quote(*, owner, client: Client, items_data: list[dict]) -> Quote:
    """Create a draft quote for ``client`` with the given line items."""
    _ensure_owned(owner=owner, client=client, items_data=items_data)
    quote = Quote.objects.create(owner=owner, client=client)
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
def update_quote(*, quote: Quote, client: Client, items_data: list[dict]) -> Quote:
    """Replace a quote's client and items; blocked once it is a project.

    A quote can be corrected as many times as the negotiation takes — its
    document is rebuilt from it every time — and stops changing when work has
    started on it, because from then on there are advances measured against it.

    Raises:
        ValidationError: the quote is already a project.
    """
    if quote.status == Quote.Status.IN_PROJECT:
        raise ValidationError(
            "La cotización ya es un proyecto en marcha; no se puede modificar"
        )
    _ensure_owned(owner=quote.owner, client=client, items_data=items_data)
    quote.client = client
    quote.save(update_fields=["client", "updated_at"])
    quote.items.all().delete()
    for item in items_data:
        _create_item(
            quote=quote,
            tariff=item["tariff"],
            quantity=item["quantity"],
            unit_price=item.get("unit_price"),
        )
    return quote
