"""Los binarios del editor, guardados en la cuenta (US-101).

A texture or a mesh imported into the planner used to live only in the browser
that imported it: opening the plan on another device drew grey boxes and blank
walls. Here each one is stored once per account, addressed by the very path the
plan document already names it with, and served from the bucket.

The bytes never travel inside the plan document: a scanned background or a
library of textures would blow past any reasonable document size, and the same
texture used in ten plans would be stored ten times.
"""

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from common.models import TimestampedModel
from common.uploads import plan_asset_upload_to


class PlanAsset(TimestampedModel):
    """Una textura o una malla de la cuenta, con la ruta que la nombra."""

    class Kind(models.TextChoices):
        TEXTURE = "texture", _("Textura")
        MODEL = "model", _("Mobiliario")

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="plan_assets",
        verbose_name=_("propietario"),
    )
    kind = models.CharField(
        max_length=10,
        choices=Kind.choices,
        default=Kind.TEXTURE,
        verbose_name=_("tipo"),
    )
    path = models.CharField(
        max_length=400,
        verbose_name=_("ruta"),
        help_text=_("Cómo lo nombra el plano: la misma con la que se vuelve a pedir."),
    )
    file = models.FileField(upload_to=plan_asset_upload_to, verbose_name=_("archivo"))
    size = models.PositiveIntegerField(default=0, verbose_name=_("tamaño en bytes"))

    class Meta:
        db_table = "assets_planasset"
        ordering = ["path"]
        verbose_name = _("archivo del editor")
        verbose_name_plural = _("archivos del editor")
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "path"], name="assets_one_file_per_path"
            )
        ]
        indexes = [models.Index(fields=["owner", "kind"])]

    def __str__(self) -> str:
        return self.path


class CatalogModel(TimestampedModel):
    """Una ficha del catálogo de mobiliario de la cuenta.

    Los bytes de la malla ya viajaban (`PlanAsset`), pero la ficha que la
    nombra —cómo se llama, en qué categoría está, cuánto mide de verdad— se
    quedaba en el navegador que importó la biblioteca: el catálogo aparecía
    vacío en el teléfono aunque el plano dibujara los muebles.

    La ficha se guarda tal como la escribe el editor, igual que el documento
    del plano: el servidor no tiene por qué saber qué es una silla, sólo de
    quién es y con qué id la vuelve a pedir.
    """

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="catalog_models",
        verbose_name=_("propietario"),
    )
    model_id = models.CharField(
        max_length=200,
        verbose_name=_("id del modelo"),
        help_text=_("El id con el que el plano nombra al mueble."),
    )
    fiche = models.JSONField(verbose_name=_("ficha"))

    class Meta:
        db_table = "assets_catalogmodel"
        ordering = ["model_id"]
        verbose_name = _("modelo del catálogo")
        verbose_name_plural = _("modelos del catálogo")
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "model_id"], name="assets_one_model_per_id"
            )
        ]

    def __str__(self) -> str:
        return str(self.fiche.get("name") or self.model_id)
