"""Los dos documentos legales, tal como viven en el repositorio.

El texto es un archivo Markdown junto a este módulo, con una cabecera que dice
su título y su versión. Cambiar la versión es lo que hace que a todas las
cuentas se les vuelva a pedir aceptarlo: el texto se revisa como cualquier
otro cambio del código, y la versión que se aceptó queda registrada.
"""

from dataclasses import dataclass
from functools import cache
from pathlib import Path

from apps.legal.models import LegalDocumentKind

DOCUMENTS_DIR = Path(__file__).resolve().parent / "documents"

FILES = {
    LegalDocumentKind.TERMS: "terminos.md",
    LegalDocumentKind.PRIVACY: "privacidad.md",
}


@dataclass(frozen=True)
class LegalDocument:
    kind: str
    title: str
    version: str
    body: str


def parse(text: str) -> tuple[dict[str, str], str]:
    """Separa la cabecera (``---`` … ``---``) del cuerpo en Markdown."""
    lines = text.lstrip("﻿").splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("El documento no empieza con su cabecera («---»).")
    try:
        end = next(
            i for i, line in enumerate(lines[1:], start=1) if line.strip() == "---"
        )
    except StopIteration:
        raise ValueError("La cabecera del documento no se cierra («---»).") from None
    meta: dict[str, str] = {}
    for line in lines[1:end]:
        key, _, value = line.partition(":")
        if key.strip():
            meta[key.strip()] = value.strip()
    return meta, "\n".join(lines[end + 1 :]).strip() + "\n"


@cache
def load(kind: str) -> LegalDocument:
    """El documento vigente de ese tipo. Se lee una vez por proceso."""
    meta, body = parse((DOCUMENTS_DIR / FILES[kind]).read_text(encoding="utf-8"))
    title, version = meta.get("title", ""), meta.get("version", "")
    if not title or not version:
        raise ValueError(f"{FILES[kind]} necesita «title» y «version» en su cabecera.")
    return LegalDocument(kind=kind, title=title, version=version, body=body)


def current_versions() -> dict[str, str]:
    """La versión vigente de cada documento: lo que hay que haber aceptado."""
    return {kind: load(kind).version for kind in FILES}
