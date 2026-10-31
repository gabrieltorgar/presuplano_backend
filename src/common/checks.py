"""Chequeos de Django: lo que tiene que estar antes de que una versión salga.

Corren con ``migrate`` y ``createcachetable``, que son parte del build de
Vercel: un error detiene el despliegue y la versión anterior sigue atendiendo.
"""

import os

from django.conf import settings
from django.core.checks import Error, Tags, register

from common.mail import SANDBOX_SENDER


@register("email")
def email_delivery(app_configs, **kwargs) -> list[Error]:
    """Producción no sale sin correo (iteracion-16, US-135).

    Los códigos de verificación, las invitaciones y los documentos salen por
    Resend. Sin su llave no sale ninguno, y con su remitente de prueba sólo le
    llegan al dueño de la cuenta de Resend; antes eso quedaba como un aviso en
    el registro y nadie se enteraba.
    """
    if not settings.REQUIRE_EMAIL_DELIVERY:
        return []
    if not settings.RESEND_API_KEY:
        return [
            Error(
                "Los correos no saldrían: falta RESEND_API_KEY.",
                hint=(
                    "Configúrala en las variables de Production de Vercel; los "
                    "códigos, las invitaciones y los documentos salen por Resend."
                ),
                id="common.E001",
            )
        ]
    if not settings.RESEND_FROM or SANDBOX_SENDER in settings.RESEND_FROM:
        return [
            Error(
                "RESEND_FROM usa el remitente de prueba de Resend: sólo le "
                "llegaría al dueño de la cuenta de Resend.",
                hint=(
                    "Pon en RESEND_FROM una dirección de un dominio verificado "
                    "en Resend."
                ),
                id="common.E002",
            )
        ]
    return []


#: Lo que hace falta para cerrarle la puerta a los bots, en los dos lados.
_RECAPTCHA_HINT = (
    "Crea las llaves de reCAPTCHA v3 del dominio y configúralas juntas en "
    "Production: RECAPTCHA_SECRET_KEY aquí y VITE_RECAPTCHA_SITE_KEY en el "
    "frontend."
)


@register(Tags.security)
def recaptcha_in_production(app_configs, **kwargs) -> list[Error]:
    """Producción no sale sin reCAPTCHA (iteracion-26 #17, BOT-01).

    Registro, acceso, recuperación, contacto y aceptar una invitación lo
    verifican en el servidor. Sin la llave secreta, o con la verificación
    apagada, sólo quedaba el campo trampa, y nada lo decía.
    """
    if os.environ.get("VERCEL_ENV") != "production":
        return []
    if not settings.RECAPTCHA_SECRET_KEY:
        return [
            Error(
                "Los formularios públicos quedarían sin reCAPTCHA: falta "
                "RECAPTCHA_SECRET_KEY.",
                hint=_RECAPTCHA_HINT,
                id="common.E003",
            )
        ]
    if not settings.RECAPTCHA_ENABLED:
        return [
            Error(
                "RECAPTCHA_ENABLED está apagado en producción: los formularios "
                "públicos no se verificarían.",
                hint="Quita RECAPTCHA_ENABLED de las variables de Production.",
                id="common.E004",
            )
        ]
    return []
