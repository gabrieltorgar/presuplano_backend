"""Mandar un documento por correo, con la marca de quien lo firma.

El PDF lo arma el navegador —es donde están las fuentes, el logotipo ya
descargado y la vista previa que el arquitecto acaba de mirar—, así que aquí
llega hecho. Lo que pone el servidor es el sobre: el cuerpo del correo pintado
con el membrete de la organización, el texto que corresponde a cada documento
y el envío por Resend.
"""

import logging
from decimal import Decimal, InvalidOperation

from django.conf import settings
from rest_framework.exceptions import ValidationError

from common import mail
from common.branding import brand_for
from common.emails import render_email

logger = logging.getLogger("apps")


class Kind:
    """Los cuatro documentos que la aplicación sabe entregar."""

    QUOTE = "quote"
    PROJECT_STATUS = "project_status"
    PAYMENT_VOUCHER = "payment_voucher"
    COLLECTION_VOUCHER = "collection_voucher"

    CHOICES = [
        (QUOTE, "Cotización"),
        (PROJECT_STATUS, "Comprobante de estatus de proyecto"),
        (PAYMENT_VOUCHER, "Comprobante de pago"),
        (COLLECTION_VOUCHER, "Comprobante de cobro"),
    ]


#: Qué dice cada correo: el asunto, el título y la primera línea.
WORDING: dict[str, dict[str, str]] = {
    Kind.QUOTE: {
        "subject": "Tu cotización",
        "title": "Aquí está tu cotización",
        "intro": (
            "Te comparto la cotización de los trabajos que platicamos. "
            "El detalle va en el PDF adjunto."
        ),
        "party": "Cliente",
    },
    Kind.PROJECT_STATUS: {
        "subject": "Avance de tu proyecto",
        "title": "Cómo va tu proyecto",
        "intro": (
            "Te comparto el estado del proyecto: lo que va hecho, lo que sigue "
            "y las cuentas al día. El detalle va en el PDF adjunto."
        ),
        "party": "Cliente",
    },
    Kind.PAYMENT_VOUCHER: {
        "subject": "Comprobante de pago",
        "title": "Comprobante de tu pago",
        "intro": (
            "Este es el comprobante del pago por los trabajos realizados. "
            "El detalle va en el PDF adjunto."
        ),
        "party": "Para",
    },
    Kind.COLLECTION_VOUCHER: {
        "subject": "Comprobante de cobro",
        "title": "Recibimos tu pago",
        "intro": (
            "Gracias por tu pago. Este es el comprobante de lo recibido; "
            "el detalle va en el PDF adjunto."
        ),
        "party": "Cliente",
    },
}


def _amount(value: str) -> str:
    """El importe como lo lee quien recibe el correo, no como viaja en la API."""
    try:
        return f"${Decimal(value):,.2f}"
    except (InvalidOperation, TypeError, ValueError):
        return value


def _rows(kind: str, reference: str, party: str, amount: str) -> list[tuple[str, str]]:
    """Lo que se lee sin abrir el adjunto."""
    rows: list[tuple[str, str]] = []
    if reference:
        rows.append(("Folio", reference))
    if party:
        rows.append((WORDING[kind]["party"], party))
    if amount:
        rows.append(("Importe", _amount(amount)))
    return rows


def send_document(
    *,
    user,
    kind: str,
    to: str,
    file,
    reference: str = "",
    party: str = "",
    amount: str = "",
    message: str = "",
) -> bool:
    """Manda el documento adjunto al correo indicado. Devuelve si salió.

    Raises:
        ValidationError: el adjunto pesa de más, o no hay a quién mandarlo.
    """
    if not mail.is_configured():
        raise ValidationError(
            "El envío de correos no está configurado todavía. "
            "Descarga el documento y compártelo como lo haces hoy."
        )

    limit = settings.DOCUMENT_EMAIL_MAX_BYTES
    if file.size > limit:
        raise ValidationError(
            f"El documento pesa más de {limit // (1024 * 1024)} MB y no se puede "
            "enviar por correo."
        )

    wording = WORDING[kind]
    brand = brand_for(user=user)
    html = render_email(
        brand=brand,
        title=wording["title"],
        intro=wording["intro"],
        rows=_rows(kind, reference, party, amount),
        note=message or None,
    )
    subject = f"{wording['subject']} — {brand.name}"

    sent = mail.send_email(
        to=to,
        subject=subject,
        html=html,
        reply_to=user.email or None,
        attachments=[
            mail.Attachment(filename=file.name or "documento.pdf", content=file.read())
        ],
    )
    logger.info(
        "Document emailed", extra={"kind": kind, "sent": sent, "user_id": str(user.pk)}
    )
    return sent
