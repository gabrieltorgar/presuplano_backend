"""La SPA recibe su cookie CSRF antes de escribir (iteracion-24 #1).

Hasta 3.12.0 el token CSRF llegaba solo con el login o con /me/: un navegador
nuevo no lo tenía antes del primer POST, y /api/auth/csrf/ —la ruta que la
SPA llama al arrancar— respondía 404 en producción. El nombre y el dominio de
la cookie eran los de Django por omisión, sin poder cambiarlos por entorno, y
la SPA no podía leer Retry-After de un 429 servido desde otro origen.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from django.conf import settings
from rest_framework import status

import core.settings as core_settings
from common.auth_cookies import ACCESS_COOKIE

CSRF = "/api/auth/csrf/"
SPA = "https://itzaka.test"


@pytest.mark.django_db
class TestLaCookieCsrf:
    def test_a_new_browser_gets_the_csrf_cookie(self, api_client) -> None:
        """SEC-04.3 · iteracion-24 #1 — Sin sesión, deja la cookie que la SPA lee."""
        response = api_client.get(CSRF)

        assert response.status_code == status.HTTP_204_NO_CONTENT
        cookie = response.cookies[settings.CSRF_COOKIE_NAME]
        assert cookie.value
        assert not cookie["httponly"]
        assert cookie["samesite"] == "Lax"

    def test_an_expired_session_cookie_does_not_turn_it_into_401(
        self, api_client
    ) -> None:
        """SEC-04.3 · iteracion-24 #1 — Una cookie de acceso inválida no la bloquea."""
        api_client.cookies[ACCESS_COOKIE] = "vencida"

        response = api_client.get(CSRF)

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert response.cookies[settings.CSRF_COOKIE_NAME].value

    def test_it_only_answers_get(self, api_client) -> None:
        """SEC-04.3 · iteracion-24 #1 — No cambia nada: no acepta escrituras."""
        response = api_client.post(CSRF)

        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED


@pytest.mark.django_db
class TestCorsParaLaSpa:
    def test_retry_after_is_readable_from_the_spa(self, api_client, settings) -> None:
        """SEC-04.6 · iteracion-24 #1 — La SPA lee la espera de un 429."""
        settings.CORS_ALLOWED_ORIGINS = [SPA]

        response = api_client.get(CSRF, HTTP_ORIGIN=SPA)

        assert response["Access-Control-Allow-Origin"] == SPA
        expuestas = response["Access-Control-Expose-Headers"].lower().split(", ")
        assert "retry-after" in expuestas


def ajustes_con(entorno_extra: dict[str, str]) -> dict:
    """Los ajustes de CSRF y CORS que resultan de un entorno dado."""
    nombres = (
        "CSRF_COOKIE_NAME",
        "CSRF_COOKIE_DOMAIN",
        "CSRF_TRUSTED_ORIGINS",
        "CORS_ALLOWED_ORIGINS",
    )
    entorno = {
        k: v
        for k, v in os.environ.items()
        if k not in nombres and not k.startswith("VERCEL")
    }
    entorno["DJANGO_SETTINGS_MODULE"] = "core.settings"
    entorno.update(entorno_extra)
    salida = subprocess.run(  # noqa: S603 -- el mismo intérprete, sin shell
        [
            sys.executable,
            "-c",
            "import json; from django.conf import settings as s; "
            f"print(json.dumps({{n: getattr(s, n) for n in {nombres!r}}}))",
        ],
        cwd=Path(core_settings.__file__).resolve().parents[1],
        env=entorno,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(salida.stdout)


class TestCsrfYCorsDesdeElEntorno:
    def test_without_variables_the_cookie_is_host_only_csrftoken(self) -> None:
        """SEC-04 · iteracion-26 #9 — En local (DEBUG), la cookie queda sin Domain."""
        ajustes = ajustes_con({"DEBUG": "True"})

        assert ajustes["CSRF_COOKIE_NAME"] == "csrftoken"
        assert ajustes["CSRF_COOKIE_DOMAIN"] is None

    def test_cookie_and_origins_come_from_the_environment(self) -> None:
        """SEC-04 · iteracion-24 #1 — Cada entorno nombra su cookie y sus orígenes."""
        ajustes = ajustes_con(
            {
                "CSRF_COOKIE_NAME": "csrftoken_dev",
                "CSRF_COOKIE_DOMAIN": ".itzaka.test",
                "CSRF_TRUSTED_ORIGINS": "https://admin.itzaka.test",
                "CORS_ALLOWED_ORIGINS": "https://dev.itzaka.test",
            }
        )

        assert ajustes["CSRF_COOKIE_NAME"] == "csrftoken_dev"
        assert ajustes["CSRF_COOKIE_DOMAIN"] == ".itzaka.test"
        assert ajustes["CORS_ALLOWED_ORIGINS"] == ["https://dev.itzaka.test"]
        # La SPA escribe desde su origen: también es de confianza para CSRF.
        assert ajustes["CSRF_TRUSTED_ORIGINS"] == [
            "https://admin.itzaka.test",
            "https://dev.itzaka.test",
        ]
