"""Configuración de seguridad de Django (TEC, bug iteracion-12 #6).

US-01 · US-125. Contraseñas que no se derivan del correo ni están en las listas
de las filtradas, una política de contenido (CSP) en todo lo que la API sirve
como HTML, el correo de nadie en los registros, y topes para lo que se pide y
lo que se manda.
"""

import logging
import os
import subprocess
import sys
from pathlib import Path

import pytest
from rest_framework import status

import core.settings as core_settings
from apps.accounts.tests.factories import UserFactory
from apps.clients.tests.factories import ClientFactory
from apps.legal.tests.consent import accepted
from common import mail


@pytest.mark.django_db
class TestContrasenasFuertes:
    """SEC-05: los cuatro validadores de Django se aplican de verdad."""

    def test_the_four_validators_are_configured(self) -> None:
        names = {
            v["NAME"].rsplit(".", 1)[-1] for v in core_settings.AUTH_PASSWORD_VALIDATORS
        }

        assert names == {
            "UserAttributeSimilarityValidator",
            "MinimumLengthValidator",
            "CommonPasswordValidator",
            "NumericPasswordValidator",
        }

    @pytest.mark.parametrize(
        "password",
        ["juanperez2026", "password123", "12345678901"],
    )
    def test_signup_refuses_a_weak_password(self, api_client, password) -> None:
        response = api_client.post(
            "/api/auth/register/",
            {"email": "juanperez@estudio.mx", "password": password, **accepted()},
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "password" in response.data

    def test_signup_with_a_strong_password_goes_through(self, api_client) -> None:
        response = api_client.post(
            "/api/auth/register/",
            {"email": "juanperez@estudio.mx", "password": "Teja-Roja-81", **accepted()},
        )

        assert response.status_code == status.HTTP_201_CREATED

    def test_changing_to_a_common_password_is_refused(self) -> None:
        from rest_framework.test import APIClient

        user = UserFactory(password="Teja-Roja-81")
        client = APIClient()
        client.force_authenticate(user)

        response = client.post(
            "/api/auth/me/password/",
            {"current_password": "Teja-Roja-81", "new_password": "qwertyuiop"},
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "new_password" in response.data


class TestPoliticaDeContenido:
    """SRV-01: CSP y Referrer-Policy en las respuestas de la API."""

    @pytest.mark.django_db
    def test_every_response_carries_a_strict_csp(self, client) -> None:
        response = client.get("/api/health/")

        # La API sirve JSON: nada que cargar (iteracion-26 #18).
        csp = response["Content-Security-Policy"]
        assert "default-src 'none'" in csp
        assert "frame-ancestors 'none'" in csp
        assert "base-uri 'none'" in csp
        assert "unsafe" not in csp

    @pytest.mark.django_db
    def test_only_the_admin_gets_what_unfold_needs(self, client) -> None:
        """Iteracion-13: Unfold usa Alpine (eval) y estilos en línea, sólo ahí."""
        admin = client.get("/admin/login/")["Content-Security-Policy"]
        api = client.get("/api/health/")["Content-Security-Policy"]

        assert "'unsafe-eval'" in admin
        assert "frame-ancestors 'none'" in admin
        assert "unsafe" not in api

    def test_production_serves_json_only(self) -> None:
        """Caso de borde - Sin API navegable no hay HTML que proteger en la API."""
        entorno = {k: v for k, v in os.environ.items() if k != "DEBUG"}
        entorno.update(VERCEL="1", DJANGO_SETTINGS_MODULE="core.settings")
        leer = (
            "from django.conf import settings as s;"
            "print(*s.REST_FRAMEWORK['DEFAULT_RENDERER_CLASSES'])"
        )

        salida = subprocess.run(  # noqa: S603 -- el mismo intérprete, sin shell
            [sys.executable, "-c", leer],
            cwd=Path(core_settings.__file__).resolve().parents[1],
            env=entorno,
            capture_output=True,
            text=True,
            check=True,
        )

        assert salida.stdout.split() == ["rest_framework.renderers.JSONRenderer"]

    @pytest.mark.django_db
    def test_the_referrer_policy_is_explicit(self, client) -> None:
        response = client.get("/api/health/")

        assert response["Referrer-Policy"] == "same-origin"


class TestCorreoEnLosRegistros:
    """CRD-01: el destinatario se registra enmascarado."""

    def test_mask_keeps_the_domain_and_the_first_letter(self) -> None:
        assert mail.mask_email("juan.perez@estudio.mx") == "j***@estudio.mx"
        assert mail.mask_email("sin-arroba") == "***"

    def test_a_sent_email_does_not_log_the_address(
        self, settings, mocker, caplog
    ) -> None:
        settings.RESEND_API_KEY = "re_test"
        respuesta = mocker.MagicMock(status=200)
        respuesta.__enter__.return_value.read.return_value = b'{"id": "1"}'
        respuesta.__enter__.return_value.status = 200
        mocker.patch.object(mail.urllib.request, "urlopen", return_value=respuesta)

        with caplog.at_level(logging.INFO, logger="apps"):
            mail.send_email(
                to="cliente.secreto@correo.mx", subject="Tu cotización", html="<p>x</p>"
            )

        assert "cliente.secreto@correo.mx" not in caplog.text
        assert "c***@correo.mx" in caplog.text


@pytest.mark.django_db
class TestTopesDeLoQueSePide:
    """VAL-06: una página no trae más de 100 y el cuerpo tiene tope."""

    def test_a_page_never_brings_more_than_a_hundred(self, user, authenticated_client):
        ClientFactory.create_batch(105, owner=user)

        response = authenticated_client.get("/api/clients/", {"page_size": 500})

        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 105
        assert len(response.data["results"]) == 100

    def test_without_asking_for_a_page_the_server_still_cuts_one(
        self, user, authenticated_client
    ):
        """Caso de borde - Sin page ni page_size llega la primera página."""
        ClientFactory.create_batch(3, owner=user)

        response = authenticated_client.get("/api/clients/")

        assert response.data["count"] == 3
        assert len(response.data["results"]) == 3

    def test_the_request_body_has_an_explicit_cap(self) -> None:
        """API-02 · iteracion-27 #7 — El tope del cuerpo es el de cada archivo
        (UPLOAD_MAX_BYTES, 4 MiB): cabe en los 4.5 MB de Vercel."""
        assert (
            core_settings.DATA_UPLOAD_MAX_MEMORY_SIZE == core_settings.UPLOAD_MAX_BYTES
        )
        assert core_settings.DATA_UPLOAD_MAX_MEMORY_SIZE < 4_500_000
        assert core_settings.REST_FRAMEWORK["DEFAULT_PAGINATION_CLASS"] == (
            "common.pagination.DefaultPagination"
        )
