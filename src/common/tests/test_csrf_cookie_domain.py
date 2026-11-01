"""Producción no despliega si la SPA no puede leer la cookie CSRF (SEC-04.4 ·
iteracion-30 #1).

Hasta 7.0.0 el dominio por omisión fuera de DEBUG era ``.itzaka.com``, y la API
de producción vive en ``api-itzaka.grupotorresmucino.com``: el navegador tiraba la
cookie (no es su dominio) y cada escritura respondía «CSRF token missing». Los
chequeos ``common.E005``, ``common.E006`` y ``common.E007`` corren con
``migrate``, parte del build de Vercel: en Production, si el dominio de la cookie,
deducido o puesto, no cubre a la SPA o a la API, o si no hay dominio y la SPA
vive en otro host, el build se detiene con el valor que tiene y el que esperaba.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from django.core.checks import run_checks

import core.settings as core_settings
from common import checks

SRC = Path(core_settings.__file__).resolve().parents[1]

SPA = "https://itzaka.grupotorresmucino.com"
API = "api-itzaka.grupotorresmucino.com"
VERCEL_HOST = "itzaka-api-abc.vercel.app"


def ids(errores) -> list[str]:
    return [error.id for error in errores]


class TestProduccionNoSaleSinLaCookieCsrf:
    """SEC-04.4 · iteracion-30 #1"""

    @pytest.fixture
    def produccion(self, monkeypatch, settings):
        """Production con la SPA y la API en el mismo dominio."""
        monkeypatch.setenv("VERCEL_ENV", "production")
        settings.CORS_ALLOWED_ORIGINS = [SPA]
        settings.ALLOWED_HOSTS = [API, VERCEL_HOST]
        settings.CSRF_COOKIE_DOMAIN = ".grupotorresmucino.com"

    def test_with_the_shared_domain_production_deploys(self, produccion) -> None:
        assert checks.csrf_cookie_domain_in_production(None) == []

    def test_a_wider_domain_covering_both_also_deploys(
        self, produccion, settings
    ) -> None:
        """Puesto a mano, cualquier dominio que cubra a las dos sirve."""
        settings.CORS_ALLOWED_ORIGINS = ["https://app.b.example.mx"]
        settings.ALLOWED_HOSTS = ["api.b.example.mx"]
        settings.CSRF_COOKIE_DOMAIN = ".example.mx"

        assert checks.csrf_cookie_domain_in_production(None) == []

    def test_the_old_itzaka_default_covers_neither(self, produccion, settings) -> None:
        """Lo que pasaba en producción con .itzaka.com."""
        settings.CSRF_COOKIE_DOMAIN = ".itzaka.com"

        errores = checks.csrf_cookie_domain_in_production(None)

        assert ids(errores) == ["common.E005", "common.E006"]
        spa, api = errores
        assert ".itzaka.com" in spa.msg
        assert "itzaka.grupotorresmucino.com" in spa.msg
        assert ".grupotorresmucino.com" in spa.hint, "dice cuál esperaba"
        assert ".itzaka.com" in api.msg
        assert API in api.msg
        assert ".grupotorresmucino.com" in api.hint

    def test_a_domain_covering_only_the_api_does_not_deploy(
        self, produccion, settings
    ) -> None:
        """La cookie en el host de la API no la lee la SPA."""
        settings.CSRF_COOKIE_DOMAIN = f".{API}"

        errores = checks.csrf_cookie_domain_in_production(None)

        assert ids(errores) == ["common.E005"]
        assert "itzaka.grupotorresmucino.com" in errores[0].msg

    def test_a_domain_covering_only_the_spa_does_not_deploy(
        self, produccion, settings
    ) -> None:
        """El navegador rechaza una cookie de un dominio que no es el del host
        que la manda."""
        settings.CSRF_COOKIE_DOMAIN = ".itzaka.grupotorresmucino.com"

        errores = checks.csrf_cookie_domain_in_production(None)

        assert ids(errores) == ["common.E006"]
        assert API in errores[0].msg
        assert VERCEL_HOST not in errores[0].msg, "los hosts de Vercel no cuentan"

    def test_a_public_suffix_covers_nobody(self, produccion, settings) -> None:
        """Con Domain=.com el navegador tira la cookie."""
        settings.CSRF_COOKIE_DOMAIN = ".com"

        assert ids(checks.csrf_cookie_domain_in_production(None)) == [
            "common.E005",
            "common.E006",
        ]

    def test_origins_on_two_domains_do_not_deploy(self, produccion, settings) -> None:
        """Un origen de la SPA fuera del dominio no podría escribir."""
        settings.CORS_ALLOWED_ORIGINS = [SPA, "https://itzaka.com"]

        errores = checks.csrf_cookie_domain_in_production(None)

        assert ids(errores) == ["common.E005"]
        assert "itzaka.com" in errores[0].msg
        assert "itzaka.grupotorresmucino.com" not in errores[0].msg, "esa sí entra"
        assert "CORS_ALLOWED_ORIGINS" in errores[0].hint

    def test_without_a_domain_on_different_hosts_it_does_not_deploy(
        self, produccion, settings
    ) -> None:
        """La cookie quedaría sólo en el host de la API."""
        settings.CSRF_COOKIE_DOMAIN = None

        errores = checks.csrf_cookie_domain_in_production(None)

        assert ids(errores) == ["common.E007"]
        assert "itzaka.grupotorresmucino.com" in errores[0].msg
        assert ".grupotorresmucino.com" in errores[0].hint

    def test_without_a_common_domain_it_says_there_is_none(
        self, produccion, settings
    ) -> None:
        """La SPA en vercel.app y la API en su dominio: nada que deducir."""
        settings.CORS_ALLOWED_ORIGINS = ["https://cuotreka.vercel.app"]
        settings.CSRF_COOKIE_DOMAIN = None

        errores = checks.csrf_cookie_domain_in_production(None)

        assert ids(errores) == ["common.E007"]
        assert "cuotreka.vercel.app" in errores[0].msg
        assert "mismo dominio" in errores[0].hint

    def test_without_a_domain_on_the_same_host_it_deploys(
        self, produccion, settings
    ) -> None:
        """Si la SPA y la API comparten el host, la cookie de host basta."""
        settings.CORS_ALLOWED_ORIGINS = [f"https://{API}"]
        settings.CSRF_COOKIE_DOMAIN = None

        assert checks.csrf_cookie_domain_in_production(None) == []

    def test_without_spa_origins_there_is_nothing_to_cover(
        self, produccion, settings
    ) -> None:
        settings.CORS_ALLOWED_ORIGINS = []
        settings.ALLOWED_HOSTS = [VERCEL_HOST]
        settings.CSRF_COOKIE_DOMAIN = None

        assert checks.csrf_cookie_domain_in_production(None) == []

    @pytest.mark.parametrize("vercel_env", ["preview", "development", ""])
    def test_outside_production_it_does_not_get_in_the_way(
        self, monkeypatch, settings, vercel_env
    ) -> None:
        monkeypatch.setenv("VERCEL_ENV", vercel_env)
        settings.CORS_ALLOWED_ORIGINS = [SPA]
        settings.ALLOWED_HOSTS = [API]
        settings.CSRF_COOKIE_DOMAIN = ".itzaka.com"

        assert checks.csrf_cookie_domain_in_production(None) == []

    def test_without_vercel_env_it_does_not_get_in_the_way(
        self, monkeypatch, settings
    ) -> None:
        monkeypatch.delenv("VERCEL_ENV", raising=False)
        settings.CORS_ALLOWED_ORIGINS = [SPA]
        settings.ALLOWED_HOSTS = [API]
        settings.CSRF_COOKIE_DOMAIN = None

        assert checks.csrf_cookie_domain_in_production(None) == []

    def test_the_check_is_registered(self, produccion, settings) -> None:
        settings.CSRF_COOKIE_DOMAIN = None

        assert "common.E007" in set(ids(run_checks(tags=["security"])))


def check_en_produccion(entorno_extra: dict[str, str]) -> subprocess.CompletedProcess:
    """``manage.py check --tag security`` en un proceso nuevo, como el build."""
    base = {
        k: v
        for k, v in os.environ.items()
        if k
        not in {"DEBUG", "ALLOWED_HOSTS", "CORS_ALLOWED_ORIGINS", "CSRF_COOKIE_DOMAIN"}
        and not k.startswith(("VERCEL", "RECAPTCHA_"))
    }
    return subprocess.run(  # noqa: S603 -- el mismo intérprete, sin shell
        [sys.executable, "manage.py", "check", "--tag", "security"],
        cwd=SRC,
        env={
            **base,
            "VERCEL": "1",
            "VERCEL_ENV": "production",
            "VERCEL_URL": VERCEL_HOST,
            "SECRET_KEY": "x" * 50,
            "RECAPTCHA_SECRET_KEY": "secreta",
            **entorno_extra,
        },
        capture_output=True,
        text=True,
        check=False,
    )


class TestElBuildDeProduccion:
    """SEC-04.4 · iteracion-30 #1 — lo que corre el build (``migrate`` llama a los
    chequeos)."""

    def test_with_todays_variables_the_build_goes_on(self) -> None:
        """ALLOWED_HOSTS y CORS_ALLOWED_ORIGINS de hoy, sin CSRF_COOKIE_DOMAIN."""
        salida = check_en_produccion(
            {"ALLOWED_HOSTS": API, "CORS_ALLOWED_ORIGINS": SPA}
        )

        assert salida.returncode == 0, salida.stderr

    def test_with_the_old_default_forced_the_build_stops(self) -> None:
        salida = check_en_produccion(
            {
                "ALLOWED_HOSTS": API,
                "CORS_ALLOWED_ORIGINS": SPA,
                "CSRF_COOKIE_DOMAIN": ".itzaka.com",
            }
        )

        assert salida.returncode != 0
        assert "common.E005" in salida.stderr
        assert "common.E006" in salida.stderr

    def test_without_variables_the_defaults_still_deploy(self) -> None:
        """Los valores por omisión (itzaka.com y api.itzaka.com) dan .itzaka.com."""
        assert check_en_produccion({}).returncode == 0
