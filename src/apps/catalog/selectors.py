"""Catalog read queries (account-scoped)."""

from django.db.models import QuerySet

from apps.catalog.models import Tariff


def list_tariffs_for_owner(*, owner) -> QuerySet[Tariff]:
    """Return the tariffs that belong to ``owner`` (tenant isolation)."""
    return Tariff.objects.filter(owner=owner)
