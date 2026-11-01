"""Chequeos de Django: lo que tiene que estar antes de que una versión salga.

Corren con ``migrate`` y ``createcachetable``, que son parte del build de
Vercel: un error detiene el despliegue y la versión anterior sigue atendiendo.
"""

import os

from django.conf import settings
from django.core.checks import Error, Tags, register

from common.mail import SANDBOX_SENDER
from core import cookie_domain


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


#: Cómo arreglarlo cuando la SPA y la API no comparten un dominio válido.
_SAME_DOMAIN_HINT = (
    "Pon la SPA y la API bajo el mismo dominio (por ejemplo app.dominio.com y "
    "api.dominio.com) en CORS_ALLOWED_ORIGINS y ALLOWED_HOSTS."
)


def _hosts(hosts: list[str]) -> str:
    return ", ".join(hosts)


def _expected_domain_hint(spa: list[str], api: list[str], deduced: str | None) -> str:
    """Qué dominio se esperaba y cómo llegar a él."""
    if deduced and all(cookie_domain.covers(deduced, h) for h in [*spa, *api]):
        return (
            f"Se esperaba {deduced}, el dominio que comparten la SPA y la API: "
            "quita CSRF_COOKIE_DOMAIN para que se deduzca, o pon ese valor."
        )
    return (
        f"Se esperaba un dominio que cubra a la SPA ({_hosts(spa)}) y a la API "
        f"({_hosts(api)}), y no hay uno común. {_SAME_DOMAIN_HINT} Si un origen "
        "de la SPA es de otro dominio, quítalo de CORS_ALLOWED_ORIGINS."
    )


@register(Tags.security)
def csrf_cookie_domain_in_production(app_configs, **kwargs) -> list[Error]:
    """Producción no sale si la SPA no lee la cookie CSRF (iteracion-30 #1, SEC-04.4).

    La SPA copia la cookie CSRF en X-CSRFToken: si su dominio, deducido o puesto
    en CSRF_COOKIE_DOMAIN, no cubre a los hosts de la SPA (los orígenes https de
    CORS_ALLOWED_ORIGINS) la SPA no la lee; si no cubre a los de la API (los de
    ALLOWED_HOSTS sin comodines, locales, IPs ni *.vercel.app) el navegador la
    tira, como pasó con el .itzaka.com de antes; sin dominio queda en el host de
    la API. En los tres casos cada escritura respondería «CSRF token missing».
    """
    if os.environ.get("VERCEL_ENV") != "production":
        return []
    domain = settings.CSRF_COOKIE_DOMAIN
    spa = cookie_domain.app_hosts(settings.CORS_ALLOWED_ORIGINS)
    api = cookie_domain.api_hosts(settings.ALLOWED_HOSTS)
    deduced = cookie_domain.csrf_cookie_domain(
        None, settings.CORS_ALLOWED_ORIGINS, settings.ALLOWED_HOSTS
    )
    hint = _expected_domain_hint(spa, api, deduced)
    if not domain:
        same_host = {host.strip().lower() for host in settings.ALLOWED_HOSTS}
        apart = [host for host in spa if host not in same_host]
        if not apart:
            return []
        return [
            Error(
                "La cookie CSRF no tiene dominio (CSRF_COOKIE_DOMAIN es None) y "
                f"queda sólo en el host de la API: la SPA en {_hosts(apart)} no "
                "podría leerla y cada escritura respondería «CSRF token missing».",
                hint=hint,
                id="common.E007",
            )
        ]
    errors = []
    outside_spa = [host for host in spa if not cookie_domain.covers(domain, host)]
    if outside_spa:
        errors.append(
            Error(
                f"El dominio de la cookie CSRF es {domain} y no cubre a la SPA en "
                f"{_hosts(outside_spa)}: la SPA no podría leerla y cada escritura "
                "respondería «CSRF token missing».",
                hint=hint,
                id="common.E005",
            )
        )
    outside_api = [host for host in api if not cookie_domain.covers(domain, host)]
    if outside_api:
        errors.append(
            Error(
                f"El dominio de la cookie CSRF es {domain} y no cubre a la API en "
                f"{_hosts(outside_api)}: el navegador tiraría la cookie que manda "
                "la API.",
                hint=hint,
                id="common.E006",
            )
        )
    return errors
