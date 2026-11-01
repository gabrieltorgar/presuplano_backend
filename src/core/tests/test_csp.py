"""CSP aplicada en la API y en el admin (SRV-01 · iteracion-26 #18).

La API sirve JSON: su política no deja cargar nada ni enmarcarla
(``default-src 'none'``). El admin de Unfold es una página y tiene la suya, sólo
bajo ``/admin/``: Alpine evalúa expresiones (``'unsafe-eval'``) y pone estilos
en línea; scripts en línea, nunca. Con DEBUG, la API navegable (HTML) usa la
del admin. pytest-django corre con ``DEBUG=False``.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
from django.conf import settings as dj_settings

import core.settings as core_settings

SRC = Path(core_settings.__file__).resolve().parents[1]


def directives(header: str) -> dict[str, list[str]]:
    """``"a x; b y z"`` → ``{"a": ["x"], "b": ["y", "z"]}``."""
    parsed = {}
    for part in header.split(";"):
        name, *values = part.split()
        parsed[name] = values
    return parsed


@pytest.mark.django_db
class TestLaApi:
    """SRV-01 · nada que cargar, nadie que la enmarque."""

    @pytest.mark.parametrize("url", ["/api/health/", "/api/no-existe/"])
    def test_the_api_answers_with_default_src_none(self, client, url) -> None:
        csp = directives(client.get(url)["Content-Security-Policy"])

        assert csp == {
            "default-src": ["'none'"],
            "frame-ancestors": ["'none'"],
            "base-uri": ["'none'"],
            "form-action": ["'self'"],
        }

    def test_the_headers_go_with_every_response(self, client) -> None:
        response = client.get("/api/health/")

        assert response["X-Content-Type-Options"] == "nosniff"
        assert response["X-Frame-Options"] == "DENY"
        assert response["Referrer-Policy"] == "same-origin"


@pytest.mark.django_db
class TestElAdmin:
    """SRV-01 · el login de Unfold carga con su propia política."""

    def test_the_admin_login_loads_with_its_policy(self, client) -> None:
        response = client.get("/admin/login/")
        html = response.content.decode()
        csp = directives(response["Content-Security-Policy"])

        assert response.status_code == 200
        assert csp["script-src"] == ["'self'", "'unsafe-eval'"]
        assert csp["style-src"] == ["'self'", "'unsafe-inline'"]
        assert csp["frame-ancestors"] == ["'none'"]
        assert csp["form-action"] == ["'self'"]
        assert csp["object-src"] == ["'none'"]
        # Lo que la página pide sale del mismo origen ('self'): ningún script
        # en línea, que 'unsafe-eval' no deja correr.
        scripts = re.findall(r"<script\b[^>]*>", html)
        assert scripts
        assert all(re.search(r'\bsrc="/static/', tag) for tag in scripts)
        assert all(
            href.startswith("/static/")
            for href in re.findall(r'<link\b[^>]*href="([^"]+)"', html)
        )

    def test_nothing_unsafe_leaves_the_admin(self, client) -> None:
        api = client.get("/api/health/")["Content-Security-Policy"]

        assert "unsafe" not in api
        assert "https:" not in api

    def test_with_debug_the_browsable_api_gets_the_admin_policy(
        self, client, settings
    ) -> None:
        """Caso de borde - Con DEBUG la API navegable es HTML con estilos."""
        settings.DEBUG = True

        html = client.get("/api/health/", HTTP_ACCEPT="text/html")
        json_ = client.get("/api/health/", HTTP_ACCEPT="application/json")

        assert "'unsafe-inline'" in html["Content-Security-Policy"]
        assert "default-src 'none'" in json_["Content-Security-Policy"]


class TestElOrden:
    """SRV-01 · CSPMiddleware tras WhiteNoise y, enseguida, AdminCSPMiddleware."""

    def test_the_admin_policy_middleware_follows_django_csp(self) -> None:
        mw = list(dj_settings.MIDDLEWARE)
        csp = mw.index("csp.middleware.CSPMiddleware")

        assert csp > mw.index("whitenoise.middleware.WhiteNoiseMiddleware")
        assert mw[csp + 1] == "core.middleware.AdminCSPMiddleware"
        assert "common.csp.ScopedCSPMiddleware" not in mw
        assert "csp" in dj_settings.INSTALLED_APPS

    def test_the_policy_is_enforced_and_strict(self) -> None:
        policy = core_settings.CONTENT_SECURITY_POLICY["DIRECTIVES"]

        assert not hasattr(core_settings, "CONTENT_SECURITY_POLICY_REPORT_ONLY")
        assert not any("unsafe" in str(v) for v in policy.values())
        assert all(
            "unsafe-inline" not in v for v in core_settings.ADMIN_CSP["script-src"]
        )

    def test_the_headers_are_declared_with_debug_too(self) -> None:
        """La suite corre con DEBUG: antes sólo existían fuera de DEBUG."""
        assert core_settings.DEBUG is True
        assert core_settings.SECURE_CONTENT_TYPE_NOSNIFF is True
        assert core_settings.X_FRAME_OPTIONS == "DENY"
        assert core_settings.SECURE_REFERRER_POLICY == "same-origin"


def _admin_img_src(**entorno: str) -> list[str]:
    base = {
        k: v for k, v in os.environ.items() if not k.startswith("R2_") and k != "USE_R2"
    }
    salida = subprocess.run(  # noqa: S603 -- el mismo intérprete, sin shell
        [
            sys.executable,
            "-c",
            "from django.conf import settings as s; print(*s.ADMIN_CSP['img-src'])",
        ],
        cwd=SRC,
        env={**base, "DJANGO_SETTINGS_MODULE": "core.settings", **entorno},
        capture_output=True,
        text=True,
        check=True,
    )
    return salida.stdout.split()


R2 = {
    "R2_ACCESS_KEY_ID": "id",
    "R2_SECRET_ACCESS_KEY": "secreto",
    "R2_BUCKET_NAME": "cubeta",
    "R2_ENDPOINT_URL": "https://cuenta.r2.cloudflarestorage.com",
}


class TestImagenesDelBucket:
    """La vista previa de logotipos y fotos en el admin sale del bucket, y nada más."""

    def test_without_a_bucket_only_the_admin_itself(self) -> None:
        assert _admin_img_src() == ["'self'", "data:"]

    def test_the_public_host_of_the_bucket(self) -> None:
        img = _admin_img_src(**R2, R2_PUBLIC_URL="https://media.ejemplo.com")

        assert img == ["'self'", "data:", "https://media.ejemplo.com"]

    def test_signed_urls_come_from_the_bucket_endpoint(self) -> None:
        img = _admin_img_src(
            **R2, R2_PUBLIC_URL="https://media.ejemplo.com", R2_SIGNED_URLS="True"
        )

        assert img == [
            "'self'",
            "data:",
            "https://cubeta.cuenta.r2.cloudflarestorage.com",
        ]
