"""RED tests for US-83 — dejar un mensaje sin abrir cuenta.

La página terminaba en «Crea tu cuenta gratis» y en el pie. Quien dudaba se iba
sin dejar rastro: no había ni contacto, ni WhatsApp, ni formulario. Esto es la
salida para el que hoy no se registra.
"""

import pytest
from rest_framework import status

URL = "/api/contact/"


@pytest.mark.django_db
class TestContactLead:
    """US-83: recibir un mensaje de alguien que todavía no es cliente."""

    def test_anyone_can_leave_a_message(self, api_client) -> None:
        """Flujo principal - Sin cuenta y sin sesión, el mensaje llega."""
        response = api_client.post(
            URL,
            {
                "name": "Javier López",
                "phone": "5512345678",
                "message": "Quiero saber si sirve para remodelaciones.",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["detail"]

    def test_the_message_is_stored(self, api_client) -> None:
        """Flujo principal - Queda guardado para poder devolver la llamada."""
        from apps.leads.models import Lead

        api_client.post(
            URL,
            {"name": "Javier López", "phone": "5512345678", "message": "Hola"},
            format="json",
        )

        lead = Lead.objects.get()
        assert lead.name == "Javier López"
        assert lead.phone == "5512345678"
        assert lead.message == "Hola"

    def test_a_name_and_a_way_to_answer_are_required(self, api_client) -> None:
        """Caso alternativo - Sin nombre no se puede contestar."""
        response = api_client.post(URL, {"phone": "5512345678"}, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "name" in response.data

    def test_either_phone_or_email_is_enough(self, api_client) -> None:
        """Flujo principal - Con el correo basta, sin dar el teléfono."""
        response = api_client.post(
            URL,
            {"name": "Carmen", "email": "carmen@obra.mx", "message": "Info"},
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED

    def test_without_any_contact_it_is_rejected(self, api_client) -> None:
        """Caso alternativo - Un mensaje al que no se puede responder no sirve."""
        response = api_client.post(URL, {"name": "Carmen"}, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_an_invalid_email_is_rejected(self, api_client) -> None:
        """Caso alternativo - Un correo mal escrito se avisa al escribirlo."""
        response = api_client.post(
            URL, {"name": "Carmen", "email": "no-es-correo"}, format="json"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "email" in response.data

    def test_the_message_is_trimmed_and_bounded(self, api_client) -> None:
        """Caso de borde - Un mensaje enorme no entra entero en la base."""
        response = api_client.post(
            URL,
            {"name": "Carmen", "phone": "55", "message": "x" * 3000},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "message" in response.data

    def test_nobody_can_read_the_messages_through_the_api(self, api_client) -> None:
        """Caso de borde - Se pueden dejar, no leer: se leen en el admin."""
        response = api_client.get(URL)

        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED
