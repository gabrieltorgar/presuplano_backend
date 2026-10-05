"""Upload-path helpers that isolate media per tenant (owning account)."""


def evidence_upload_to(instance, filename: str) -> str:
    """Scope progress evidence by owning account.

    Path: ``evidence/<owner_id>/<filename>`` so no account can read or overwrite
    another's media even when they share a bucket.
    """
    owner_id = instance.progress.project.owner_id
    return f"evidence/{owner_id}/{filename}"


def organization_id_for(user) -> str:
    """El id de la organización de esa cuenta, creándola si aún no existe.

    Every file in the bucket hangs from it —logo, textures, furniture— so it is
    the one folder name that must never change: the account's own uuid.
    """
    # Import local: `common` no depende de las apps, y esto se llama al subir.
    from apps.accounts.services import get_my_organization

    return str(get_my_organization(user=user).id)


def organization_logo_upload_to(instance, filename: str) -> str:
    """Path: ``<organización>/logo/<archivo>``."""
    return f"{instance.id}/logo/{filename}"


def plan_asset_upload_to(instance, filename: str) -> str:
    """Path: ``<organización>/texturas|inmobiliario/<archivo>``.

    Two folders, named as the trade names them, so what is in the bucket can be
    read by a person who never saw this code.
    """
    folder = "texturas" if instance.kind == "texture" else "inmobiliario"
    return f"{organization_id_for(instance.owner)}/{folder}/{filename}"
