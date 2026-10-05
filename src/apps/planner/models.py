"""Planner models: the floor plans of an account."""

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from common.models import TimestampedModel


class Plan(TimestampedModel):
    """A floor plan, stored whole as the editor serialises it.

    The document travels as one JSON on purpose: it is the editor's own format,
    with its own version number and its own migration path, and the server has
    no business knowing what a wall is. What the server does own is whose plan
    it is, so it can be opened from any device of that account and from no
    other.
    """

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="plans",
        verbose_name=_("propietario"),
    )
    name = models.CharField(max_length=150, verbose_name=_("nombre"))
    document = models.JSONField(verbose_name=_("documento"))

    class Meta:
        db_table = "planner_plan"
        # Lo último que se tocó, primero: es lo que se sigue dibujando.
        ordering = ["-updated_at"]
        verbose_name = _("plano")
        verbose_name_plural = _("planos")
        indexes = [models.Index(fields=["owner", "-updated_at"])]

    def __str__(self) -> str:
        return self.name
