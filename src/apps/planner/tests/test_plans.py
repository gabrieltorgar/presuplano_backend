"""RED tests for US-92 — los planos viven en la cuenta, no en el navegador.

Un plano dibujado en la computadora del despacho no existía en el teléfono de
la obra: se guardaba en el almacenamiento del navegador que lo dibujó.
"""

import pytest
from rest_framework import status

URL = "/api/plans/"

DOCUMENT = {
    "id": "plan-1",
    "name": "Casa Reyes",
    "unit": "m",
    "walls": [
        {
            "id": "w1",
            "start": {"x": 0, "y": 0},
            "end": {"x": 4, "y": 0},
            "thickness": 0.15,
            "height": 2.5,
        }
    ],
    "rooms": [],
    "openings": [],
    "furniture": [],
    "dimensions": [],
    "viewpoints": [],
    "levels": [],
    "groups": [],
    "textures": [],
    "compass": {
        "northAngle": 0,
        "date": "2026-06-21",
        "time": "12:00",
        "latitude": 19.4,
    },
    "updatedAt": "2026-09-24T10:00:00.000Z",
}


def detail(plan_id: str) -> str:
    return f"{URL}{plan_id}/"


@pytest.mark.django_db
class TestPlans:
    """US-92: guardar, listar, abrir y borrar planos de la cuenta."""

    def test_a_plan_saved_here_opens_anywhere(self, authenticated_client) -> None:
        """Flujo principal - Lo dibujado en un dispositivo se abre en otro."""
        created = authenticated_client.post(
            URL, {"name": "Casa Reyes", "document": DOCUMENT}, format="json"
        )

        assert created.status_code == status.HTTP_201_CREATED
        opened = authenticated_client.get(detail(created.data["id"]))

        assert opened.status_code == status.HTTP_200_OK
        assert opened.data["name"] == "Casa Reyes"
        # El documento vuelve entero: es el mismo que serializa el editor.
        assert opened.data["document"]["walls"][0]["thickness"] == 0.15

    def test_the_list_does_not_carry_the_whole_document(
        self, authenticated_client
    ) -> None:
        """Flujo principal - La lista es de resúmenes.

        Pintar cinco renglones no puede costar bajarse cinco planos enteros.
        """
        authenticated_client.post(
            URL, {"name": "Casa Reyes", "document": DOCUMENT}, format="json"
        )

        listed = authenticated_client.get(URL)

        assert listed.status_code == status.HTTP_200_OK
        assert len(listed.data) == 1
        assert listed.data[0]["name"] == "Casa Reyes"
        assert "updated_at" in listed.data[0]
        assert "document" not in listed.data[0]

    def test_saving_again_replaces_the_document(self, authenticated_client) -> None:
        """Flujo principal - Guardar otra vez deja la versión nueva."""
        created = authenticated_client.post(
            URL, {"name": "Casa Reyes", "document": DOCUMENT}, format="json"
        )
        changed = {**DOCUMENT, "walls": []}

        updated = authenticated_client.put(
            detail(created.data["id"]),
            {"name": "Casa Reyes (revisión)", "document": changed},
            format="json",
        )

        assert updated.status_code == status.HTTP_200_OK
        assert updated.data["name"] == "Casa Reyes (revisión)"
        assert updated.data["document"]["walls"] == []

    def test_plans_of_another_account_do_not_exist(
        self, authenticated_client, user_factory
    ) -> None:
        """Caso de borde - Un plano ajeno no se lista ni se abre."""
        from apps.planner.models import Plan

        otra = user_factory()
        ajeno = Plan.objects.create(owner=otra, name="Plano ajeno", document=DOCUMENT)

        listed = authenticated_client.get(URL)
        opened = authenticated_client.get(detail(str(ajeno.pk)))

        assert listed.data == []
        assert opened.status_code == status.HTTP_404_NOT_FOUND

    def test_without_a_session_there_are_no_plans(self, api_client) -> None:
        """Caso de borde - Los planos son de una cuenta, siempre."""
        response = api_client.get(URL)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_the_name_is_required(self, authenticated_client) -> None:
        """Caso de borde - Un plano sin nombre no se guarda."""
        response = authenticated_client.post(
            URL, {"name": "", "document": DOCUMENT}, format="json"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "nombre" in str(response.data).lower()

    def test_a_document_too_heavy_is_refused_with_a_reason(
        self, authenticated_client
    ) -> None:
        """Caso de borde - Un escaneo enorme se rechaza explicando qué pesa.

        Una textura suelta o un plano de fondo viajan dentro del documento; sin
        tope, un escaneo de veinte megas se llevaría la base de datos por
        delante.
        """
        gordo = {
            **DOCUMENT,
            "background": {"src": "data:image/png;base64," + "A" * 5_000_000},
        }

        response = authenticated_client.post(
            URL, {"name": "Casa Reyes", "document": gordo}, format="json"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "pesa" in str(response.data).lower()

    def test_deleting_takes_it_off_the_list(self, authenticated_client) -> None:
        """Flujo principal - Borrar el plano lo quita de la cuenta."""
        created = authenticated_client.post(
            URL, {"name": "Casa Reyes", "document": DOCUMENT}, format="json"
        )

        removed = authenticated_client.delete(detail(created.data["id"]))

        assert removed.status_code == status.HTTP_204_NO_CONTENT
        assert authenticated_client.get(URL).data == []

    def test_the_list_starts_with_the_one_touched_last(
        self, authenticated_client
    ) -> None:
        """Flujo principal - Lo último que se tocó, primero."""
        primero = authenticated_client.post(
            URL, {"name": "Primero", "document": DOCUMENT}, format="json"
        )
        authenticated_client.post(
            URL, {"name": "Segundo", "document": DOCUMENT}, format="json"
        )
        authenticated_client.put(
            detail(primero.data["id"]),
            {"name": "Primero", "document": DOCUMENT},
            format="json",
        )

        nombres = [plan["name"] for plan in authenticated_client.get(URL).data]

        assert nombres == ["Primero", "Segundo"]

    def test_the_plan_keeps_the_id_the_editor_gave_it(
        self, authenticated_client
    ) -> None:
        """Flujo principal - El mismo plano se llama igual en todas partes.

        El editor le pone el id al crearlo y con ese id vive en su dirección:
        si el servidor le pusiera otro, el plano del teléfono y el de la
        computadora serían dos.
        """
        propio = "7f1d2c3b-4a5e-4f60-8123-abcdefabcdef"

        created = authenticated_client.post(
            URL,
            {"id": propio, "name": "Casa Reyes", "document": DOCUMENT},
            format="json",
        )

        assert created.status_code == status.HTTP_201_CREATED
        assert str(created.data["id"]) == propio
        assert (
            authenticated_client.get(detail(propio)).status_code == status.HTTP_200_OK
        )

    def test_the_summary_says_when_the_editor_stamped_it(
        self, authenticated_client
    ) -> None:
        """Flujo principal - La lista trae la fecha del propio documento.

        Es con la que el dispositivo decide qué copia es la nueva, sin depender
        de que su reloj y el del servidor coincidan.
        """
        authenticated_client.post(
            URL, {"name": "Casa Reyes", "document": DOCUMENT}, format="json"
        )

        resumen = authenticated_client.get(URL).data[0]

        assert resumen["document_updated_at"] == DOCUMENT["updatedAt"]
