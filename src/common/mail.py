"""Resend, a pelo: el correo sale por su API HTTP y no por el mailer de Django.

Django's email backend is built around SMTP and a synchronous connection; on a
serverless deployment that means an outbound port that may not be open and a
connection paid for on every request. Resend is an HTTPS call, which is the one
thing the platform always allows, and it is also who tells us whether the mail
was accepted.

Nothing here raises: an email that could not be sent must not lose the quote
that was just created. The caller gets ``False`` and the log gets the reason.
"""

import json
import logging
import urllib.error
import urllib.request
from base64 import b64encode
from dataclasses import dataclass
from email.utils import formataddr, parseaddr

from django.conf import settings

from common.brand import BRAND_NAME

logger = logging.getLogger("apps")

RESEND_ENDPOINT = "https://api.resend.com/emails"

#: La tanda: varios correos en una sola petición, que Resend acepta o rechaza
#: entera (su validación estricta, la de por omisión).
RESEND_BATCH_ENDPOINT = "https://api.resend.com/emails/batch"

#: Cuántos correos caben en una tanda de Resend.
BATCH_MAX = 100

#: Lo que se espera a que Resend conteste. Más allá, el envío se da por perdido
#: y quien pidió la pantalla sigue con su trabajo.
TIMEOUT_SECONDS = 10

#: El remitente de pruebas de Resend. Funciona sin configurar nada, pero sólo
#: entrega al correo del dueño de la cuenta: a un cliente nunca le llega.
SANDBOX_SENDER = "onboarding@resend.dev"

#: Con qué nombre se presenta este cliente.
#:
#: No es cosmético. La API de Resend está detrás de Cloudflare, que corta las
#: peticiones cuya firma parece un script suelto: con el `Python-urllib/3.x`
#: que pone la biblioteca por omisión, la respuesta era un 403 con «error code:
#: 1010» —una página de Cloudflare, no de Resend— y el envío no llegaba ni a
#: aparecer en el registro de la cuenta.
USER_AGENT = f"{BRAND_NAME}/1.0 (+https://itzaka.com)"


def mask_email(address: str) -> str:
    """``j***@dominio.com``: lo justo para reconocerlo, no para leerlo.

    El correo de una persona es un dato personal; en los registros de la
    plataforma queda a la vista de quien los lea (iteracion-12).
    """
    local, at, domain = (address or "").partition("@")
    if not at or not local:
        return "***"
    return f"{local[0]}***@{domain}"


def sender() -> str:
    """Quién firma el correo: la marca, con la dirección configurada.

    La dirección vive en `RESEND_FROM` porque depende del dominio verificado en
    Resend; el nombre que se ve en la bandeja es el de la marca y no se deja a
    la configuración: así un cambio de nombre no espera a que alguien edite
    una variable en el servidor.
    """
    _, address = parseaddr(settings.RESEND_FROM)
    return formataddr((BRAND_NAME, address or settings.RESEND_FROM))


class Attachment:
    """Un archivo que viaja con el correo: el PDF del documento."""

    def __init__(self, *, filename: str, content: bytes) -> None:
        self.filename = filename
        self.content = content

    def payload(self) -> dict[str, str]:
        return {
            "filename": self.filename,
            "content": b64encode(self.content).decode("ascii"),
        }


@dataclass(frozen=True)
class Message:
    """Un correo de una tanda."""

    to: str
    subject: str
    html: str
    reply_to: str | None = None


def _cannot_send(reason: str) -> None:
    """Un correo que no puede salir: donde el correo es obligatorio, es un error.

    En producción un aviso se perdía entre los demás registros y nadie se
    enteraba de que los códigos y las invitaciones no llegaban (iteracion-16).
    """
    level = logging.ERROR if settings.REQUIRE_EMAIL_DELIVERY else logging.WARNING
    logger.log(level, "Email not sent: %s", reason)


def _flag_sandbox_sender() -> None:
    """Con el remitente de prueba, Resend sólo entrega al dueño de la cuenta."""
    if SANDBOX_SENDER in settings.RESEND_FROM:
        level = logging.ERROR if settings.REQUIRE_EMAIL_DELIVERY else logging.WARNING
        logger.log(
            level,
            "Sending from Resend's test address: only the account owner will "
            "receive it. Set RESEND_FROM to an address of a verified domain.",
        )


def _post(endpoint: str, payload: dict | list, *, recipients: str) -> bool:
    """Una petición a Resend. Devuelve si la aceptaron; nunca lanza."""
    request = urllib.request.Request(  # noqa: S310 -- URL fija y https
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {settings.RESEND_API_KEY}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310
            return 200 <= response.status < 300
    except urllib.error.HTTPError as error:
        # El motivo va en el propio mensaje y no en los campos extra: el visor
        # de registros de la plataforma sólo muestra el texto, así que «Email
        # refused by Resend» a secas no decía nada de lo que hay que corregir.
        detail = error.read()[:500].decode("utf-8", "replace")
        logger.warning(
            "Email refused by Resend (HTTP %s) from=%r to=%s: %s",
            error.code,
            settings.RESEND_FROM,
            recipients,
            detail,
        )
        return False
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        logger.warning("Email could not be sent: %s", error)
        return False


def is_configured() -> bool:
    """Si hay por dónde mandar correo.

    Sin llave no hay envío, y eso cambia lo que la aplicación puede prometer:
    el código de verificación vuelve a ser el universal porque no habría manera
    de hacerle llegar uno propio a nadie.
    """
    return bool(settings.RESEND_API_KEY)


def send_email(
    *,
    to: str,
    subject: str,
    html: str,
    reply_to: str | None = None,
    attachments: list[Attachment] | None = None,
) -> bool:
    """Manda un correo por Resend. Devuelve si lo aceptaron."""
    if not is_configured():
        _cannot_send("RESEND_API_KEY is empty")
        return False
    if not to:
        logger.warning("Email not sent: no recipient")
        return False

    # Con el remitente de prueba, la cotización de un cliente se rechaza y el
    # fallo no se explica solo.
    _flag_sandbox_sender()

    body: dict = {
        "from": sender(),
        "to": [to],
        "subject": subject,
        "html": html,
    }
    if reply_to:
        body["reply_to"] = reply_to
    if attachments:
        body["attachments"] = [item.payload() for item in attachments]

    accepted = _post(RESEND_ENDPOINT, body, recipients=mask_email(to))
    if accepted:
        logger.info("Email sent to %s: %s", mask_email(to), subject)
    return accepted


def send_batch(messages: list[Message]) -> bool:
    """Manda una tanda de correos en una sola petición a Resend.

    O salen todos o ninguno: Resend valida la tanda entera antes de aceptarla.
    Y una petición cabe en el tiempo de la función, que veinte seguidas, con su
    espera cada una, no (iteracion-16).

    Raises:
        ValueError: la tanda pasa de ``BATCH_MAX`` correos.
    """
    if not messages:
        return True
    if len(messages) > BATCH_MAX:
        raise ValueError(f"Una tanda lleva a lo más {BATCH_MAX} correos")
    if not is_configured():
        _cannot_send("RESEND_API_KEY is empty")
        return False
    _flag_sandbox_sender()

    payload = []
    for message in messages:
        item = {
            "from": sender(),
            "to": [message.to],
            "subject": message.subject,
            "html": message.html,
        }
        if message.reply_to:
            item["reply_to"] = message.reply_to
        payload.append(item)

    accepted = _post(
        RESEND_BATCH_ENDPOINT, payload, recipients=f"{len(messages)} recipients"
    )
    if accepted:
        logger.info("Email batch sent: %s message(s)", len(messages))
    return accepted
