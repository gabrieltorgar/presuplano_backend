"""Con qué cara sale un correo: la de la organización, o la de CUOTREKA.

Es la misma regla que ya siguen los PDF —el membrete manda cuando está
configurado— con una diferencia que pidió el negocio: cuando el documento sale
con la marca del arquitecto, el pie dice que va «optimizado por CUOTREKA».
Cuando la cuenta no ha configurado nada, el correo es de CUOTREKA y ese pie
sobraría.
"""

from dataclasses import dataclass

from django.conf import settings

from apps.accounts.models import DEFAULT_ORGANIZATION_COLOR
from common.brand import BRAND_NAME

#: El logotipo propio, para cuando la cuenta todavía no tiene el suyo.
BRAND_LOGO_PATH = "/pwa-192x192.png"

#: El pie que acompaña a los documentos con marca del arquitecto.
OPTIMIZED_BY = f"optimizado por {BRAND_NAME}"


@dataclass(frozen=True)
class Brand:
    """Nombre, color y logotipo con los que se pinta un correo."""

    name: str
    color: str
    logo_url: str
    #: Si el pie lleva el «optimizado por CUOTREKA».
    optimized: bool


def house_brand() -> Brand:
    """La marca de la casa."""
    return Brand(
        name=BRAND_NAME,
        color=DEFAULT_ORGANIZATION_COLOR,
        logo_url=f"{settings.APP_BASE_URL.rstrip('/')}{BRAND_LOGO_PATH}",
        optimized=False,
    )


def brand_for(*, user) -> Brand:
    """La marca con la que firma esa cuenta.

    Una organización cuenta como configurada en cuanto tiene nombre o
    logotipo: el color solo no basta, porque todas las cuentas nacen con uno.
    """
    organization = getattr(user, "organization", None)
    if organization is None:
        return house_brand()

    logo = organization.logo.url if organization.logo else ""
    if not organization.name and not logo:
        return house_brand()

    return Brand(
        name=organization.name or BRAND_NAME,
        color=organization.color or DEFAULT_ORGANIZATION_COLOR,
        logo_url=logo,
        optimized=True,
    )
