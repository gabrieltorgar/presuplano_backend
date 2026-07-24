"""Payments read queries (account-scoped)."""

from django.db.models import QuerySet

from apps.payments.models import Payment
from apps.projects.models import Project


def list_payments_for_owner(
    *, owner, project_id: str | None = None
) -> QuerySet[Payment]:
    """Return the owner's payments, optionally filtered by project."""
    queryset = Payment.objects.filter(owner=owner)
    if project_id:
        queryset = queryset.filter(project_id=project_id)
    return queryset


def get_owned_project(*, owner, project_id: str | None) -> Project | None:
    """Return the owner's project by id, or ``None`` (tenant-scoped lookup)."""
    if not project_id:
        return None
    return Project.objects.filter(id=project_id, owner=owner).first()
