"""Los settings leen del entorno, con o sin ``src/core/.env`` (iteracion-26 #2).

Los secretos del backend viven en Infisical: ``infisical sm run --env=<entorno>
-- <comando>`` los inyecta como variables de entorno del proceso, y Vercel los
recibe por su sincronización. ``src/core/.env`` queda como respaldo local
opcional y nunca pisa lo que llega del entorno (``read_env`` sin
``overwrite``): un ``.env`` viejo no debe ganarle al valor de Infisical.

Cada caso carga ``core.settings`` en un intérprete limpio desde una copia de
``src/core`` en una carpeta temporal, para controlar el ``.env`` sin tocar el
del repositorio (que nunca se copia ni se lee).
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import core.settings as core_settings

CORE_DIR = Path(core_settings.__file__).resolve().parent
REPO_ROOT = CORE_DIR.parents[1]
PROBE = "APP_BASE_URL"


def _setting(tmp_path: Path, *, dotenv: str | None = None, **environment: str) -> str:
    """``core.settings.<PROBE>`` con ese ``.env`` (o sin él) y ese entorno."""
    src = tmp_path / "src"
    shutil.copytree(
        CORE_DIR,
        src / "core",
        ignore=shutil.ignore_patterns("__pycache__", ".env", ".env.*"),
    )
    shutil.copy(REPO_ROOT / "pyproject.toml", tmp_path / "pyproject.toml")
    if dotenv is not None:
        (src / "core" / ".env").write_text(dotenv, encoding="utf-8")
    entorno = {k: v for k, v in os.environ.items() if k != PROBE}
    entorno.pop("DJANGO_SETTINGS_MODULE", None)
    entorno.update(DEBUG="True", **environment)
    salida = subprocess.run(  # noqa: S603 -- el mismo intérprete, sin shell
        [sys.executable, "-c", f"import core.settings as s; print(s.{PROBE})"],
        cwd=src,
        env=entorno,
        capture_output=True,
        text=True,
        check=True,
    )
    return salida.stdout.strip()


def test_the_injected_environment_wins_over_a_stale_dotenv(tmp_path: Path) -> None:
    """Lo que inyecta Infisical (o Vercel) manda aunque ``.env`` diga otra cosa."""
    valor = _setting(
        tmp_path,
        dotenv=f"{PROBE}=https://del-archivo.example\n",
        **{PROBE: "https://de-infisical.example"},
    )

    assert valor == "https://de-infisical.example"


def test_settings_read_the_environment_without_a_dotenv(tmp_path: Path) -> None:
    """Sin ``src/core/.env`` los settings cargan y toman el valor del entorno."""
    valor = _setting(tmp_path, **{PROBE: "https://de-infisical.example"})

    assert valor == "https://de-infisical.example"


def test_the_dotenv_is_only_a_local_fallback(tmp_path: Path) -> None:
    """Sin la variable en el entorno, ``.env`` sigue sirviendo de respaldo local."""
    valor = _setting(tmp_path, dotenv=f"{PROBE}=https://del-archivo.example\n")

    assert valor == "https://del-archivo.example"
