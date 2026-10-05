"""El resumen de la cuenta: lo que se ve al abrir la aplicación (US-99).

Read-only, and it owns no data of its own. It answers, in one trip, the
questions an architect opens the app to ask —qué hay en marcha, cuánto de lo
que cotizo se vuelve obra, qué me deben, qué debo y qué se vende— by reading
what the other apps already keep.
"""

from datetime import date
from decimal import Decimal

from django.db.models import Count, DecimalField, ExpressionWrapper, F, Max, Sum
from django.db.models.functions import Coalesce, TruncMonth

from apps.payments.models import Payment
from apps.payments.services import receivable_balance
from apps.projects.models import Progress, Project
from apps.quotes.models import Quote, QuoteItem
from apps.staff.selectors import list_workers_for_owner, worker_totals
from common.money import money

ZERO = Decimal("0.00")

#: Cuántos meses de ingresos se enseñan, con el actual como último.
INCOME_MONTHS = 6

#: Cuántos entran en cada tabla de lo más vendido.
TOP_SERVICES = 10
TOP_CLIENTS = 5
TOP_WORKERS = 5

MONEY_FIELD = DecimalField(max_digits=20, decimal_places=6)


def line_total() -> ExpressionWrapper:
    """Lo que cobra un renglón de cotización.

    `subtotal` is a Python property —it rounds to cents—, and adding thousands
    of rows in memory to paint a table would be paying dearly for two decimals.
    A fresh expression each time: Django resolves them in place, and sharing one
    between two queries makes the second think it is already an aggregate.
    """
    return ExpressionWrapper(F("quantity") * F("unit_price"), output_field=MONEY_FIELD)


def labor_total() -> ExpressionWrapper:
    """Lo que un avance le ganó a quien lo hizo."""
    return ExpressionWrapper(
        F("quantity") * Coalesce(F("labor_unit_price"), Decimal("0")),
        output_field=MONEY_FIELD,
    )


def _sold_items(owner):
    """Los renglones de lo que ya se vendió: cotizaciones vueltas proyecto."""
    return QuoteItem.objects.filter(
        quote__owner=owner, quote__status=Quote.Status.IN_PROJECT
    )


def _last_months(today: date, count: int) -> list[tuple[int, int]]:
    """Los últimos `count` meses, del más viejo al actual."""
    months: list[tuple[int, int]] = []
    year, month = today.year, today.month
    for _ in range(count):
        months.append((year, month))
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    return list(reversed(months))


def monthly_income(*, owner, today: date | None = None) -> list[dict]:
    """Lo cobrado mes a mes, terminando en el mes en curso.

    Income is money RECEIVED, not money earned: what the account can count on
    is what the client has already paid.
    """
    today = today or date.today()
    months = _last_months(today, INCOME_MONTHS)
    first = date(months[0][0], months[0][1], 1)

    rows = (
        Payment.objects.filter(owner=owner, date__gte=first)
        .annotate(bucket=TruncMonth("date"))
        .values("bucket")
        .annotate(total=Sum("amount"))
    )
    collected = {
        (row["bucket"].year, row["bucket"].month): row["total"] for row in rows
    }

    return [
        {
            "month": f"{year:04d}-{month:02d}",
            "amount": money(collected.get((year, month), ZERO)),
        }
        for year, month in months
    ]


def top_services(*, owner) -> list[dict]:
    """Lo que más se vende, por importe vendido."""
    rows = (
        _sold_items(owner)
        .values("tariff_id")
        # Los alias no pueden llamarse como los campos: `quantity` pasaría a
        # ser la suma, y el importe —que multiplica por la cantidad— se
        # calcularía sobre un agregado.
        .annotate(
            label=Max("name"),
            unit=Max("unit_type"),
            sold=Sum("quantity"),
            billed=Sum(line_total()),
        )
        .order_by("-billed")[:TOP_SERVICES]
    )
    return [
        {
            "name": row["label"],
            "unit_type": row["unit"],
            "quantity": money(row["sold"] or ZERO),
            "amount": money(row["billed"] or ZERO),
        }
        for row in rows
    ]


def top_clients(*, owner) -> list[dict]:
    """Quién compra más, por lo que se le ha vendido."""
    rows = (
        _sold_items(owner)
        .values("quote__client_id")
        .annotate(
            label=Max("quote__client__name"),
            billed=Sum(line_total()),
            projects=Count("quote_id", distinct=True),
        )
        .order_by("-billed")[:TOP_CLIENTS]
    )
    return [
        {
            "name": row["label"],
            "projects": row["projects"],
            "amount": money(row["billed"] or ZERO),
        }
        for row in rows
    ]


def top_workers(*, owner) -> list[dict]:
    """Quién trabaja más, por avances ejecutados.

    «Yo» —el propio despacho— queda fuera: no es personal al que contarle
    trabajos, es lo que hace la casa.
    """
    rows = (
        Progress.objects.filter(project__owner=owner, worker__isnull=False)
        .exclude(worker__is_self=True)
        .values("worker_id")
        .annotate(
            label=Max("worker__name"), jobs=Count("id"), earned=Sum(labor_total())
        )
        .order_by("-jobs", "-earned")[:TOP_WORKERS]
    )
    return [
        {
            "name": row["label"],
            "jobs": row["jobs"],
            "amount": money(row["earned"] or ZERO),
        }
        for row in rows
    ]


def build_dashboard(*, owner, today: date | None = None) -> dict:
    """Todo el resumen, en una sola respuesta."""
    quotes = Quote.objects.filter(owner=owner)
    quoted = (
        QuoteItem.objects.filter(quote__owner=owner).aggregate(total=Sum(line_total()))[
            "total"
        ]
        or ZERO
    )
    converted = _sold_items(owner).aggregate(total=Sum(line_total()))["total"] or ZERO

    projects = list(
        Project.objects.filter(owner=owner)
        .select_related("quote")
        .prefetch_related("quote__items", "payments")
    )
    receivable = sum((receivable_balance(project) for project in projects), ZERO)
    payable = sum(
        (
            Decimal(worker_totals(worker)["balance"])
            for worker in list_workers_for_owner(owner=owner)
        ),
        ZERO,
    )

    return {
        "active_projects": sum(
            1 for p in projects if p.status == Project.Status.IN_PROGRESS
        ),
        "quotes_total": quotes.count(),
        "quotes_in_project": quotes.filter(status=Quote.Status.IN_PROJECT).count(),
        "quoted_value": money(quoted),
        "converted_value": money(converted),
        # Cuánto de lo cotizado se vuelve obra, en dinero: dos cotizaciones
        # chicas ganadas y una grande perdida no son un 66 % de nada.
        "conversion_rate": (round(float(converted / quoted * 100), 2) if quoted else 0),
        "receivable": money(receivable),
        "payable": money(payable),
        "monthly_income": monthly_income(owner=owner, today=today),
        "top_services": top_services(owner=owner),
        "top_clients": top_clients(owner=owner),
        "top_workers": top_workers(owner=owner),
    }
