"""Staff read queries (account-scoped) + what is owed to each worker."""

from decimal import Decimal

from django.db.models import QuerySet

from apps.projects.models import Progress, Project
from apps.staff.models import Assignment, Worker, WorkerPayment
from common.money import money

ZERO = Decimal("0.00")


def list_workers_for_owner(*, owner) -> QuerySet[Worker]:
    """Return the owner's staff with everything the totals need (no N+1)."""
    return Worker.objects.filter(owner=owner).prefetch_related(
        "services__tariff", "assignments", "progresses", "payments"
    )


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


def list_worker_payments_for_owner(
    *, owner, worker_id: str | None = None, project_id: str | None = None
) -> QuerySet[WorkerPayment]:
    """Return the owner's payments to staff, filtered as asked."""
    queryset = WorkerPayment.objects.filter(owner=owner).select_related("worker")
    if worker_id:
        queryset = queryset.filter(worker_id=worker_id)
    if project_id:
        queryset = queryset.filter(project_id=project_id)
    return queryset


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
