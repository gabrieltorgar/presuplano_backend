"""Entregar un documento por correo, con la marca de quien lo firma.

El PDF ya se compartía a mano: se descargaba y se mandaba por donde fuera.
Esto lo entrega desde la aplicación y con el membrete puesto, que es lo que
distingue un documento del estudio de un archivo suelto.
"""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status

from apps.accounts.services import get_my_organization
from common.branding import OPTIMIZED_BY, PRESUPLANO_NAME

URL = "/api/documents/send/"

PDF = b"%PDF-1.4 documento de prueba"


@pytest.fixture
def correo(settings, mocker):
    """Resend configurado, con el envío interceptado."""
    settings.RESEND_API_KEY = "re_test"
    return mocker.patch("common.mail.send_email", return_value=True)


def enviar(client, **extra):
    payload = {
        "kind": "quote",
        "to": "cliente@correo.mx",
        "file": SimpleUploadedFile("cotizacion.pdf", PDF, "application/pdf"),
        **extra,
    }
    return client.post(URL, payload, format="multipart")


@pytest.mark.django_db
class TestEnvioDeDocumentos:
    """Los cuatro comprobantes salen por correo."""

    def test_a_quote_travels_with_its_pdf(self, authenticated_client, correo) -> None:
        """Flujo principal - La cotización llega con el PDF adjunto."""
        response = enviar(authenticated_client, reference="COT-0007", amount="12500.00")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["sent"] is True
        enviado = correo.call_args.kwargs
        assert enviado["to"] == "cliente@correo.mx"
        assert enviado["attachments"][0].content == PDF
        assert "COT-0007" in enviado["html"]
        assert "$12,500.00" in enviado["html"]

    def test_without_a_letterhead_it_is_presuplano_who_signs(
        self, authenticated_client, correo
    ) -> None:
        """Flujo principal - Sin organización configurada firma presuplano."""
        enviar(authenticated_client)

        html = correo.call_args.kwargs["html"]
        assert PRESUPLANO_NAME in html
        assert OPTIMIZED_BY not in html

    def test_with_a_letterhead_it_carries_its_colors_and_a_footer(
        self, authenticated_client, user, correo
    ) -> None:
        """Flujo principal - Con membrete, su color y el pie de presuplano."""
        organizacion = get_my_organization(user=user)
        organizacion.name = "Estudio Reyes"
        organizacion.color = "#0F766E"
        organizacion.save()

        enviar(authenticated_client)

        html = correo.call_args.kwargs["html"]
        assert "Estudio Reyes" in html
        assert "#0F766E" in html
        assert OPTIMIZED_BY in html

    def test_each_document_says_what_it_is(self, authenticated_client, correo) -> None:
        """Flujo alternativo - El asunto distingue los cuatro documentos."""
        for kind, esperado in (
            ("project_status", "Avance de tu proyecto"),
            ("payment_voucher", "Comprobante de pago"),
            ("collection_voucher", "Comprobante de cobro"),
        ):
            enviar(authenticated_client, kind=kind)
            assert esperado in correo.call_args.kwargs["subject"]

    def test_a_note_from_the_architect_travels_too(
        self, authenticated_client, correo
    ) -> None:
        """Flujo alternativo - El recado escrito a mano va en el cuerpo."""
        enviar(authenticated_client, message="Cualquier duda me dices, Ana.")

        assert "Cualquier duda me dices, Ana." in correo.call_args.kwargs["html"]

    def test_an_invalid_recipient_is_refused(
        self, authenticated_client, correo
    ) -> None:
        """Caso de borde - Sin un correo válido no hay envío."""
        response = enviar(authenticated_client, to="esto-no-es-un-correo")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert correo.called is False

    def test_a_document_too_big_is_refused_with_a_reason(
        self, authenticated_client, correo, settings
    ) -> None:
        """Caso de borde - Un adjunto enorme no sale."""
        settings.DOCUMENT_EMAIL_MAX_BYTES = 10

        response = enviar(authenticated_client)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "pesa más" in str(response.data)

    def test_without_resend_it_says_so_instead_of_pretending(
        self, authenticated_client, settings
    ) -> None:
        """Caso de borde - Sin correo configurado se dice, no se finge."""
        settings.RESEND_API_KEY = ""

        response = enviar(authenticated_client)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "no está configurado" in str(response.data)

    def test_without_a_session_nothing_is_sent(self, api_client, correo) -> None:
        """Caso de borde - Sin sesión no se manda nada."""
        response = enviar(api_client)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert correo.called is False
