"""Assets business logic: guardar un binario del editor una sola vez."""

import hashlib
import logging
import os

from django.conf import settings
from django.utils.text import get_valid_filename
from rest_framework.exceptions import ValidationError

from apps.assets.models import PlanAsset

logger = logging.getLogger("apps")


def stored_filename(path: str, original: str) -> str:
    """Un nombre estable y sin sorpresas para el archivo en el bucket.

    The logical path can carry folders, accents and spaces from whatever
    archive it came in; the hash keeps two files with the same basename apart
    while the name still says what it is when someone opens the bucket.
    """
    # No es una firma: sólo separa dos archivos que se llaman igual.
    digest = hashlib.sha256(path.encode("utf-8")).hexdigest()[:8]
    name = get_valid_filename(os.path.basename(original) or "archivo")
    return f"{digest}-{name}"


def store_asset(*, owner, kind: str, path: str, file) -> tuple[PlanAsset, bool]:
    """Guarda el binario del editor. Devuelve (archivo, si es nuevo).

    Uploading the same path twice is not an error: it is the same file, and the
    account already has it. That makes importing a library twice —or from two
    devices— cost nothing.

    Raises:
        ValidationError: sin ruta, o un archivo por encima del tope.
    """
    if not path:
        raise ValidationError("El archivo necesita una ruta")

    limit = settings.PLAN_ASSET_MAX_BYTES
    if file.size > limit:
        raise ValidationError(
            f"El archivo pesa más de {limit // (1024 * 1024)} MB. "
            "Las texturas y las mallas del editor tienen ese tope."
        )

    existing = PlanAsset.objects.filter(owner=owner, path=path).first()
    if existing is not None:
        return existing, False

    file.name = stored_filename(path, file.name)
    asset = PlanAsset.objects.create(
        owner=owner, kind=kind, path=path, file=file, size=file.size
    )
    logger.info("Plan asset stored", extra={"asset_id": str(asset.pk), "kind": kind})
    return asset, True
