"""Reusable abstract models."""

import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _


class TimestampedModel(models.Model):
    """Adds self-managed ``created_at`` / ``updated_at`` timestamps."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("creado en"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("actualizado en"))

    class Meta:
        abstract = True
        ordering = ["-created_at"]
