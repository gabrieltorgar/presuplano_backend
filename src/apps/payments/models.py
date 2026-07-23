"""Payments model: a payment against a project, optionally tied to an element."""

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from common.models import TimestampedModel


class Payment(TimestampedModel):
    """A payment received on a project (total or partial)."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="payments",
        verbose_name=_("propietario"),
    )
    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.CASCADE,
        related_name="payments",
        verbose_name=_("proyecto"),
    )
    quote_item = models.ForeignKey(
        "quotes.QuoteItem",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payments",
        verbose_name=_("partida cubierta"),
    )
    amount = models.DecimalField(
        max_digits=12, decimal_places=2, verbose_name=_("monto")
    )
    date = models.DateField(verbose_name=_("fecha"))

    class Meta:
        db_table = "payments_payment"
        ordering = ["date", "created_at"]
        verbose_name = _("pago")
        verbose_name_plural = _("pagos")

    def __str__(self) -> str:
        return f"Pago {self.amount}"
