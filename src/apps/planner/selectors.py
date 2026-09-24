"""Planner read queries (account-scoped)."""

from django.db.models import QuerySet

from apps.planner.models import Plan


def list_plans_for_owner(*, owner) -> QuerySet[Plan]:
    """Return the owner's plans (tenant isolation)."""
    return Plan.objects.filter(owner=owner)
