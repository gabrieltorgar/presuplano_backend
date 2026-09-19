"""Leads model: a message from someone who is not a customer yet."""

from django.db import models
from django.utils.translation import gettext_lazy as _

from common.models import TimestampedModel

#: Lo que cabe en un mensaje de contacto; más que esto es otra conversación.
MESSAGE_MAX_LENGTH = 1000


class Lead(TimestampedModel):
    """Quien escribió desde la página pública, y cómo devolverle el contacto.

    No pertenece a ninguna cuenta: llega de fuera, antes de que exista una. Se
    lee desde el admin, no por la API: la página deja mensajes, no los consulta.
    """

    name = models.CharField(max_length=150, verbose_name=_("nombre"))
    phone = models.CharField(max_length=30, blank=True, verbose_name=_("teléfono"))
    email = models.EmailField(blank=True, verbose_name=_("correo"))
    message = models.TextField(
        max_length=MESSAGE_MAX_LENGTH, blank=True, verbose_name=_("mensaje")
    )
    handled = models.BooleanField(default=False, verbose_name=_("atendido"))

    class Meta:
        db_table = "leads_lead"
        ordering = ["-created_at"]
        verbose_name = _("contacto")
        verbose_name_plural = _("contactos")

    def __str__(self) -> str:
        return f"{self.name} ({self.phone or self.email})"
