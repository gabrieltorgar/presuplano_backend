"""Clients business logic."""

import logging

from rest_framework.exceptions import ValidationError

from apps.clients.models import Client
from common.wording import quotes_phrase

logger = logging.getLogger("apps")


def delete_client(*, client: Client) -> None:
    """Borra un cliente que no está en ninguna cotización.

    Un cliente con cotizaciones es parte de su historia —el documento lleva su
    nombre, el proyecto cobra a su cuenta—, así que sólo se puede borrar el que
    se capturó y nunca llegó a cotizarse.

    Raises:
        ValidationError: el cliente está en al menos una cotización.
    """
    count = client.quotes.count()
    if count:
        raise ValidationError(
            f"No se puede borrar: el cliente está en {quotes_phrase(count)}."
        )
    client_id = str(client.pk)
    client.delete()
    logger.info("Client deleted", extra={"client_id": client_id})
