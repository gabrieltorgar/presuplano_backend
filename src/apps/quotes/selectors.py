"""Quotes read queries (account-scoped)."""

from decimal import Decimal

from django.db.models import DecimalField, ExpressionWrapper, F, QuerySet, Sum
from django.db.models.functions import Coalesce

from apps.quotes.models import Quote

MONEY_FIELD = DecimalField(max_digits=20, decimal_places=6)


def quotes_of(*, owner) -> QuerySet[Quote]:
    """Las cotizaciones de la cuenta, sin sumas: las que se bloquean para cambiarlas.

    ``select_for_update`` no admite el ``GROUP BY`` de la lista; los servicios
    releen aquí la fila que van a cambiar (SEC-03, iteracion-26 #20).
    """
    return Quote.objects.filter(owner=owner)


def list_quotes_for_owner(*, owner) -> QuerySet[Quote]:
    """Return the owner's quotes with items + client prefetched (no N+1).

    Each line comes with its rooms (iteracion-25), also prefetched.

    ``total`` and ``client_name`` come computed by the database so the list
    can be ordered by amount or by client across every page (US-13,
    iteracion-17). The line is not rounded to cents here: for ordering, the
    difference with the total the serializer shows is under a cent.
    """
    line = ExpressionWrapper(
        F("items__quantity") * F("items__unit_price"), output_field=MONEY_FIELD
    )
    return (
        Quote.objects.filter(owner=owner)
        .select_related("client", "plan")
        .prefetch_related("items__rooms")
        .annotate(
            total=Coalesce(Sum(line), Decimal("0"), output_field=MONEY_FIELD),
            client_name=F("client__name"),
        )
    )
