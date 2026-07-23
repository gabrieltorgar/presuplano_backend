"""Clients model: per-account Client."""

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from common.models import TimestampedModel


class Client(TimestampedModel):
    """A client of the account (the person/company being quoted)."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="clients",
        verbose_name=_("propietario"),
    )
    name = models.CharField(max_length=150, verbose_name=_("nombre"))
    phone = models.CharField(max_length=30, blank=True, verbose_name=_("teléfono"))
    email = models.EmailField(blank=True, verbose_name=_("correo"))

    class Meta:
        db_table = "clients_client"
        ordering = ["-created_at"]
        verbose_name = _("cliente")
        verbose_name_plural = _("clientes")
        indexes = [models.Index(fields=["owner", "name"])]

    def __str__(self) -> str:
        return self.name
