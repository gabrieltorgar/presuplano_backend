"""Catalog read queries (account-scoped)."""

from django.db.models import Count, QuerySet

from apps.catalog.models import Tariff


def list_tariffs_for_owner(*, owner) -> QuerySet[Tariff]:
    """Return the owner's catalog tariffs (tenant isolation).

    Tariffs created only for a specific quote (``in_catalog=False``) are excluded
    so they never pollute the catalog nor other quotes.

    Each one carries ``quotes_count`` —distinct quotes it appears in— so the
    list can say, before anyone tries, which services can be deleted.
    """
    return Tariff.objects.filter(owner=owner, in_catalog=True).annotate(
        quotes_count=Count("quote_items__quote", distinct=True)
    )
