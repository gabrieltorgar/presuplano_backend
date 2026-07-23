"""Projects read queries (account-scoped) + value computations."""

from decimal import Decimal

from django.db.models import QuerySet

from apps.projects.models import Progress, Project


def list_projects_for_owner(*, owner) -> QuerySet[Project]:
    """Return the owner's projects with related data prefetched (no N+1)."""
    return (
        Project.objects.filter(owner=owner)
        .select_related("quote", "quote__client")
        .prefetch_related("quote__items", "progresses", "progresses__quote_item")
    )


def quoted_value(project: Project) -> Decimal:
    """Total quoted value = sum of quote line subtotals."""
    return sum((item.subtotal for item in project.quote.items.all()), Decimal("0"))


def advanced_value(project: Project) -> Decimal:
    """Total advanced (earned) value = sum of progress earned values."""
    return sum(
        (progress.earned_value for progress in project.progresses.all()),
        Decimal("0"),
    )


def progresses_for_owner(*, owner) -> QuerySet[Progress]:
    """Progress entries belonging to the owner's projects."""
    return Progress.objects.filter(project__owner=owner).select_related("quote_item")
