"""Staff models: who does the work, what they were handed and what they are paid.

The account already tracked the money coming in —quote, progress, payment— from
the client's side. This is the other side: a `Worker` (a person or a company) is
handed part of a project's line items (`Assignment`), executes them (a `Progress`
that now says who did it), and is paid for what they executed (`WorkerPayment`).

Two figures, deliberately kept apart: what is COMMITTED —everything handed out—
and what is ACCRUED —what has actually been executed—. You pay against the
accrued; the committed is what is still owed by the end if nothing changes.
"""

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from common.models import TimestampedModel


class Worker(TimestampedModel):
    """Alguien que ejecuta servicios: una persona o una empresa."""

    class Kind(models.TextChoices):
        PERSON = "person", _("Persona")
        COMPANY = "company", _("Empresa")

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="workers",
        verbose_name=_("propietario"),
    )
    kind = models.CharField(
        max_length=10,
        choices=Kind.choices,
        default=Kind.PERSON,
        verbose_name=_("tipo"),
    )
    name = models.CharField(max_length=150, verbose_name=_("nombre"))
    phone = models.CharField(
        max_length=30, blank=True, default="", verbose_name=_("teléfono")
    )
    email = models.EmailField(blank=True, default="", verbose_name=_("correo"))
    notes = models.TextField(blank=True, default="", verbose_name=_("notas"))
    is_self = models.BooleanField(
        default=False,
        verbose_name=_("soy yo"),
        help_text=_(
            "El propio despacho. Se le reparte trabajo para saber qué parte hace, "
            "pero no se le debe ni se le paga."
        ),
    )
    is_active = models.BooleanField(default=True, verbose_name=_("activo"))

    class Meta:
        db_table = "staff_worker"
        # «Yo» primero: es a quien más se le reparte.
        ordering = ["-is_self", "name"]
        verbose_name = _("personal")
        verbose_name_plural = _("personal")
        constraints = [
            models.UniqueConstraint(
                fields=["owner"],
                condition=Q(is_self=True),
                name="staff_one_self_per_owner",
            )
        ]
        indexes = [models.Index(fields=["owner", "name"])]

    def __str__(self) -> str:
        return self.name


class WorkerService(TimestampedModel):
    """Un servicio que ese personal hace, y a cómo se le paga.

    The price is what I PAY, which has nothing to do with what I charge the
    client for the same service: the difference is the margin of the job.
    """

    worker = models.ForeignKey(
        Worker,
        on_delete=models.CASCADE,
        related_name="services",
        verbose_name=_("personal"),
    )
    tariff = models.ForeignKey(
        "catalog.Tariff",
        on_delete=models.CASCADE,
        related_name="worker_services",
        verbose_name=_("servicio"),
    )
    unit_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("precio unitario que se le paga"),
        help_text=_("Vacío: se acuerda al repartir el trabajo."),
    )

    class Meta:
        db_table = "staff_workerservice"
        ordering = ["tariff__name"]
        verbose_name = _("servicio del personal")
        verbose_name_plural = _("servicios del personal")
        constraints = [
            models.UniqueConstraint(
                fields=["worker", "tariff"], name="staff_service_once_per_worker"
            )
        ]

    def __str__(self) -> str:
        return f"{self.worker} — {self.tariff}"


class Assignment(TimestampedModel):
    """El reparto: cuánto de una partida le tocó a quién, y a qué precio.

    The price is snapshotted here, as the quote does with the tariff: agreeing a
    new rate with someone must not rewrite what was already handed out.
    """

    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.CASCADE,
        related_name="assignments",
        verbose_name=_("proyecto"),
    )
    quote_item = models.ForeignKey(
        "quotes.QuoteItem",
        on_delete=models.CASCADE,
        related_name="assignments",
        verbose_name=_("partida"),
    )
    worker = models.ForeignKey(
        Worker,
        on_delete=models.PROTECT,
        related_name="assignments",
        verbose_name=_("personal"),
    )
    quantity = models.DecimalField(
        max_digits=12, decimal_places=2, verbose_name=_("cantidad repartida")
    )
    unit_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name=_("precio unitario que se le paga"),
    )
    note = models.CharField(
        max_length=255, blank=True, default="", verbose_name=_("nota")
    )

    class Meta:
        db_table = "staff_assignment"
        ordering = ["created_at"]
        verbose_name = _("reparto")
        verbose_name_plural = _("repartos")
        constraints = [
            models.UniqueConstraint(
                fields=["quote_item", "worker"], name="staff_one_share_per_item_worker"
            )
        ]

    @property
    def committed_value(self) -> Decimal:
        """Lo comprometido con esa persona en esta partida."""
        return self.quantity * self.unit_price

    def __str__(self) -> str:
        return f"{self.worker} — {self.quote_item.name}"


class WorkerPayment(TimestampedModel):
    """Un pago al personal. Puede ser de un proyecto o de la semana entera."""

    class Method(models.TextChoices):
        CASH = "cash", _("Efectivo")
        TRANSFER = "transfer", _("Transferencia")

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="worker_payments",
        verbose_name=_("propietario"),
    )
    worker = models.ForeignKey(
        Worker,
        on_delete=models.PROTECT,
        related_name="payments",
        verbose_name=_("personal"),
    )
    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="worker_payments",
        verbose_name=_("proyecto"),
    )
    amount = models.DecimalField(
        max_digits=12, decimal_places=2, verbose_name=_("monto")
    )
    method = models.CharField(
        max_length=12,
        choices=Method.choices,
        default=Method.CASH,
        verbose_name=_("método de pago"),
    )
    date = models.DateField(verbose_name=_("fecha"))
    note = models.CharField(
        max_length=255, blank=True, default="", verbose_name=_("nota")
    )

    class Meta:
        db_table = "staff_workerpayment"
        ordering = ["date", "created_at"]
        verbose_name = _("pago a personal")
        verbose_name_plural = _("pagos a personal")

    def __str__(self) -> str:
        return f"Pago {self.amount} a {self.worker}"
