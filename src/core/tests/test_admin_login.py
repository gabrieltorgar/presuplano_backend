"""Login del admin con límite de intentos (iteracion-26 #16 · BOT-03.4).

Los límites de DRF no llegan al admin de Django: su login aceptaba intentos sin
fin. Ahora, tras ``ADMIN_LOGIN_MAX_FAILURES`` fallos desde una dirección o para
un usuario, responde 429 con ``Retry-After`` durante 15 minutos.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from django.urls import resolve

import core.settings as core_settings
from core.admin_login import LOCK_SECONDS, admin_login

LOGIN = "/admin/login/"


def fail(client, username: str, **extra):
    return client.post(LOGIN, {"username": username, "password": "wrong"}, **extra)


@pytest.mark.django_db
def test_admin_login_locks_after_failures(client, admin_user, settings) -> None:
    """BOT-03.4 · iteracion-26 #16 — Ni la contraseña correcta entra mientras
    dura el candado."""
    for _attempt in range(settings.ADMIN_LOGIN_MAX_FAILURES):
        fail(client, admin_user.email)

    response = client.post(
        LOGIN, {"username": admin_user.email, "password": "password"}
    )

    assert response.status_code == 429
    assert response["Retry-After"] == str(LOCK_SECONDS)


@pytest.mark.django_db
def test_admin_login_lock_is_per_username_across_ips(
    client, admin_user, settings
) -> None:
    """BOT-03.4 · iteracion-26 #16 — Cambiar de dirección no reinicia la cuenta."""
    for n in range(settings.ADMIN_LOGIN_MAX_FAILURES):
        fail(client, admin_user.email, REMOTE_ADDR=f"10.0.0.{n}")

    response = client.post(
        LOGIN,
        {"username": admin_user.email, "password": "password"},
        REMOTE_ADDR="10.0.0.99",
    )

    assert response.status_code == 429


@pytest.mark.django_db
class TestElCandadoDelAdmin:
    """BOT-03.4 · iteracion-26 #16"""

    def test_the_login_route_is_the_limited_one(self) -> None:
        """Montada antes de ``admin.site.urls``: la de Django no se alcanza."""
        assert resolve(LOGIN).func is admin_login

    def test_one_address_is_locked_for_any_username(
        self, client, admin_user, settings
    ) -> None:
        for n in range(settings.ADMIN_LOGIN_MAX_FAILURES):
            fail(client, f"otro{n}@itzaka.test")

        response = client.post(
            LOGIN, {"username": admin_user.email, "password": "password"}
        )

        assert response.status_code == 429

    def test_under_the_limit_the_right_password_still_enters(
        self, client, admin_user, settings
    ) -> None:
        for _attempt in range(settings.ADMIN_LOGIN_MAX_FAILURES - 1):
            fail(client, admin_user.email)

        response = client.post(
            LOGIN, {"username": admin_user.email, "password": "password"}
        )

        assert response.status_code == 302
        assert response["Location"] == "/admin/"

    def test_a_successful_login_is_not_counted(
        self, client, admin_user, settings
    ) -> None:
        settings.ADMIN_LOGIN_MAX_FAILURES = 2
        body = {"username": admin_user.email, "password": "password"}
        for _attempt in range(3):
            assert client.post(LOGIN, body).status_code == 302
            client.logout()

    def test_the_page_itself_is_never_locked(self, client, settings) -> None:
        for _attempt in range(settings.ADMIN_LOGIN_MAX_FAILURES):
            fail(client, "alguien@itzaka.test")

        assert client.get(LOGIN).status_code == 200

    def test_the_username_case_does_not_reset_the_lock(
        self, client, admin_user, settings
    ) -> None:
        for n in range(settings.ADMIN_LOGIN_MAX_FAILURES):
            fail(client, admin_user.email.upper(), REMOTE_ADDR=f"10.0.1.{n}")

        response = client.post(
            LOGIN,
            {"username": admin_user.email, "password": "password"},
            REMOTE_ADDR="10.0.1.99",
        )

        assert response.status_code == 429


def test_the_failure_limit_comes_from_the_environment() -> None:
    """BOT-03.4 · iteracion-26 #16 — 5 por omisión; ``ADMIN_LOGIN_MAX_FAILURES``."""
    env = {k: v for k, v in os.environ.items() if k != "ADMIN_LOGIN_MAX_FAILURES"}
    env.update(DJANGO_SETTINGS_MODULE="core.settings")
    read = "from django.conf import settings as s; print(s.ADMIN_LOGIN_MAX_FAILURES)"

    def value(**extra) -> str:
        run = subprocess.run(  # noqa: S603 -- el mismo intérprete, sin shell
            [sys.executable, "-c", read],
            cwd=Path(core_settings.__file__).resolve().parents[1],
            env={**env, **extra},
            capture_output=True,
            text=True,
            check=True,
        )
        return run.stdout.strip()

    assert value() == "5"
    assert value(ADMIN_LOGIN_MAX_FAILURES="3") == "3"
