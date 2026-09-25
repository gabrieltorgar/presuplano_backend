"""El correo sale por la API de Resend, y un fallo no tumba lo que se hacía."""

import json
import logging
import urllib.error

import pytest

from common import mail
from common.branding import OPTIMIZED_BY, Brand
from common.emails import render_email


class FakeResponse:
    """Lo que devuelve urlopen, en pequeño."""

    def __init__(self, status: int) -> None:
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args) -> None:
        return None


@pytest.fixture
def configurado(settings):
    settings.RESEND_API_KEY = "re_test"
    settings.RESEND_FROM = "presuplano <hola@presuplano.mx>"


class TestResend:
    """Resend a pelo: una llamada HTTPS, y nada que pueda romper la pantalla."""

    def test_the_email_goes_out_with_its_key_and_body(
        self, configurado, mocker
    ) -> None:
        """Flujo principal - Un correo aceptado."""
        urlopen = mocker.patch("urllib.request.urlopen", return_value=FakeResponse(200))

        sent = mail.send_email(to="ana@estudio.mx", subject="Hola", html="<p>Hola</p>")

        assert sent is True
        request = urlopen.call_args.args[0]
        assert request.full_url == mail.RESEND_ENDPOINT
        assert request.headers["Authorization"] == "Bearer re_test"
        body = json.loads(request.data)
        assert body["to"] == ["ana@estudio.mx"]
        assert body["subject"] == "Hola"

    def test_the_client_says_who_it_is(self, configurado, mocker) -> None:
        """Caso de borde - Sin nombre, Cloudflare corta la petición.

        Regresión: con el `User-Agent` que pone urllib por omisión, la API de
        Resend contestaba 403 «error code: 1010» —la página de Cloudflare— y el
        envío no llegaba ni a aparecer en el registro de la cuenta.
        """
        urlopen = mocker.patch("urllib.request.urlopen", return_value=FakeResponse(200))

        mail.send_email(to="ana@estudio.mx", subject="x", html="x")

        cabeceras = urlopen.call_args.args[0].headers
        assert cabeceras["User-agent"] == mail.USER_AGENT
        assert "urllib" not in cabeceras["User-agent"]

    def test_an_attachment_travels_encoded(self, configurado, mocker) -> None:
        """Flujo principal - El PDF va en base64, como pide la API."""
        urlopen = mocker.patch("urllib.request.urlopen", return_value=FakeResponse(200))

        mail.send_email(
            to="ana@estudio.mx",
            subject="Cotización",
            html="<p>Va adjunta</p>",
            attachments=[mail.Attachment(filename="c.pdf", content=b"%PDF-1.4")],
        )

        adjunto = json.loads(urlopen.call_args.args[0].data)["attachments"][0]
        assert adjunto["filename"] == "c.pdf"
        assert adjunto["content"] == "JVBERi0xLjQ="

    def test_the_test_sender_is_flagged(self, settings, mocker, caplog) -> None:
        """Caso de borde - El remitente de pruebas no llega a un cliente.

        Funciona sin configurar nada, así que es fácil dejarlo puesto y no
        entender por qué la cotización nunca llegó.
        """
        settings.RESEND_API_KEY = "re_test"
        settings.RESEND_FROM = "presuplano <onboarding@resend.dev>"
        mocker.patch("urllib.request.urlopen", return_value=FakeResponse(200))

        with caplog.at_level(logging.WARNING, logger="apps"):
            assert mail.send_email(to="ana@estudio.mx", subject="x", html="x") is True

        assert any("RESEND_FROM" in record.message for record in caplog.records)

    def test_without_a_key_nothing_is_sent(self, settings) -> None:
        """Caso de borde - Sin llave no hay envío, y se sabe."""
        settings.RESEND_API_KEY = ""

        assert mail.is_configured() is False
        assert mail.send_email(to="ana@estudio.mx", subject="x", html="x") is False

    def test_a_refusal_does_not_break_the_caller(self, configurado, mocker) -> None:
        """Caso de borde - Resend rechaza y la aplicación sigue viva."""
        mocker.patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.HTTPError(
                mail.RESEND_ENDPOINT, 422, "Unprocessable", {}, None
            ),
        )

        assert mail.send_email(to="ana@estudio.mx", subject="x", html="x") is False

    def test_a_network_failure_does_not_break_the_caller(
        self, configurado, mocker
    ) -> None:
        """Caso de borde - Sin red tampoco se cae nada."""
        mocker.patch(
            "urllib.request.urlopen", side_effect=urllib.error.URLError("sin red")
        )

        assert mail.send_email(to="ana@estudio.mx", subject="x", html="x") is False


class TestPlantilla:
    """El cuerpo del correo se pinta con la marca que toque."""

    def test_the_brand_paints_the_header(self) -> None:
        """Flujo principal - Nombre, color y logotipo de quien firma."""
        brand = Brand(
            name="Estudio Reyes",
            color="#0F766E",
            logo_url="https://bucket/logo.png",
            optimized=True,
        )

        html = render_email(brand=brand, title="Tu cotización", intro="Va adjunta.")

        assert "Estudio Reyes" in html
        assert "#0F766E" in html
        assert "https://bucket/logo.png" in html
        assert OPTIMIZED_BY in html

    def test_what_someone_writes_cannot_become_html(self) -> None:
        """Caso de borde - Un recado no puede inyectar etiquetas."""
        brand = Brand(name="x", color="#000000", logo_url="", optimized=False)

        html = render_email(
            brand=brand,
            title="Tu cotización",
            intro="Va adjunta.",
            note="<script>alert(1)</script>",
        )

        assert "<script>" not in html
        assert "&lt;script&gt;" in html
