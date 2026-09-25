"""Assets read queries (account-scoped)."""

from django.db.models import QuerySet

from apps.assets.models import PlanAsset


def list_assets_for_owner(*, owner) -> QuerySet[PlanAsset]:
    """Los archivos del editor que tiene esa cuenta."""
    return PlanAsset.objects.filter(owner=owner)


def missing_paths(*, owner, paths: list[str]) -> list[str]:
    """De esas rutas, las que la cuenta todavía no tiene.

    A library brings dozens of files; re-uploading all of them on every import
    would be paying the site's connection for nothing.
    """
    stored = set(
        PlanAsset.objects.filter(owner=owner, path__in=paths).values_list(
            "path", flat=True
        )
    )
    return [path for path in paths if path not in stored]
