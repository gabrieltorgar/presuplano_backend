"""Quotes business logic (all domain operations live here)."""

import logging
from decimal import Decimal

from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.catalog.models import Tariff
from apps.clients.models import Client
from apps.planner.models import Plan
from apps.quotes.models import DEFAULT_VALIDITY_DAYS, Quote, QuoteItem

logger = logging.getLogger("apps")


def _ensure_owned(
    *, owner, client: Client | None, items_data: list[dict], plan: Plan | None = None
) -> None:
    """Reject a payload referencing another account's client, plan or services."""
    if client is not None and client.owner_id != owner.id:
        raise ValidationError("Cliente no encontrado.")
    if plan is not None and plan.owner_id != owner.id:
        raise ValidationError("Plano no encontrado.")
    for item in items_data:
        if item["tariff"].owner_id != owner.id:
            raise ValidationError("Servicio no encontrado.")


def _create_item(
    *,
    quote: Quote,
    tariff: Tariff,
    quantity: Decimal,
    unit_price: Decimal | None = None,
    from_plan: bool = False,
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
        from_plan=from_plan,
    )


@transaction.atomic
def create_quote(
    *,
    owner,
    client: Client,
    items_data: list[dict],
    notes: str | None = None,
    validity_days: int | None = None,
    plan: Plan | None = None,
) -> Quote:
    """Create a draft quote for ``client`` with the given line items.

    Without a validity it gets the house one (20 days), which is what every
    quote had before it could be changed.
    """
    _ensure_owned(owner=owner, client=client, items_data=items_data, plan=plan)
    quote = Quote.objects.create(
        owner=owner,
        client=client,
        plan=plan,
        notes=(notes or "").strip(),
        validity_days=validity_days or DEFAULT_VALIDITY_DAYS,
    )
    for item in items_data:
        _create_item(
            quote=quote,
            tariff=item["tariff"],
            quantity=item["quantity"],
            unit_price=item.get("unit_price"),
            from_plan=bool(item.get("from_plan")),
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
    # La pantalla de la cotización no sabe de planos: lo que no dice si viene
    # del plano conserva lo que era, para que recotizar lo siga reconociendo.
    measured = set(
        quote.items.filter(from_plan=True).values_list("tariff_id", flat=True)
    )
    quote.items.all().delete()
    for item in items_data:
        from_plan = item.get("from_plan")
        _create_item(
            quote=quote,
            tariff=item["tariff"],
            quantity=item["quantity"],
            unit_price=item.get("unit_price"),
            from_plan=item["tariff"].id in measured if from_plan is None else from_plan,
        )
    return quote


@transaction.atomic
def sync_quote_with_plan(*, quote: Quote, plan: Plan, items_data: list[dict]) -> Quote:
    """Brings a draft quote up to date with what its plan measures now (US-95).

    The lines that came from the plan take the new quantities and keep their
    price — what was negotiated is still the deal —; a service the plan no
    longer has leaves; a new one enters. What the architect added by hand is
    not touched.

    Raises:
        ValidationError: the quote is already a project, which does not change.
    """
    if quote.status == Quote.Status.IN_PROJECT:
        raise ValidationError(
            "La cotización ya es un proyecto en marcha; crea una nueva desde el plano"
        )
    _ensure_owned(owner=quote.owner, client=None, items_data=items_data, plan=plan)

    current = {item.tariff_id: item for item in quote.items.filter(from_plan=True)}
    measured = set()
    for data in items_data:
        tariff = data["tariff"]
        measured.add(tariff.id)
        line = current.get(tariff.id)
        if line is None:
            _create_item(
                quote=quote,
                tariff=tariff,
                quantity=data["quantity"],
                unit_price=data.get("unit_price"),
                from_plan=True,
            )
        else:
            line.quantity = data["quantity"]
            line.save(update_fields=["quantity", "updated_at"])
    quote.items.filter(from_plan=True).exclude(tariff_id__in=measured).delete()

    quote.plan = plan
    quote.save(update_fields=["plan", "updated_at"])
    logger.info("Quote synced with its plan", extra={"quote_id": str(quote.pk)})
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
