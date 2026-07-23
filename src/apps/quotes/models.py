"""Quotes models: Quote and its QuoteItem line items.

Each line item snapshots the tariff's name, unit type and unit price at quoting
time, so later tariff edits never change an already-issued quote (US-05 edge).
"""

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from common.models import TimestampedModel


class Quote(TimestampedModel):
    """A quote for a client, composed of line items with an automatic total."""

    class Status(models.TextChoices):
        DRAFT = "draft", _("Borrador")
        DOCUMENT_GENERATED = "document_generated", _("Documento generado")
        IN_PROJECT = "in_project", _("En proyecto")

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="quotes",
        verbose_name=_("propietario"),
    )
    client = models.ForeignKey(
        "clients.Client",
        on_delete=models.PROTECT,
        related_name="quotes",
        verbose_name=_("cliente"),
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        verbose_name=_("estado"),
    )

    class Meta:
        db_table = "quotes_quote"
        ordering = ["-created_at"]
        verbose_name = _("cotización")
        verbose_name_plural = _("cotizaciones")

    def __str__(self) -> str:
        return f"Cotización {self.pk} — {self.client}"


class QuoteItem(TimestampedModel):
    """A line item: a snapshot of a tariff plus a quantity."""

    quote = models.ForeignKey(
        Quote,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name=_("cotización"),
    )
    tariff = models.ForeignKey(
        "catalog.Tariff",
        on_delete=models.PROTECT,
        related_name="quote_items",
        verbose_name=_("tarifa"),
    )
    name = models.CharField(max_length=150, verbose_name=_("nombre"))
    unit_type = models.CharField(max_length=20, verbose_name=_("tipo de unidad"))
    unit_price = models.DecimalField(
        max_digits=12, decimal_places=2, verbose_name=_("precio unitario")
    )
    quantity = models.DecimalField(
        max_digits=12, decimal_places=2, verbose_name=_("cantidad")
    )

    class Meta:
        db_table = "quotes_quote_item"
        ordering = ["created_at"]
        verbose_name = _("partida")
        verbose_name_plural = _("partidas")

    @property
    def subtotal(self) -> Decimal:
        """Line subtotal = quantity × snapshotted unit price (pure fields)."""
        return self.quantity * self.unit_price

    def __str__(self) -> str:
        return f"{self.name} × {self.quantity}"
