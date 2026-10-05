"""Clients read queries (account-scoped)."""

from django.db.models import Count, QuerySet

from apps.clients.models import Client


def list_clients_for_owner(*, owner) -> QuerySet[Client]:
    """Return the clients that belong to ``owner`` (tenant isolation).

    Each one carries ``quotes_count``: the list uses it to say, before anyone
    tries, which clients can be deleted.
    """
    return Client.objects.filter(owner=owner).annotate(quotes_count=Count("quotes"))
