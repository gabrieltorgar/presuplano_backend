"""Legal models: quién aceptó qué versión de los documentos, y cuándo."""

import uuid

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class LegalDocumentKind(models.TextChoices):
    TERMS = "terms", _("Términos y condiciones")
    PRIVACY = "privacy", _("Política de privacidad")


class LegalAcceptance(models.Model):
    """La constancia de que una cuenta aceptó una versión de un documento.

    Se guarda la versión, la hora, la dirección IP y el navegador: es lo que
    permite demostrar qué texto se aceptó y desde dónde. Se borra con la
    cuenta, como todo lo demás.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="legal_acceptances",
        verbose_name=_("usuario"),
    )
    document = models.CharField(
        max_length=10, choices=LegalDocumentKind.choices, verbose_name=_("documento")
    )
    version = models.CharField(max_length=40, verbose_name=_("versión"))
    accepted_at = models.DateTimeField(auto_now_add=True, verbose_name=_("aceptado en"))
    ip_address = models.GenericIPAddressField(
        null=True, blank=True, verbose_name=_("dirección IP")
    )
    user_agent = models.CharField(
        max_length=300, blank=True, default="", verbose_name=_("navegador")
    )

    class Meta:
        db_table = "legal_acceptance"
        ordering = ["-accepted_at"]
        verbose_name = _("aceptación")
        verbose_name_plural = _("aceptaciones")
        constraints = [
            models.UniqueConstraint(
                fields=["user", "document", "version"],
                name="legal_one_acceptance_per_version",
            )
        ]

    def __str__(self) -> str:
        return f"{self.user} — {self.document} {self.version}"
