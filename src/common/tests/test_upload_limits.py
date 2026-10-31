"""Subidas que caben en Vercel y juzgadas por su contenido (API-02 · iteracion-26 #19).

Una función de Vercel no recibe cuerpos de más de 4.5 MB: responde 413 antes
de Django y, sin cabeceras de CORS, la SPA lo lee como «Sin conexión». Cada
archivo que viaja por la API cabe en ``UPLOAD_MAX_BYTES`` (4 MiB, del entorno),
y un despliegue en Vercel con un tope mayor no sale (``core.E002``). Toda
imagen pasa por la firma real (filetype) y por Pillow ``verify()``: una rota es
un 400, nunca un 500.
"""

import io
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
from django.core.checks import run_checks
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from rest_framework import status
from rest_framework.exceptions import ValidationError

import core.settings as core_settings
from apps.assets.models import PlanAsset
from apps.planner import photo_conversion
from common.validators import IMAGES, TEXTURES, validate_upload

MIB = 1024 * 1024
SRC = Path(core_settings.__file__).resolve().parents[1]
CORRUPT = "Imagen corrupta o demasiado grande."
UUID_NAME = re.compile(r"[0-9a-f]{32}\.[a-z0-9]+$")


def image(fmt: str = "PNG", size=(10, 10), mode: str = "RGB") -> bytes:
    buffer = io.BytesIO()
    Image.new(mode, size).save(buffer, fmt)
    return buffer.getvalue()


def corrupt_png() -> bytes:
    """Firma de PNG válida, CRC del primer IDAT roto: Pillow lanza SyntaxError."""
    data = bytearray(image("PNG"))
    i = data.index(b"IDAT")
    data[i + 4 + int.from_bytes(data[i - 4 : i], "big")] ^= 0xFF
    return bytes(data)


def subir(nombre: str, contenido: bytes) -> SimpleUploadedFile:
    return SimpleUploadedFile(nombre, contenido)


class TestElTope:
    """API-02 · un solo tope por archivo, del entorno, que cabe en Vercel."""

    def test_the_default_fits_vercels_body(self) -> None:
        assert core_settings.UPLOAD_MAX_BYTES == 4 * MIB
        # Los topes propios que viajan por la función no pasan de él.
        assert core_settings.PLAN_ASSET_MAX_BYTES == 4 * MIB
        assert core_settings.DOCUMENT_EMAIL_MAX_BYTES == 4 * MIB
        assert core_settings.PHOTO_PLAN_MAX_BYTES <= 4 * MIB

    def test_it_comes_from_the_environment(self) -> None:
        salida = subprocess.run(  # noqa: S603 -- el mismo intérprete, sin shell
            [
                sys.executable,
                "-c",
                "from django.conf import settings as s; print(s.UPLOAD_MAX_BYTES)",
            ],
            cwd=SRC,
            env={
                **os.environ,
                "DJANGO_SETTINGS_MODULE": "core.settings",
                "UPLOAD_MAX_BYTES": "1048576",
            },
            capture_output=True,
            text=True,
            check=True,
        )

        assert salida.stdout.strip() == "1048576"


class TestDespliegueEnVercel:
    """API-02 · core.E002: en Vercel ningún tope de subida pasa de 4 MiB."""

    def test_upload_limit_over_the_vercel_body_cap_fails_the_system_check(
        self, monkeypatch, settings
    ) -> None:
        monkeypatch.setenv("VERCEL", "1")
        settings.UPLOAD_MAX_BYTES = 5_000_000

        assert "core.E002" in {m.id for m in run_checks(tags=["security"])}

    @pytest.mark.parametrize(
        "nombre", ["PLAN_ASSET_MAX_BYTES", "DOCUMENT_EMAIL_MAX_BYTES"]
    )
    def test_any_cap_through_the_function_counts(
        self, monkeypatch, settings, nombre
    ) -> None:
        monkeypatch.setenv("VERCEL", "1")
        setattr(settings, nombre, 10 * MIB)

        errores = [m for m in run_checks(tags=["security"]) if m.id == "core.E002"]

        assert errores and nombre in errores[0].msg

    def test_at_four_mib_it_deploys(self, monkeypatch) -> None:
        monkeypatch.setenv("VERCEL", "1")

        assert "core.E002" not in {m.id for m in run_checks(tags=["security"])}

    def test_off_vercel_a_bigger_cap_is_allowed(self, monkeypatch, settings) -> None:
        monkeypatch.delenv("VERCEL", raising=False)
        settings.UPLOAD_MAX_BYTES = 5_000_000

        assert "core.E002" not in {m.id for m in run_checks(tags=["security"])}


class TestPillowVerify:
    """API-02 · una imagen rota o descomunal es un 400 con su mensaje."""

    def test_a_corrupt_png_is_refused_not_a_500(self) -> None:
        with pytest.raises(ValidationError) as error:
            validate_upload(
                subir("foto.png", corrupt_png()),
                allowed=IMAGES,
                max_bytes=MIB,
                max_pixels=1_000_000,
            )

        assert error.value.detail == [CORRUPT]

    def test_without_a_pixel_cap_the_image_is_verified_too(self) -> None:
        """Las texturas no pasaban un tope de píxeles: tampoco pasaban por Pillow."""
        with pytest.raises(ValidationError) as error:
            validate_upload(
                subir("azulejo.png", corrupt_png()), allowed=TEXTURES, max_bytes=MIB
            )

        assert error.value.detail == [CORRUPT]

    def test_too_many_pixels_says_so_not_corrupt(self) -> None:
        archivo = subir("grande.png", image("PNG", (200, 200), mode="1"))

        with pytest.raises(ValidationError) as error:
            validate_upload(archivo, allowed=IMAGES, max_bytes=MIB, max_pixels=10_000)

        assert error.value.detail == ["La imagen excede las dimensiones máximas."]

    @pytest.mark.parametrize("fmt", ["JPEG", "PNG", "WEBP", "GIF"])
    def test_a_real_image_passes_and_the_file_is_rewound(self, fmt) -> None:
        archivo = subir("foto", image(fmt))

        assert validate_upload(archivo, allowed=IMAGES, max_bytes=MIB) in {
            "jpg",
            "png",
            "webp",
            "gif",
        }
        assert archivo.tell() == 0


@pytest.mark.django_db
class TestPorCadaSubida:
    """API-02 · el tope y la validación en cada ruta que recibe un archivo."""

    def _avance(self, user):
        from common.tests.test_cross_account import cuenta_completa

        return cuenta_completa(user)["project"].progresses.first()

    def _evidencia(self, client, avance, nombre, contenido):
        return client.post(
            f"/api/progresses/{avance.id}/evidence/",
            {"image": subir(nombre, contenido)},
            format="multipart",
        )

    def test_evidence_size_boundary(self, authenticated_client, user, settings):
        settings.UPLOAD_MAX_BYTES = 64 * 1024
        avance = self._avance(user)
        jpeg = image("JPEG")
        al_tope = jpeg + b"\0" * (settings.UPLOAD_MAX_BYTES - len(jpeg))

        dentro = self._evidencia(authenticated_client, avance, "a.jpg", al_tope)
        fuera = self._evidencia(authenticated_client, avance, "b.jpg", al_tope + b"\0")

        assert dentro.status_code == status.HTTP_201_CREATED
        assert fuera.status_code == status.HTTP_400_BAD_REQUEST
        assert avance.evidences.count() == 1

    def test_a_corrupt_evidence_photo_is_400(self, authenticated_client, user):
        avance = self._avance(user)

        response = self._evidencia(
            authenticated_client, avance, "foto.png", corrupt_png()
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert CORRUPT in str(response.data)
        assert not avance.evidences.exists()

    def test_a_path_in_the_name_never_reaches_the_bucket(
        self, authenticated_client, user
    ):
        avance = self._avance(user)

        self._evidencia(
            authenticated_client, avance, "../../etc/passwd.jpg", image("JPEG")
        )

        nombre = avance.evidences.get().image.name
        assert nombre.startswith(f"evidence/{user.id}/")
        assert UUID_NAME.search(nombre) and ".." not in nombre
        assert nombre.endswith(".jpg")

    def test_a_corrupt_texture_is_400(self, authenticated_client):
        response = authenticated_client.post(
            "/api/plan-assets/",
            {
                "path": "sh3t/azulejo.png",
                "kind": "texture",
                "file": subir("azulejo.png", corrupt_png()),
            },
            format="multipart",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert not PlanAsset.objects.exists()

    def test_a_png_named_jpg_is_stored_as_png(self, authenticated_client):
        """El nombre guardado sale del tipo detectado, nunca del que trae el cliente."""
        authenticated_client.post(
            "/api/plan-assets/",
            {
                "path": "sh3t/azulejo.jpg",
                "kind": "texture",
                "file": subir("azulejo.jpg", image("PNG")),
            },
            format="multipart",
        )

        assert PlanAsset.objects.get().file.name.endswith(".png")

    def test_a_corrupt_plan_photo_never_reaches_claude(
        self, authenticated_client, mocker
    ):
        convertir = mocker.patch.object(photo_conversion, "convert_photo")

        response = authenticated_client.post(
            "/api/plans/photo-conversions/",
            {"photo": subir("plano.png", corrupt_png())},
            format="multipart",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "photo" in response.data
        convertir.assert_not_called()

    def test_a_plan_photo_with_too_many_pixels_never_reaches_claude(
        self, authenticated_client, mocker
    ):
        mocker.patch("apps.planner.serializers.PHOTO_MAX_PIXELS", 10_000)
        convertir = mocker.patch.object(photo_conversion, "convert_photo")

        response = authenticated_client.post(
            "/api/plans/photo-conversions/",
            {"photo": subir("plano.png", image("PNG", (200, 200), mode="1"))},
            format="multipart",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "dimensiones" in str(response.data["photo"])
        convertir.assert_not_called()
