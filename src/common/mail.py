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

from django.conf import settings

logger = logging.getLogger("apps")

RESEND_ENDPOINT = "https://api.resend.com/emails"

#: Lo que se espera a que Resend conteste. Más allá, el envío se da por perdido
#: y quien pidió la pantalla sigue con su trabajo.
TIMEOUT_SECONDS = 10


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
        logger.warning("Email not sent: Resend is not configured")
        return False
    if not to:
        logger.warning("Email not sent: no recipient")
        return False

    body: dict = {
        "from": settings.RESEND_FROM,
        "to": [to],
        "subject": subject,
        "html": html,
    }
    if reply_to:
        body["reply_to"] = reply_to
    if attachments:
        body["attachments"] = [item.payload() for item in attachments]

    request = urllib.request.Request(  # noqa: S310 -- URL fija y https
        RESEND_ENDPOINT,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {settings.RESEND_API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310
            accepted = 200 <= response.status < 300
    except urllib.error.HTTPError as error:
        # El cuerpo dice por qué: dominio sin verificar, destinatario inválido.
        detail = error.read()[:500].decode("utf-8", "replace")
        logger.warning(
            "Email refused by Resend", extra={"status": error.code, "detail": detail}
        )
        return False
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        logger.warning("Email could not be sent", extra={"error": str(error)})
        return False

    logger.info("Email sent", extra={"subject": subject})
    return accepted
