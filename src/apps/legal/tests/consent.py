"""Lo que un formulario manda para aceptar los documentos vigentes."""

from apps.legal.documents import current_versions


def accepted() -> dict[str, str]:
    versions = current_versions()
    return {"terms_version": versions["terms"], "privacy_version": versions["privacy"]}
