"""Payments read queries (account-scoped)."""

from django.db.models import QuerySet

from apps.payments.models import Payment


def list_payments_for_owner(
    *, owner, project_id: str | None = None
) -> QuerySet[Payment]:
    """Return the owner's payments, optionally filtered by project."""
    queryset = Payment.objects.filter(owner=owner)
    if project_id:
        queryset = queryset.filter(project_id=project_id)
    return queryset
