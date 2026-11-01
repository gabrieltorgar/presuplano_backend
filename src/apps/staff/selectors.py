"""Staff read queries (account-scoped) + what is owed to each worker."""

from decimal import Decimal

from django.db.models import (
    DecimalField,
    ExpressionWrapper,
    F,
    OuterRef,
    QuerySet,
    Subquery,
    Sum,
    Value,
)
from django.db.models.functions import Coalesce, Greatest

from apps.projects.models import Progress, Project
from apps.staff.models import Assignment, Worker, WorkerPayment
from common.money import money

ZERO = Decimal("0.00")
MONEY_FIELD = DecimalField(max_digits=20, decimal_places=6)


def list_workers_for_owner(*, owner) -> QuerySet[Worker]:
    """Return the owner's staff with everything the totals need (no N+1)."""
    return Worker.objects.filter(owner=owner).prefetch_related(
        "services__tariff", "assignments", "progresses", "payments"
    )


def _money(subquery) -> Coalesce:
    """A total from a subquery, zero when there is nothing to add."""
    return Coalesce(
        Subquery(subquery, output_field=MONEY_FIELD),
        Decimal("0"),
        output_field=MONEY_FIELD,
    )


def worker_rows_for_owner(*, owner) -> QuerySet[Worker]:
    """The owner's staff with ``balance`` computed by the database.

    What is owed today —accrued minus paid, never below zero, as
    ``worker_totals`` says— so the list filters «con saldo» and orders by what
    is owed across every page (US-96, iteracion-17). Accrued and paid are each
    their own subquery: adding both in one join would multiply one by the other.
    """
    accrued = (
        Progress.objects.filter(worker=OuterRef("pk"), labor_unit_price__isnull=False)
        .order_by()
        .values("worker")
        .annotate(
            total=Sum(
                ExpressionWrapper(
                    F("quantity") * F("labor_unit_price"), output_field=MONEY_FIELD
                )
            )
        )
        .values("total")
    )
    paid = (
        WorkerPayment.objects.filter(worker=OuterRef("pk"))
        .order_by()
        .values("worker")
        .annotate(total=Sum("amount"))
        .values("total")
    )
    return (
        list_workers_for_owner(owner=owner)
        .annotate(accrued_total=_money(accrued), paid_total=_money(paid))
        .annotate(
            balance=Greatest(
                F("accrued_total") - F("paid_total"),
                Value(Decimal("0")),
                output_field=MONEY_FIELD,
            )
        )
    )


def staff_totals(*, owner) -> dict:
    """Lo que se le debe hoy a todo el personal y todo lo repartido (US-96).

    The sum of each worker's own figures —the ones the list shows on its rows—
    so the totals above the list are the whole account's, whatever page is on
    screen (iteracion-17).
    """
    owed = committed = ZERO
    for worker in list_workers_for_owner(owner=owner):
        totals = worker_totals(worker)
        owed += Decimal(totals["balance"])
        committed += Decimal(totals["committed_value"])
    return {"balance": money(owed), "committed_value": money(committed)}


def get_owned_worker(*, owner, worker_id) -> Worker | None:
    """Esa persona del personal, si es de la cuenta; si no, ninguna."""
    if not worker_id:
        return None
    return Worker.objects.filter(id=worker_id, owner=owner).first()


def list_assignments_for_owner(
    *, owner, project_id: str | None = None
) -> QuerySet[Assignment]:
    """Return the owner's assignments, optionally filtered by project."""
    queryset = Assignment.objects.filter(project__owner=owner).select_related(
        "worker", "quote_item"
    )
    if project_id:
        queryset = queryset.filter(project_id=project_id)
    return queryset


def list_worker_payments_for_owner(*, owner) -> QuerySet[WorkerPayment]:
    """Return the owner's payments to staff, with who was paid (no N+1).

    The list narrows them with ``?worker=`` and ``?project=``.
    """
    return WorkerPayment.objects.filter(owner=owner).select_related("worker")


def committed_value(worker: Worker, *, project_id: str | None = None) -> Decimal:
    """Todo lo repartido a esa persona: lo que costará si se ejecuta entero."""
    assignments = [
        a
        for a in worker.assignments.all()
        if project_id is None or str(a.project_id) == str(project_id)
    ]
    return sum((a.committed_value for a in assignments), ZERO)


def accrued_value(worker: Worker, *, project_id: str | None = None) -> Decimal:
    """Lo ya ejecutado por esa persona: lo que se le ha ganado hasta hoy."""
    progresses = [
        p
        for p in worker.progresses.all()
        if project_id is None or str(p.project_id) == str(project_id)
    ]
    return sum((p.labor_value for p in progresses), ZERO)


def paid_value(worker: Worker, *, project_id: str | None = None) -> Decimal:
    """Lo que ya se le pagó."""
    payments = [
        p
        for p in worker.payments.all()
        if project_id is None or str(p.project_id) == str(project_id)
    ]
    return sum((p.amount for p in payments), ZERO)


def worker_totals(worker: Worker, *, project_id: str | None = None) -> dict:
    """Las cuatro cifras de una persona: repartido, ejecutado, pagado y saldo.

    The balance is what is owed TODAY —accrued minus paid— and never goes
    negative: money handed over beyond what was executed is an advance, and it
    is reported apart so it does not read as a debt.
    """
    committed = committed_value(worker, project_id=project_id)
    accrued = accrued_value(worker, project_id=project_id)
    paid = paid_value(worker, project_id=project_id)
    return {
        "committed_value": money(committed),
        "accrued_value": money(accrued),
        "total_paid": money(paid),
        "balance": money(max(accrued - paid, ZERO)),
        "advance_balance": money(max(paid - accrued, ZERO)),
    }


def project_distribution(*, project: Project) -> dict:
    """Cómo está repartida cada partida del proyecto, y qué falta por repartir."""
    assignments = list(
        Assignment.objects.filter(project=project).select_related(
            "worker", "quote_item"
        )
    )
    progresses = list(Progress.objects.filter(project=project).select_related("worker"))

    items = []
    for item in project.quote.items.all():
        mine = [a for a in assignments if a.quote_item_id == item.id]
        advances = [p for p in progresses if p.quote_item_id == item.id]
        assigned = sum((a.quantity for a in mine), ZERO)
        advanced = sum((p.quantity for p in advances), ZERO)
        items.append(
            {
                "id": str(item.id),
                "name": item.name,
                "unit_type": item.unit_type,
                "tariff": str(item.tariff_id),
                "quantity": money(item.quantity),
                "assigned_quantity": money(assigned),
                "unassigned_quantity": money(item.quantity - assigned),
                "advanced_quantity": money(advanced),
                "assignments": [
                    {
                        "id": str(a.id),
                        "worker": str(a.worker_id),
                        "worker_name": a.worker.name,
                        "is_self": a.worker.is_self,
                        "quantity": money(a.quantity),
                        "unit_price": money(a.unit_price),
                        "committed_value": money(a.committed_value),
                        "advanced_quantity": money(
                            sum(
                                (
                                    p.quantity
                                    for p in advances
                                    if p.worker_id == a.worker_id
                                ),
                                ZERO,
                            )
                        ),
                        "accrued_value": money(
                            sum(
                                (
                                    p.labor_value
                                    for p in advances
                                    if p.worker_id == a.worker_id
                                ),
                                ZERO,
                            )
                        ),
                    }
                    for a in mine
                ],
            }
        )
    return {"items": items}
