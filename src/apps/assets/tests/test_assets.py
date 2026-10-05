"""Pruebas de los archivos del editor (US-101).

Una textura o una malla importada vivía sólo en el navegador que la importó:
abrir el plano en otro dispositivo dejaba cajas grises y muros en blanco.
"""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status

from apps.accounts.services import get_my_organization
from apps.assets.models import CatalogModel, PlanAsset

URL = "/api/plan-assets/"

PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
)


def subir(
    client, path="sh3t/azulejo.png", kind="texture", data=PNG, name="azulejo.png"
):
    return client.post(
        URL,
        {
            "path": path,
            "kind": kind,
            "file": SimpleUploadedFile(name, data, "image/png"),
        },
        format="multipart",
    )


@pytest.mark.django_db
class TestPlanAssets:
    """US-101: lo importado vive en la cuenta, no en el dispositivo."""

    def test_an_imported_texture_lives_in_the_account(
        self, authenticated_client, user
    ) -> None:
        """Flujo principal - Subir una textura."""
        response = subir(authenticated_client)

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["path"] == "sh3t/azulejo.png"
        assert response.data["url"]
        assert response.data["size"] == len(PNG)

    def test_the_bucket_folder_hangs_from_the_organization(
        self, authenticated_client, user
    ) -> None:
        """Flujo principal - Cada archivo en su carpeta."""
        subir(authenticated_client)
        subir(
            authenticated_client, path="sh3f/silla.obj", kind="model", name="silla.obj"
        )

        organizacion = get_my_organization(user=user)
        rutas = {asset.kind: asset.file.name for asset in PlanAsset.objects.all()}
        assert rutas["texture"].startswith(f"{organizacion.id}/texturas/")
        assert rutas["model"].startswith(f"{organizacion.id}/inmobiliario/")

    def test_uploading_the_same_path_twice_does_not_duplicate(
        self, authenticated_client
    ) -> None:
        """Caso de borde - La misma ruta es el mismo archivo."""
        subir(authenticated_client)

        segunda = subir(authenticated_client)

        assert segunda.status_code == status.HTTP_200_OK
        assert PlanAsset.objects.count() == 1

    def test_the_list_says_what_the_account_has(self, authenticated_client) -> None:
        """Flujo principal - Lo que la cuenta ya tiene."""
        subir(authenticated_client)
        subir(
            authenticated_client, path="sh3f/silla.obj", kind="model", name="silla.obj"
        )

        response = authenticated_client.get(URL)

        assert {item["path"] for item in response.data} == {
            "sh3t/azulejo.png",
            "sh3f/silla.obj",
        }

    def test_it_says_which_ones_are_missing(self, authenticated_client) -> None:
        """Flujo principal - Sólo se sube lo que falta.

        Una biblioteca trae decenas de archivos; volver a subirlos todos en
        cada importación sería pagar la red de la obra por nada.
        """
        subir(authenticated_client)

        response = authenticated_client.post(
            f"{URL}missing/",
            {"paths": ["sh3t/azulejo.png", "sh3t/madera.png"]},
            format="json",
        )

        assert response.data["missing"] == ["sh3t/madera.png"]

    def test_a_file_too_big_is_refused_with_a_reason(
        self, authenticated_client, settings
    ) -> None:
        """Caso de borde - Un archivo enorme no entra."""
        settings.PLAN_ASSET_MAX_BYTES = 10

        response = subir(authenticated_client, data=PNG * 10)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "pesa" in str(response.data).lower()

    def test_assets_are_isolated_per_account(
        self, authenticated_client, user_factory
    ) -> None:
        """Caso de borde - Los archivos de otra cuenta no se ven."""
        otra = user_factory()
        PlanAsset.objects.create(owner=otra, path="ajena.png", file="x.png", size=1)

        response = authenticated_client.get(URL)

        assert response.data == []

    def test_without_a_session_there_are_no_assets(self, api_client) -> None:
        """Caso de borde - Sin sesión no hay archivos."""
        assert api_client.get(URL).status_code == status.HTTP_401_UNAUTHORIZED


MODELOS = "/api/plan-models/"

SILLA = {
    "id": "eTeks#chair",
    "name": "Silla",
    "category": "Comedor",
    "width": 0.45,
    "depth": 0.45,
    "height": 0.9,
    "format": "sh3f",
    "modelRef": "sh3f/chair.obj",
}


@pytest.mark.django_db
class TestCatalogoDeModelos:
    """El catálogo de mobiliario vive en la cuenta, no en el navegador."""

    def test_an_imported_library_lives_in_the_account(
        self, authenticated_client
    ) -> None:
        """Flujo principal - Guardar el catálogo y volver a leerlo."""
        guardado = authenticated_client.post(
            MODELOS, {"models": [SILLA]}, format="json"
        )

        assert guardado.status_code == status.HTTP_201_CREATED
        assert guardado.data["stored"] == 1
        assert authenticated_client.get(MODELOS).data == [SILLA]

    def test_importing_the_same_library_twice_does_not_duplicate(
        self, authenticated_client
    ) -> None:
        """Caso de borde - El mismo id es la misma ficha."""
        authenticated_client.post(MODELOS, {"models": [SILLA]}, format="json")

        renombrada = {**SILLA, "name": "Silla de comedor"}
        authenticated_client.post(MODELOS, {"models": [renombrada]}, format="json")

        assert authenticated_client.get(MODELOS).data == [renombrada]

    def test_a_fiche_without_an_id_is_refused(self, authenticated_client) -> None:
        """Caso de borde - Sin id no hay con qué volver a pedirla."""
        response = authenticated_client.post(
            MODELOS, {"models": [{"name": "Silla"}]}, format="json"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_a_removed_model_leaves_the_account(self, authenticated_client) -> None:
        """Flujo alternativo - Quitar una ficha del catálogo."""
        authenticated_client.post(MODELOS, {"models": [SILLA]}, format="json")

        quitado = authenticated_client.post(
            f"{MODELOS}remove/", {"ids": [SILLA["id"]]}, format="json"
        )

        assert quitado.data["removed"] == 1
        assert authenticated_client.get(MODELOS).data == []

    def test_the_catalog_is_isolated_per_account(
        self, authenticated_client, user_factory
    ) -> None:
        """Caso de borde - El catálogo de otra cuenta no se ve."""
        otra = user_factory()
        CatalogModel.objects.create(owner=otra, model_id="ajeno", fiche=SILLA)

        assert authenticated_client.get(MODELOS).data == []

    def test_without_a_session_there_is_no_catalog(self, api_client) -> None:
        """Caso de borde - Sin sesión no hay catálogo."""
        assert api_client.get(MODELOS).status_code == status.HTTP_401_UNAUTHORIZED
