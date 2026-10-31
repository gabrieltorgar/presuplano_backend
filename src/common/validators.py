"""Archivos juzgados por su contenido (iteracion-12 #5).

La extensión y el tipo que declara el navegador los pone quien sube: lo que
cuenta son los primeros bytes. Un HTML con nombre de foto, servido desde el
bucket de la aplicación, sería un script corriendo con su dominio.
"""

import filetype
from PIL import Image
from rest_framework.exceptions import ValidationError

# Guarda contra las «bombas de descompresión»: una imagen chica que al abrirse
# pide gigas de memoria.
Image.MAX_IMAGE_PIXELS = 40_000_000

#: Lo que se acepta como imagen (extensión → tipo real). SVG nunca: lleva scripts.
IMAGES = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
    "gif": "image/gif",
}
#: Una textura puede venir también en BMP, como en Sweet Home 3D.
TEXTURES = {**IMAGES, "bmp": "image/bmp"}
PDF = {"pdf": "application/pdf"}

TOO_BIG = "El archivo excede el tamaño máximo."
NOT_ALLOWED = "Tipo de archivo no permitido."
CORRUPT = "Imagen corrupta o demasiado grande."
TOO_MANY_PIXELS = "La imagen excede las dimensiones máximas."

_HEAD = 2048


def _head(file) -> bytes:
    file.seek(0)
    head = file.read(_HEAD)
    file.seek(0)
    return head


def validate_upload(
    file,
    *,
    allowed: dict[str, str],
    max_bytes: int,
    max_pixels: int | None = None,
    too_big: str = TOO_BIG,
    not_allowed: str = NOT_ALLOWED,
) -> str:
    """Revisa tamaño y firma real; devuelve la extensión que le corresponde.

    Raises:
        ValidationError: pesa de más, su contenido no es de los permitidos o,
            siendo imagen, está rota o es demasiado grande.
    """
    if file.size > max_bytes:
        raise ValidationError(too_big)
    kind = filetype.guess(_head(file))
    if kind is None or kind.mime not in allowed.values():
        raise ValidationError(not_allowed)
    if kind.mime.startswith("image/"):
        _check_image(file, max_pixels or Image.MAX_IMAGE_PIXELS)
    return kind.extension


def _check_image(file, max_pixels: int) -> None:
    """Pillow la abre entera (``verify``) y cuenta sus píxeles (iteracion-26 #19).

    Toda imagen, también las que no traen tope propio (las texturas): una con
    la firma bien y los datos rotos era un 500 al guardarla o al leerla.
    """
    try:
        with Image.open(file) as image:
            image.verify()
        file.seek(0)
        with Image.open(file) as image:
            width, height = image.size
    except Exception as exc:  # SyntaxError, OSError, ValueError, DecompressionBomb…
        raise ValidationError(CORRUPT) from exc
    finally:
        file.seek(0)
    # Fuera del try: su propio mensaje nunca se vuelve «corrupta».
    if width * height > max_pixels:
        raise ValidationError(TOO_MANY_PIXELS)


#: Las mallas y materiales de texto que el editor sabe leer.
MESH_TEXT_EXTENSIONS = {"obj", "mtl", "gltf"}
_GLB_MAGIC = b"glTF"


def validate_mesh_part(file, *, max_bytes: int, original_name: str) -> str:
    """Una pieza de un mueble: malla, material o una de sus texturas.

    Se acepta una imagen de verdad, un glTF binario o un texto plano (OBJ, MTL,
    glTF); nada que sea un programa, un documento o una página. Devuelve la
    extensión con la que se guarda: la de texto sólo si es una de las suyas,
    para que el bucket nunca la sirva como otra cosa.
    """
    if file.size > max_bytes:
        raise ValidationError(TOO_BIG)
    head = _head(file)
    kind = filetype.guess(head)
    if kind is not None:
        if kind.mime in TEXTURES.values():
            return kind.extension
        raise ValidationError(NOT_ALLOWED)
    if head.startswith(_GLB_MAGIC):
        return "glb"
    if not _is_plain_text(head):
        raise ValidationError(NOT_ALLOWED)
    ext = original_name.rsplit(".", 1)[-1].lower() if "." in original_name else ""
    return ext if ext in MESH_TEXT_EXTENSIONS else "txt"


def _is_plain_text(head: bytes) -> bool:
    """Texto sin bytes nulos y que no empieza como marcado (HTML, SVG, XML)."""
    if b"\x00" in head:
        return False
    try:
        text = head.decode("utf-8")
    except UnicodeDecodeError:
        # Un corte a la mitad de un carácter no lo vuelve binario.
        try:
            text = head[:-3].decode("utf-8")
        except UnicodeDecodeError:
            text = head.decode("latin-1")
    return not text.lstrip("﻿ \t\r\n").startswith("<")
