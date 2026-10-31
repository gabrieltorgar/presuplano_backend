"""Chequeos de la plataforma (corren con ``migrate``, parte del build de Vercel).

Se registran desde ``AccountsConfig.ready()``. Un error detiene el despliegue y
la versión anterior sigue atendiendo.
"""

import os

from django.conf import settings
from django.core.checks import Error, Tags, register

#: Lo más que una función de Vercel deja pasar sin cortar el cuerpo (4.5 MB),
#: menos el resto del formulario multipart.
VERCEL_UPLOAD_CAP = 4 * 1024 * 1024

#: Los topes de los archivos que viajan por el cuerpo de la función.
UPLOAD_CAPS = (
    "UPLOAD_MAX_BYTES",
    "PLAN_ASSET_MAX_BYTES",
    "DOCUMENT_EMAIL_MAX_BYTES",
    "PHOTO_PLAN_MAX_BYTES",
)


@register(Tags.security)
def uploads_fit_vercel(app_configs, **kwargs) -> list[Error]:
    """En Vercel, ningún archivo por la API pasa de 4 MiB (API-02, iteracion-26 #19).

    Vercel responde 413 a un cuerpo de más de 4.5 MB antes de llegar a Django,
    sin cabeceras de CORS: la SPA ve «Sin conexión» en vez del mensaje del tope.
    """
    if not os.environ.get("VERCEL"):
        return []
    over = [
        name for name in UPLOAD_CAPS if getattr(settings, name, 0) > VERCEL_UPLOAD_CAP
    ]
    if not over:
        return []
    return [
        Error(
            f"{', '.join(over)} pasa de 4 MiB: en Vercel ese archivo nunca llega "
            "a la API (413 antes de Django).",
            hint=(
                "Deja cada tope en 4194304 o menos; lo más grande va directo al "
                "bucket con una subida firmada."
            ),
            id="core.E002",
        )
    ]
