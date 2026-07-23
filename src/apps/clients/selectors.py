"""Clients read queries (account-scoped)."""

from django.db.models import QuerySet

from apps.clients.models import Client


def list_clients_for_owner(*, owner) -> QuerySet[Client]:
    """Return the clients that belong to ``owner`` (tenant isolation)."""
    return Client.objects.filter(owner=owner)
