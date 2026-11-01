"""Respuestas de error de la API en palabras de la aplicación."""

import logging
import math

from django.conf import settings
from django.core.exceptions import RequestDataTooBig
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


class RequestTooBig(APIException):
    """400: el cuerpo pasa de ``DATA_UPLOAD_MAX_MEMORY_SIZE`` (iteracion-27 #7).

    Django lo corta antes de la validación de la vista (``RequestDataTooBig``)
    y, sin esto, respondía su página «Bad Request» sin motivo. Es un 400, como
    el tope propio del documento de un plano, y dice qué pesa.
    """

    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "request_too_big"


def _too_big_text() -> str:
    limit = settings.DATA_UPLOAD_MAX_MEMORY_SIZE // (1024 * 1024)
    return (
        f"Lo que enviaste pesa más de {limit} MB, lo más que recibe el servidor. "
        "Si es un plano, lo que más pesa suele ser el plano de fondo escaneado o "
        "una textura suelta."
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
    - Un cuerpo de más de ``DATA_UPLOAD_MAX_MEMORY_SIZE`` (``RequestDataTooBig``)
      es un 400 que dice qué pesa, con ``code: request_too_big`` (iteracion-27
      #7), no la página de Django sin motivo.
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
    elif isinstance(exc, RequestDataTooBig):
        exc = RequestTooBig(_too_big_text())
    response = drf_exception_handler(exc, context)
    if response is not None and isinstance(exc, Conflict | RequestTooBig):
        response.data["code"] = exc.default_code
    return response
