"""reCAPTCHA v3 verificado en el servidor y campo trampa (iteracion-12 #4).

Las vistas no llaman a Google: usan ``guard_public_form``, que aplica el campo
trampa y la política de fallos que declara cada formulario.
"""

import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from rest_framework import status
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.settings import api_settings

logger = logging.getLogger("apps")

VERIFY_URL = "https://www.google.com/recaptcha/api/siteverify"
#: El campo que una persona nunca ve; un bot que llena todo, sí.
HONEYPOT_FIELD = "website"
TOKEN_FIELD = "recaptcha_token"  # noqa: S105 -- nombre del campo, no un secreto
REJECTED = "No pudimos verificar el formulario. Intenta de nuevo."
#: Un token de v3 mide unos cientos de caracteres; uno de megas no se le manda
#: a Google (MAN-04, iteracion-26 #17).
TOKEN_MAX_LENGTH = 8192
NOT_AN_OBJECT = "Envía el formulario como un objeto JSON."


class CaptchaUnavailable(Exception):
    """Google no contestó o contestó con un error."""


class CaptchaDown(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = (
        "No pudimos verificar el formulario en este momento. Intenta más tarde."
    )
    default_code = "captcha_unavailable"


@dataclass(frozen=True)
class CaptchaResult:
    ok: bool
    reason: str = ""


def _siteverify(*, token: str, remote_ip: str | None) -> dict:
    """La respuesta de Google para ese token."""
    fields = {"secret": settings.RECAPTCHA_SECRET_KEY, "response": token}
    if remote_ip:
        fields["remoteip"] = remote_ip
    request = Request(  # noqa: S310 -- URL fija de Google, https
        VERIFY_URL, data=urlencode(fields).encode(), method="POST"
    )
    try:
        with urlopen(request, timeout=5) as response:  # noqa: S310
            return json.loads(response.read())
    except (URLError, TimeoutError, ValueError) as exc:
        logger.warning("recaptcha unavailable: %s", type(exc).__name__)
        raise CaptchaUnavailable from exc


def verify_recaptcha(
    *, token: str | None, action: str, remote_ip: str | None
) -> CaptchaResult:
    """Verificar un token v3. Google caído levanta ``CaptchaUnavailable``."""
    if not settings.RECAPTCHA_ENABLED:
        return CaptchaResult(ok=True, reason="disabled")
    if not token:
        return CaptchaResult(ok=False, reason="missing")
    if not isinstance(token, str) or len(token) > TOKEN_MAX_LENGTH:
        return CaptchaResult(ok=False, reason="invalid")
    data = _siteverify(token=token, remote_ip=remote_ip)
    if not data.get("success"):
        return CaptchaResult(ok=False, reason="invalid")
    if data.get("action") != action:
        return CaptchaResult(ok=False, reason="action")
    if data.get("hostname") not in settings.RECAPTCHA_HOSTNAMES:
        return CaptchaResult(ok=False, reason="hostname")
    if float(data.get("score", 0)) < settings.RECAPTCHA_MIN_SCORE:
        return CaptchaResult(ok=False, reason="score")
    return CaptchaResult(ok=True)


class Verdict(Enum):
    """Lo que la vista hace con el formulario."""

    PASS = "pass"  # noqa: S105 -- sigue como siempre
    REVIEW = "review"  # se acepta, marcado para revisar (Google caído)
    DROP = "drop"  # campo trampa lleno: respuesta de siempre, sin efectos


def guard_public_form(
    request, *, action: str, when_unavailable: str, remote_ip: str | None
) -> Verdict:
    """El campo trampa y reCAPTCHA, antes de validar nada y de cualquier efecto.

    ``when_unavailable`` es la política del formulario si Google no contesta:
    ``"reject"`` (503, las puertas de la cuenta) o ``"review"`` (se acepta bajo
    su límite de intentos y queda marcado, el contacto). Un token que no pasa
    responde 400 con un mensaje que no dice por qué, y un cuerpo que no es un
    objeto JSON (un arreglo, un texto, ``null``), 400 antes de leer nada.
    """
    if not isinstance(request.data, Mapping):
        raise ValidationError({api_settings.NON_FIELD_ERRORS_KEY: [NOT_AN_OBJECT]})
    if str(request.data.get(HONEYPOT_FIELD) or "").strip():
        logger.info("honeypot", extra={"action": action})
        return Verdict.DROP
    try:
        result = verify_recaptcha(
            token=request.data.get(TOKEN_FIELD),
            action=action,
            remote_ip=remote_ip,
        )
    except CaptchaUnavailable:
        if when_unavailable == "review":
            logger.warning("recaptcha down, kept for review", extra={"action": action})
            return Verdict.REVIEW
        raise CaptchaDown from None
    if not result.ok:
        logger.info(
            "recaptcha rejected", extra={"action": action, "reason": result.reason}
        )
        raise ValidationError(REJECTED)
    return Verdict.PASS
