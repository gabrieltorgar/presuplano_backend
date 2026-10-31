"""La conexión a la base, lista para el pooler de Neon (iteracion-25 #7 · DJ-01).

El pooler de Neon corre PgBouncer en modo transacción: los cursores del lado del
servidor (``.iterator()``) se rompen entre transacciones, y tras el reposo de
Neon una conexión guardada puede estar muerta. Conexiones cortas, revisadas
antes de reusarse y sin cursores del servidor.
"""

import os
import subprocess
import sys
from pathlib import Path

from django.conf import settings as dj_settings

import core.settings as core_settings


def test_database_settings_fit_transaction_pooler() -> None:
    db = dj_settings.DATABASES["default"]

    assert db.get("DISABLE_SERVER_SIDE_CURSORS") is True
    assert db.get("CONN_HEALTH_CHECKS") is True
    if "-pooler" in (db.get("HOST") or ""):
        assert db.get("CONN_MAX_AGE") == 0


def _conn_max_age(**extra_env: str) -> str:
    """``CONN_MAX_AGE`` de los settings en un intérprete limpio."""
    entorno = {k: v for k, v in os.environ.items() if k != "CONN_MAX_AGE"}
    entorno.update(DJANGO_SETTINGS_MODULE="core.settings", **extra_env)
    leer = (
        "from django.conf import settings as s;"
        "print(s.DATABASES['default']['CONN_MAX_AGE'])"
    )
    salida = subprocess.run(  # noqa: S603 -- el mismo intérprete, sin shell
        [sys.executable, "-c", leer],
        cwd=Path(core_settings.__file__).resolve().parents[1],
        env=entorno,
        capture_output=True,
        text=True,
        check=True,
    )
    return salida.stdout.strip()


def test_connections_last_one_request_unless_the_environment_says_otherwise() -> None:
    """Sin ``CONN_MAX_AGE``, 0: una conexión por petición, como pide el pooler."""
    assert _conn_max_age() == "0"
    assert _conn_max_age(CONN_MAX_AGE="60") == "60"


def test_env_example_names_only_the_app_database_url() -> None:
    """Una sola conexión por entorno: la API y el build de Vercel usan DATABASE_URL.

    iteracion-26 #1: se retiran DATABASE_URL_UNPOOLED y DATABASE_URL_MIGRATIONS
    (el buildCommand que las usaba pasaba de los 256 caracteres de Vercel).
    """
    env_example = Path(core_settings.__file__).with_name(".env.example")
    names = {
        line.split("=", 1)[0].lstrip("# ").strip()
        for line in env_example.read_text(encoding="utf-8").splitlines()
        if "=" in line
    }

    assert "DATABASE_URL" in names
    assert not names & {"DATABASE_URL_UNPOOLED", "DATABASE_URL_MIGRATIONS"}
