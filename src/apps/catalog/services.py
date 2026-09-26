"""Catalog business logic."""

import logging

from rest_framework.exceptions import ValidationError

from apps.catalog.models import Tariff
from common.wording import quotes_phrase

logger = logging.getLogger("apps")


def quotes_using(tariff: Tariff) -> int:
    """En cuántas cotizaciones distintas aparece el servicio."""
    return tariff.quote_items.values("quote_id").distinct().count()


def delete_tariff(*, tariff: Tariff) -> None:
    """Borra un servicio que no está en ninguna cotización.

    Una cotización guarda su propia copia del nombre y del precio, pero sigue
    apuntando al servicio del que salió: el reparto y el precio de cada
    trabajador se buscan por él. Por eso sólo se borra el que nunca se cotizó.

    Quien del personal lo tenía entre lo que hace, deja de tenerlo: no queda
    un trato apuntando a un servicio que ya no existe.

    Raises:
        ValidationError: el servicio está en al menos una cotización.
    """
    count = quotes_using(tariff)
    if count:
        raise ValidationError(
            f"No se puede borrar: el servicio está en {quotes_phrase(count)}."
        )
    tariff_id = str(tariff.pk)
    tariff.delete()
    logger.info("Tariff deleted", extra={"tariff_id": tariff_id})
