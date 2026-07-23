"""Catalog models: per-account Tariff (product/service with unit price)."""

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from common.models import TimestampedModel


class Tariff(TimestampedModel):
    """A product/service with its unit type and price, owned by one account."""

    class UnitType(models.TextChoices):
        SQUARE_METER = "square_meter", _("Metro cuadrado")
        LINEAR_METER = "linear_meter", _("Metro lineal")
        FLOOR_WALL = "floor_wall", _("Piso/Muro")
        UNIT = "unit", _("Unidad")

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="tariffs",
        verbose_name=_("propietario"),
    )
    name = models.CharField(max_length=150, verbose_name=_("nombre"))
    unit_type = models.CharField(
        max_length=20,
        choices=UnitType.choices,
        default=UnitType.SQUARE_METER,
        verbose_name=_("tipo de unidad"),
    )
    unit_price = models.DecimalField(
        max_digits=12, decimal_places=2, verbose_name=_("precio unitario")
    )

    class Meta:
        db_table = "catalog_tariff"
        ordering = ["-created_at"]
        verbose_name = _("tarifa")
        verbose_name_plural = _("tarifas")
        indexes = [models.Index(fields=["owner", "name"])]

    def __str__(self) -> str:
        return f"{self.name} ({self.get_unit_type_display()})"
