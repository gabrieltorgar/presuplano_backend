"""The deployment entrypoint: what Vercel imports, and with which path.

This suite exists because the API answered 404 to everything in production
while every other test was green. The cause was not code but routing: a
catch-all rewrite in ``vercel.json`` sent every request to ``/api/index``, and
once Vercel started handing the app the REWRITTEN path, Django had no URL for
it. Nothing under ``src/`` could see that, so it is checked here.
"""

import importlib
import io
import json
import sys
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]


def _vercel_entrypoint() -> str:
    """The WSGI instance Vercel is told to serve, as ``module:attribute``."""
    with (REPO_ROOT / "pyproject.toml").open("rb") as handle:
        return tomllib.load(handle)["tool"]["vercel"]["entrypoint"]


def _load(entrypoint: str):
    """Imports it the way Vercel does: by module name, from the repo root."""
    module_name, _, attribute = entrypoint.partition(":")
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    return getattr(importlib.import_module(module_name), attribute)


def _get(app, path: str) -> str:
    """The status line of a real WSGI call — the request Vercel would deliver."""
    captured: dict[str, str] = {}

    def start_response(status: str, headers, exc_info=None) -> None:
        captured["status"] = status

    environ = {
        "REQUEST_METHOD": "GET",
        "PATH_INFO": path,
        "SERVER_NAME": "testserver",
        "SERVER_PORT": "443",
        "SERVER_PROTOCOL": "HTTP/1.1",
        "wsgi.url_scheme": "https",
        "wsgi.input": io.BytesIO(b""),
        "CONTENT_LENGTH": "0",
        "QUERY_STRING": "",
    }
    list(app(environ, start_response))
    return captured["status"]


@pytest.mark.django_db
def test_entrypoint_serves_a_real_path() -> None:
    """Flujo principal - La instancia que sirve Vercel resuelve la API."""
    app = _load(_vercel_entrypoint())

    assert _get(app, "/api/health/").startswith("200")


def test_entrypoint_is_importable_from_the_repository_root() -> None:
    """Caso de borde - Vercel importa por nombre de módulo, no por ruta."""
    module_name = _vercel_entrypoint().partition(":")[0]

    assert (REPO_ROOT / f"{module_name.replace('.', '/')}.py").is_file()


def test_no_catch_all_rewrite_reaches_the_app() -> None:
    """Caso de borde - Un rewrite general le cambiaría la ruta a Django.

    Vercel entrega ahora la ruta ya reescrita, de modo que un `/(.*)` hacia una
    función deja a Django resolviendo siempre el mismo camino inexistente: eso
    es lo que hizo que toda la API respondiera 404.
    """
    config = json.loads((REPO_ROOT / "vercel.json").read_text())

    for rewrite in config.get("rewrites", []):
        assert rewrite["source"] not in ("/(.*)", "/(.*)$", "/:path*"), (
            "un rewrite general vuelve a romper el enrutado de la API"
        )


@pytest.mark.django_db
@pytest.mark.parametrize("path", ["/api/tariffs/", "/api/auth/login/", "/admin/login/"])
def test_the_paths_the_app_actually_receives_resolve(path: str) -> None:
    """Flujo principal - Las rutas que pide el cliente existen para Django."""
    app = _load(_vercel_entrypoint())

    assert not _get(app, path).startswith("404")
