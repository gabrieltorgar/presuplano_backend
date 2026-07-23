"""Quotes read queries (account-scoped)."""

from django.db.models import QuerySet

from apps.quotes.models import Quote


def list_quotes_for_owner(*, owner) -> QuerySet[Quote]:
    """Return the owner's quotes with items + client prefetched (no N+1)."""
    return (
        Quote.objects.filter(owner=owner)
        .select_related("client")
        .prefetch_related("items")
    )
