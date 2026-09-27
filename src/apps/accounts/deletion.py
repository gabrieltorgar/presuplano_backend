"""Eliminar una cuenta con todo lo suyo: filas y archivos, sin anonimizar.

Lo que una cuenta deja en el sistema vive en dos lugares. En la base, cada fila
cuelga de la cuenta por su ``owner``, pero varias relaciones están protegidas
—una cotización protege a su cliente, un avance a su partida y a quien lo
hizo—, así que se borran en el orden que esas protecciones piden. En el bucket,
todo cuelga de dos carpetas: la de la organización (logotipo, texturas y
mobiliario) y la de sus evidencias. Se barren las dos carpetas enteras y no
sólo los archivos que la base nombra, porque un logotipo reemplazado o una
subida interrumpida dejan archivos que ya ninguna fila recuerda.

Los archivos se borran después de confirmar el borrado de la base: si la base
fallara, la cuenta seguiría entera y con sus archivos, en vez de quedar con
filas que apuntan a nada.
"""

import logging

from django.core.files.storage import default_storage
from django.db import transaction

from apps.accounts.models import Organization, User
from apps.assets.models import CatalogModel, PlanAsset
from apps.catalog.models import Tariff
from apps.clients.models import Client
from apps.payments.models import Payment
from apps.planner.models import Plan
from apps.projects.models import Evidence, Project
from apps.quotes.models import Quote
from apps.staff.models import Worker, WorkerPayment

logger = logging.getLogger("apps")


def _walk(storage, prefix: str) -> list[str]:
    """Todos los archivos bajo una carpeta del almacenamiento, a cualquier nivel."""
    try:
        folders, files = storage.listdir(prefix)
    except (FileNotFoundError, NotADirectoryError, NotImplementedError, OSError):
        return []
    names = [f"{prefix}{name}" for name in files]
    for folder in folders:
        names += _walk(storage, f"{prefix}{folder}/")
    return names


def _files_of(user: User) -> list[tuple[object, str]]:
    """Qué archivos son de la cuenta: los que la base nombra y sus carpetas."""
    found: list[tuple[object, str]] = []
    organization = Organization.objects.filter(user=user).first()
    if organization and organization.logo:
        found.append((organization.logo.storage, organization.logo.name))
    for evidence in Evidence.objects.filter(progress__project__owner=user):
        if evidence.image:
            found.append((evidence.image.storage, evidence.image.name))
    for asset in PlanAsset.objects.filter(owner=user):
        if asset.file:
            found.append((asset.file.storage, asset.file.name))

    prefixes = [f"evidence/{user.pk}/"]
    if organization:
        prefixes.append(f"{organization.pk}/")
    for prefix in prefixes:
        found += [(default_storage, name) for name in _walk(default_storage, prefix)]
    return found


def _remove(files: list[tuple[object, str]]) -> None:
    """Borra cada archivo una vez; uno que ya no está no detiene a los demás."""
    seen: set[tuple[int, str]] = set()
    for storage, name in files:
        key = (id(storage), name)
        if key in seen:
            continue
        seen.add(key)
        try:
            storage.delete(name)
        except Exception:  # noqa: BLE001 — un archivo no puede frenar el resto
            logger.warning("Account file could not be deleted", extra={"file": name})


@transaction.atomic
def purge_account(*, user: User) -> dict[str, int]:
    """Borra la cuenta y todo lo suyo. No se puede deshacer.

    Returns:
        Cuántas filas y archivos se borraron, para el registro.
    """
    files = _files_of(user)
    user_id = str(user.pk)

    # Del más dependiente al menos: cada paso quita lo que protegía al siguiente.
    counts = {
        "worker_payments": WorkerPayment.objects.filter(owner=user).delete()[0],
        "payments": Payment.objects.filter(owner=user).delete()[0],
        # Con el proyecto se van sus avances, sus fotos y su reparto.
        "projects": Project.objects.filter(owner=user).delete()[0],
        # Con la cotización, sus partidas.
        "quotes": Quote.objects.filter(owner=user).delete()[0],
        "workers": Worker.objects.filter(owner=user).delete()[0],
        "tariffs": Tariff.objects.filter(owner=user).delete()[0],
        "clients": Client.objects.filter(owner=user).delete()[0],
        "plans": Plan.objects.filter(owner=user).delete()[0],
        "plan_assets": PlanAsset.objects.filter(owner=user).delete()[0],
        "catalog_models": CatalogModel.objects.filter(owner=user).delete()[0],
        # La cuenta se lleva su organización, su suscripción, sus códigos y sus
        # constancias de aceptación.
        "account": user.delete()[0],
    }
    counts["files"] = len({name for _, name in files})
    transaction.on_commit(lambda: _remove(files))
    logger.info("Account deleted", extra={"user_id": user_id, **counts})
    return counts
