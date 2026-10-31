"""OTP universal sólo en local y develop (iteracion-26 #15 · CRD-04.4).

Hasta 4.0.0 ``OTP_UNIVERSAL_CODE`` valía «123456» por omisión y abría cualquier
cuenta, para cualquier propósito, mientras el correo no estuviera configurado
(y ``OTP_UNIVERSAL_CODE_ENABLED``, encendido con ``DEBUG``). Ahora no tiene valor
por omisión, existe sólo con ``APP_ENV`` en ``local`` o ``develop`` (los
settings se niegan a cargar con él en cualquier otro entorno, y un despliegue
Production de Vercel es producción diga lo que diga ``APP_ENV``), sirve sólo
para las cuentas de ``OTP_UNIVERSAL_EMAILS`` y sólo para verificar la cuenta:
nunca para recuperar la contraseña ni para cambiar el correo. Lo usa la suite
E2E de develop.
"""

import json
import logging
import os
import subprocess
import sys
from pathlib import Path

import pytest
from rest_framework import status
from rest_framework.test import APIClient

import core.settings as core_settings
from apps.accounts.models import OtpCode, User
from apps.accounts.services import check_otp, issue_otp, send_verification_code
from apps.accounts.tests.otp_helpers import wrong
from common.auth_cookies import ACCESS_COOKIE

SRC = Path(core_settings.__file__).resolve().parents[1]
#: Lo que cada prueba de los settings controla; lo demás llega del entorno.
GATE_VARIABLES = ("APP_ENV", "VERCEL_ENV", "OTP_UNIVERSAL_CODE", "OTP_UNIVERSAL_EMAILS")

VERIFY = "/api/auth/verify-otp/"
RESET = "/api/auth/password-reset/"
RESET_CONFIRM = "/api/auth/password-reset/confirm/"
EMAIL = "/api/auth/me/email/"
EMAIL_VERIFY = "/api/auth/me/email/verify/"
E2E_EMAIL = "e2e@itzaka.test"
TEST_CODE = "000000"
PASSWORD = "testpass123"
NEW_PASSWORD = "Teja-Roja-81"


def _settings_with(**variables: str) -> subprocess.CompletedProcess:
    """Carga los settings en otro proceso, con esas variables y sin las demás de
    la compuerta."""
    env = {k: v for k, v in os.environ.items() if k not in GATE_VARIABLES}
    env.update(
        DJANGO_SETTINGS_MODULE="core.settings",
        SECRET_KEY="x" * 50,
        PYTHONPATH=str(SRC),
        **variables,
    )
    read = (
        "import django, json; django.setup(); from django.conf import settings as s; "
        "print(json.dumps({k: getattr(s, k, None) for k in "
        "('APP_ENV', 'OTP_UNIVERSAL_CODE', 'OTP_UNIVERSAL_EMAILS')}))"
    )
    return subprocess.run(  # noqa: S603 -- el mismo intérprete, sin shell
        [sys.executable, "-c", read],
        cwd=SRC,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _loaded(run: subprocess.CompletedProcess) -> dict:
    assert run.returncode == 0, run.stderr
    return json.loads(run.stdout)


def test_universal_otp_is_refused_in_production() -> None:
    """CRD-04.4 · iteracion-26 #15 — Con el código universal en producción los
    settings no cargan: el build (``migrate``) y cada proceso fallan."""
    run = _settings_with(APP_ENV="production", OTP_UNIVERSAL_CODE=TEST_CODE)

    assert run.returncode != 0
    assert "ImproperlyConfigured" in run.stderr


class TestLaCompuertaDelEntorno:
    """CRD-04.4 · iteracion-26 #15"""

    def test_without_app_env_it_is_production_and_has_no_code(self) -> None:
        assert _loaded(_settings_with()) == {
            "APP_ENV": "production",
            "OTP_UNIVERSAL_CODE": "",
            "OTP_UNIVERSAL_EMAILS": [],
        }

    def test_without_app_env_the_code_is_refused(self) -> None:
        """Una variable que falta no abre la puerta: falla cerrado."""
        run = _settings_with(OTP_UNIVERSAL_CODE=TEST_CODE)

        assert run.returncode != 0
        assert "ImproperlyConfigured" in run.stderr

    @pytest.mark.parametrize("app_env", ["staging", "qa", "prod"])
    def test_any_other_environment_refuses_the_code(self, app_env) -> None:
        run = _settings_with(APP_ENV=app_env, OTP_UNIVERSAL_CODE=TEST_CODE)

        assert run.returncode != 0
        assert "ImproperlyConfigured" in run.stderr

    def test_a_vercel_production_deployment_is_production(self) -> None:
        """``VERCEL_ENV=production`` gana a un ``APP_ENV=develop`` copiado de más."""
        assert (
            _loaded(_settings_with(APP_ENV="develop", VERCEL_ENV="production"))[
                "APP_ENV"
            ]
            == "production"
        )
        run = _settings_with(
            APP_ENV="develop", VERCEL_ENV="production", OTP_UNIVERSAL_CODE=TEST_CODE
        )
        assert run.returncode != 0
        assert "ImproperlyConfigured" in run.stderr

    @pytest.mark.parametrize("app_env", ["develop", "local", " Develop "])
    def test_local_and_develop_load_it_with_their_accounts(self, app_env) -> None:
        loaded = _loaded(
            _settings_with(
                APP_ENV=app_env,
                VERCEL_ENV="preview",
                OTP_UNIVERSAL_CODE=TEST_CODE,
                OTP_UNIVERSAL_EMAILS=f" {E2E_EMAIL.upper()} ,otra@itzaka.test,",
            )
        )

        assert loaded == {
            "APP_ENV": app_env.strip().lower(),
            "OTP_UNIVERSAL_CODE": TEST_CODE,
            "OTP_UNIVERSAL_EMAILS": [E2E_EMAIL, "otra@itzaka.test"],
        }


@pytest.mark.django_db
class TestElCodigoDePruebas:
    """CRD-04.4 · iteracion-26 #15 — En develop, para las cuentas de la lista y
    sólo para verificar la cuenta."""

    @pytest.fixture(autouse=True)
    def _develop(self, settings, otp_sent):
        settings.APP_ENV = "develop"
        settings.OTP_UNIVERSAL_CODE = TEST_CODE
        settings.OTP_UNIVERSAL_EMAILS = [E2E_EMAIL]

    @pytest.fixture
    def e2e(self, user_factory):
        return user_factory(email=E2E_EMAIL, is_email_verified=False)

    def verify(self, email: str = E2E_EMAIL, code: str = TEST_CODE):
        return APIClient().post(VERIFY, {"email": email, "code": code}, format="json")

    def test_it_verifies_the_e2e_account_on_develop(self, e2e) -> None:
        """Control: la suite E2E de develop entra con él (y la sesión se abre)."""
        response = self.verify()

        assert response.status_code == status.HTTP_200_OK
        assert response.cookies[ACCESS_COOKIE].value
        e2e.refresh_from_db()
        assert e2e.is_email_verified is True

    def test_it_also_works_locally_with_the_mail_configured(
        self, e2e, settings
    ) -> None:
        """Con o sin correo: develop sí manda correos (Resend)."""
        settings.APP_ENV = "local"

        assert self.verify().status_code == status.HTTP_200_OK

    def test_the_real_code_still_works_for_the_e2e_account(self, e2e, otp_sent) -> None:
        send_verification_code(user=e2e)

        response = self.verify(code=otp_sent.call_args.kwargs["code"])

        assert response.status_code == status.HTTP_200_OK

    def test_it_is_ignored_in_production(self, e2e, settings) -> None:
        settings.APP_ENV = "production"

        assert self.verify().status_code == status.HTTP_400_BAD_REQUEST
        e2e.refresh_from_db()
        assert e2e.is_email_verified is False

    def test_it_is_only_for_the_listed_accounts(self, user_factory) -> None:
        other = user_factory(is_email_verified=False)

        assert self.verify(email=other.email).status_code == 400
        other.refresh_from_db()
        assert other.is_email_verified is False

    def test_the_list_ignores_how_the_email_is_written(self, e2e) -> None:
        assert self.verify(email=f" {E2E_EMAIL.upper()} ").status_code == 200

    def test_without_a_code_configured_nothing_is_universal(
        self, e2e, settings
    ) -> None:
        settings.OTP_UNIVERSAL_CODE = ""

        assert self.verify().status_code == status.HTTP_400_BAD_REQUEST

    def test_another_code_is_a_wrong_try(self, e2e) -> None:
        code = issue_otp(user=e2e, purpose=OtpCode.Purpose.SIGNUP)
        bad = wrong(code) if wrong(code) != TEST_CODE else wrong(wrong(code))

        assert self.verify(code=bad).status_code == 400
        assert OtpCode.objects.get(user=e2e).attempts == 1

    def test_never_for_password_recovery(self, user_factory) -> None:
        account = user_factory(email=E2E_EMAIL, password=PASSWORD)
        APIClient().post(RESET, {"email": E2E_EMAIL}, format="json")

        response = APIClient().post(
            RESET_CONFIRM,
            {"email": E2E_EMAIL, "code": TEST_CODE, "password": NEW_PASSWORD},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        account.refresh_from_db()
        assert account.check_password(PASSWORD)

    def test_never_for_an_email_change(self, user_factory) -> None:
        account = user_factory(email=E2E_EMAIL)
        client = APIClient()
        client.force_authenticate(user=account)
        client.post(EMAIL, {"email": "nuevo@itzaka.test"}, format="json")

        response = client.post(EMAIL_VERIFY, {"code": TEST_CODE}, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert User.objects.get(pk=account.pk).email == E2E_EMAIL

    def test_each_use_is_logged_without_the_code(self, e2e, caplog) -> None:
        with caplog.at_level(logging.WARNING, logger="apps"):
            self.verify()

        used = [r for r in caplog.records if "Universal OTP used" in r.getMessage()]
        assert len(used) == 1
        assert used[0].user_id == str(e2e.pk)
        assert TEST_CODE not in used[0].getMessage()


@pytest.mark.django_db
def test_universal_otp_is_ignored_outside_local_and_develop(
    settings, user_factory
) -> None:
    """CRD-04.4 · iteracion-26 #15 — Aunque llegara al proceso, en producción el
    código universal no abre nada."""
    account = user_factory(is_email_verified=False)
    settings.APP_ENV = "production"
    settings.OTP_UNIVERSAL_CODE = TEST_CODE
    settings.OTP_UNIVERSAL_EMAILS = [account.email]

    assert (
        check_otp(user=account, purpose=OtpCode.Purpose.SIGNUP, code=TEST_CODE) is False
    )


@pytest.mark.django_db
def test_without_mail_a_real_code_is_still_issued(settings, user, mocker) -> None:
    """CRD-04.4 · iteracion-26 #15 — Sin correo configurado ya no hay código
    universal de reemplazo: se emite el propio (y el envío lo anota si falla)."""
    settings.RESEND_API_KEY = ""
    sent = mocker.patch("apps.accounts.services.send_otp_email", return_value=False)

    send_verification_code(user=user)

    assert sent.called
    assert OtpCode.objects.filter(user=user).exists()
