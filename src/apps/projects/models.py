"""Projects models: Project, Progress (avance) and photographic Evidence.

A project is started from a documented quote. Progress is recorded against a
quote line item, by quantity or percentage (both normalized to an advanced
quantity). Earned value = advanced quantity × the item's snapshotted unit price.
"""

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from common.models import TimestampedModel
from common.uploads import evidence_upload_to


class Project(TimestampedModel):
    """A project tracking the execution and payment of a quote."""

    class Status(models.TextChoices):
        IN_PROGRESS = "in_progress", _("En curso")
        FINISHED = "finished", _("Finalizado")

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="projects",
        verbose_name=_("propietario"),
    )
    quote = models.OneToOneField(
        "quotes.Quote",
        on_delete=models.PROTECT,
        related_name="project",
        verbose_name=_("cotización"),
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.IN_PROGRESS,
        verbose_name=_("estado"),
    )

    class Meta:
        db_table = "projects_project"
        ordering = ["-created_at"]
        verbose_name = _("proyecto")
        verbose_name_plural = _("proyectos")

    def __str__(self) -> str:
        return f"Proyecto {self.pk}"


class Progress(TimestampedModel):
    """An advance on a quote line item (normalized to an advanced quantity)."""

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="progresses",
        verbose_name=_("proyecto"),
    )
    quote_item = models.ForeignKey(
        "quotes.QuoteItem",
        on_delete=models.PROTECT,
        related_name="progresses",
        verbose_name=_("partida"),
    )
    quantity = models.DecimalField(
        max_digits=12, decimal_places=2, verbose_name=_("cantidad avanzada")
    )
    date = models.DateField(verbose_name=_("fecha"))

    class Meta:
        db_table = "projects_progress"
        ordering = ["date", "created_at"]
        verbose_name = _("avance")
        verbose_name_plural = _("avances")

    @property
    def earned_value(self) -> Decimal:
        """Earned value = advanced quantity × snapshotted unit price."""
        return self.quantity * self.quote_item.unit_price


class Evidence(TimestampedModel):
    """A photograph backing a progress entry."""

    progress = models.ForeignKey(
        Progress,
        on_delete=models.CASCADE,
        related_name="evidences",
        verbose_name=_("avance"),
    )
    image = models.ImageField(upload_to=evidence_upload_to, verbose_name=_("imagen"))

    class Meta:
        db_table = "projects_evidence"
        ordering = ["created_at"]
        verbose_name = _("evidencia")
        verbose_name_plural = _("evidencias")
