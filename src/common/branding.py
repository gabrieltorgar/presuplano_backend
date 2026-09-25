"""Con qué cara sale un correo: la de la organización, o la de presuplano.

Es la misma regla que ya siguen los PDF —el membrete manda cuando está
configurado— con una diferencia que pidió el negocio: cuando el documento sale
con la marca del arquitecto, el pie dice que va «optimizado por presuplano».
Cuando la cuenta no ha configurado nada, el correo es de presuplano y ese pie
sobraría.
"""

from dataclasses import dataclass

from django.conf import settings

from apps.accounts.models import DEFAULT_ORGANIZATION_COLOR

#: La marca propia, para cuando la cuenta todavía no tiene la suya.
PRESUPLANO_NAME = "presuplano"
PRESUPLANO_LOGO_PATH = "/pwa-192x192.png"

#: El pie que acompaña a los documentos con marca del arquitecto.
OPTIMIZED_BY = "optimizado por presuplano"


@dataclass(frozen=True)
class Brand:
    """Nombre, color y logotipo con los que se pinta un correo."""

    name: str
    color: str
    logo_url: str
    #: Si el pie lleva el «optimizado por presuplano».
    optimized: bool


def presuplano_brand() -> Brand:
    """La marca de la casa."""
    return Brand(
        name=PRESUPLANO_NAME,
        color=DEFAULT_ORGANIZATION_COLOR,
        logo_url=f"{settings.APP_BASE_URL.rstrip('/')}{PRESUPLANO_LOGO_PATH}",
        optimized=False,
    )


def brand_for(*, user) -> Brand:
    """La marca con la que firma esa cuenta.

    Una organización cuenta como configurada en cuanto tiene nombre o
    logotipo: el color solo no basta, porque todas las cuentas nacen con uno.
    """
    organization = getattr(user, "organization", None)
    if organization is None:
        return presuplano_brand()

    logo = organization.logo.url if organization.logo else ""
    if not organization.name and not logo:
        return presuplano_brand()

    return Brand(
        name=organization.name or PRESUPLANO_NAME,
        color=organization.color or DEFAULT_ORGANIZATION_COLOR,
        logo_url=logo,
        optimized=True,
    )
