"""Projects read queries (account-scoped) + value computations."""

from decimal import Decimal

from django.db.models import (
    Case,
    DecimalField,
    ExpressionWrapper,
    F,
    OuterRef,
    QuerySet,
    Subquery,
    Sum,
    Value,
    When,
)
from django.db.models.functions import Coalesce

from apps.projects.models import Evidence, Progress, Project
from apps.quotes.models import QuoteItem

MONEY_FIELD = DecimalField(max_digits=20, decimal_places=6)


def _money(subquery) -> Coalesce:
    """A total from a subquery, zero when there is nothing to add."""
    return Coalesce(
        Subquery(subquery, output_field=MONEY_FIELD),
        Decimal("0"),
        output_field=MONEY_FIELD,
    )


def projects_of(*, owner) -> QuerySet[Project]:
    """Los proyectos de la cuenta, sin sumas: los que se bloquean para cambiarlos.

    Los servicios releen aquí, con ``select_for_update``, la fila que van a
    cambiar (SEC-03, iteracion-26 #20).
    """
    return Project.objects.filter(owner=owner)


def project_rows_for_owner(*, owner) -> QuerySet[Project]:
    """The owner's projects as the list shows them: no progress or photos.

    ``quoted_value``, ``advanced_value`` and ``progress_percentage`` come
    computed by the database so the list orders by them across every page
    (US-67, iteracion-17). Each total is its own subquery: adding the quote
    lines and the progress entries in one join would multiply one by the other.
    The row still shows the values computed in Python —the same ones the
    project's screen shows— from the lines and entries of that page only.
    """
    quoted = (
        QuoteItem.objects.filter(quote=OuterRef("quote"))
        .order_by()
        .values("quote")
        .annotate(
            total=Sum(
                ExpressionWrapper(
                    F("quantity") * F("unit_price"), output_field=MONEY_FIELD
                )
            )
        )
        .values("total")
    )
    advanced = (
        Progress.objects.filter(project=OuterRef("pk"))
        .order_by()
        .values("project")
        .annotate(
            total=Sum(
                ExpressionWrapper(
                    F("quantity") * F("quote_item__unit_price"),
                    output_field=MONEY_FIELD,
                )
            )
        )
        .values("total")
    )
    return (
        Project.objects.filter(owner=owner)
        .select_related("quote", "quote__client")
        .prefetch_related("quote__items", "progresses__quote_item")
        .annotate(
            quoted_value=_money(quoted),
            advanced_value=_money(advanced),
            client_name=F("quote__client__name"),
        )
        .annotate(
            progress_percentage=Case(
                When(quoted_value=0, then=Value(Decimal("0"))),
                default=F("advanced_value") * 100 / F("quoted_value"),
                output_field=MONEY_FIELD,
            )
        )
    )


def list_projects_for_owner(*, owner) -> QuerySet[Project]:
    """Return the owner's projects with everything their detail shows (no N+1).

    The detail no longer carries the progress entries and their photos: they
    come by pages from ``progress_rows_for_owner`` (iteracion-28 #16).
    """
    return project_rows_for_owner(owner=owner).prefetch_related(
        "quote__items__progresses",
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
    return Progress.objects.filter(project__owner=owner).select_related(
        "quote_item", "project", "worker"
    )


def progress_rows_for_owner(*, owner) -> QuerySet[Progress]:
    """The owner's progress entries as their list shows them, photos included.

    One query for the page and one for the photos of its rows, whatever the
    page size (US-113, iteracion-28 #16).
    """
    return progresses_for_owner(owner=owner).prefetch_related("evidences")


def evidences_for_owner(*, owner) -> QuerySet[Evidence]:
    """Las fotos de los avances de los proyectos de la cuenta."""
    return Evidence.objects.filter(progress__project__owner=owner).select_related(
        "progress__project"
    )
