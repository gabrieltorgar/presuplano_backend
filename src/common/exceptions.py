"""Respuestas de error de la API en palabras de la aplicación."""

import logging
import math

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.db.models import ProtectedError, RestrictedError
from rest_framework import status
from rest_framework.exceptions import APIException, Throttled, ValidationError
from rest_framework.serializers import as_serializer_error
from rest_framework.views import exception_handler as drf_exception_handler

from apps.accounts.otp_quota import OTPCooldown

logger = logging.getLogger("apps")

#: Lo que se le dice a la petición que perdió contra otra simultánea.
CONFLICT_MESSAGE = (
    "Otra petición hizo este mismo cambio al mismo tiempo. Actualiza y vuelve "
    "a intentarlo."
)


class Conflict(APIException):
    """409: el registro cambió bajo la petición o está en uso."""

    status_code = status.HTTP_409_CONFLICT
    default_detail = CONFLICT_MESSAGE
    default_code = "conflict"


def _in_use(objects) -> str:
    """Por qué no se borra: qué registros lo usan, por su nombre en plural."""
    models = sorted({str(obj._meta.verbose_name_plural) for obj in objects})
    if not models:
        return "No se puede eliminar: el registro está en uso."
    return (
        "No se puede eliminar porque tiene registros relacionados: "
        f"{', '.join(models)}."
    )


def _wait_text(seconds: float | None) -> str:
    if not seconds:
        return "Intenta de nuevo en un momento."
    seconds = math.ceil(seconds)
    if seconds < 60:
        unit = "segundo" if seconds == 1 else "segundos"
        return f"Intenta de nuevo en {seconds} {unit}."
    minutes = math.ceil(seconds / 60)
    unit = "minuto" if minutes == 1 else "minutos"
    return f"Intenta de nuevo en {minutes} {unit}."


def api_exception_handler(exc, context):
    """El de DRF, con los errores del dominio en su forma (api-lists-errors.md §5).

    - El ``ValidationError`` de Django (servicios, o un id que no es UUID al
      filtrar) es un 400 con el dict de campos, no un 500.
    - Borrar algo en uso (``ProtectedError``/``RestrictedError``) es un 409 que
      dice qué lo usa: heredan de ``IntegrityError`` y antes recibían el
      mensaje de dos peticiones simultáneas.
    - Dos peticiones que chocan con una restricción única de la base ya no
      terminan en un 500 (iteracion-16): la que perdió recibe 409 con qué
      hacer. El mensaje de la base —tablas, restricciones— nunca llega al
      cliente.
    - El 429 se dice como lo diría la aplicación, también el de la espera
      del código de un solo uso (``OTPCooldown``, iteracion-26 #14), con su
      ``Retry-After``.
    """
    if isinstance(exc, DjangoValidationError):
        exc = ValidationError(as_serializer_error(exc))
    elif isinstance(exc, ProtectedError):
        exc = Conflict(_in_use(exc.protected_objects))
    elif isinstance(exc, RestrictedError):
        exc = Conflict(_in_use(exc.restricted_objects))
    elif isinstance(exc, IntegrityError):
        logger.warning("Integrity conflict: %s", type(exc).__name__)
        exc = Conflict()
    elif isinstance(exc, OTPCooldown):
        wait = exc.wait
        exc = Throttled(wait=wait)
        exc.detail = f"Ya te enviamos un código. {_wait_text(wait)}"
    elif isinstance(exc, Throttled):
        exc.detail = f"Demasiados intentos. {_wait_text(exc.wait)}"
    response = drf_exception_handler(exc, context)
    if response is not None and isinstance(exc, Conflict):
        response.data["code"] = exc.default_code
    return response
