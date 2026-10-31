"""Espera, tope por hora y respuestas sin enumeración del OTP (iteracion-26 #14).

Hasta 4.0.0 cada «Reenviar código» mandaba un correo (sólo el límite por
dirección lo frenaba) y la verificación y la recuperación respondían 404 «No
existe una cuenta con ese correo»: preguntando por mil correos se sabía cuáles
eran clientes. Ahora la cuota va antes de buscar la cuenta, por destino (el
correo normalizado) y propósito —una espera entre envíos
(``OTP_RESEND_COOLDOWN_SECONDS``) y un tope por hora
(``OTP_MAX_CODES_PER_HOUR``)— y responde 429 con ``Retry-After`` igual para un
correo que existe y uno que no. Verificar o recuperar con un correo desconocido
responde el mismo 400 que un código equivocado.
"""

import pytest
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework.throttling import ScopedRateThrottle

from apps.accounts import services
from apps.accounts.models import OtpCode
from apps.accounts.services import issue_otp
from apps.accounts.tests.otp_helpers import wrong
from apps.legal.tests.consent import accepted

RESEND = "/api/auth/resend-otp/"
RESET = "/api/auth/password-reset/"
RESET_CONFIRM = "/api/auth/password-reset/confirm/"
VERIFY = "/api/auth/verify-otp/"
REGISTER = "/api/auth/register/"
LOGIN = "/api/auth/login/"
EMAIL = "/api/auth/me/email/"
EMAIL_RESEND = "/api/auth/me/email/resend/"
UNKNOWN = "nadie@estudio.mx"
PASSWORD = "testpass123"
NEW_PASSWORD = "Teja-Roja-81"


@pytest.fixture(autouse=True)
def _no_scope_limits(monkeypatch, otp_sent):
    """La cuota se sostiene sola; los límites por dirección tienen sus pruebas."""
    for scope in list(ScopedRateThrottle.THROTTLE_RATES):
        monkeypatch.setitem(ScopedRateThrottle.THROTTLE_RATES, scope, "1000/min")


@pytest.mark.django_db
class TestEsperaYTopePorHora:
    """CRD-04.2 · iteracion-26 #14"""

    def test_resend_within_the_cooldown_is_429_with_retry_after(
        self, api_client, user_factory, otp_sent, settings
    ) -> None:
        pending = user_factory(is_email_verified=False)

        first = api_client.post(RESEND, {"email": pending.email}, format="json")
        again = api_client.post(RESEND, {"email": pending.email}, format="json")

        assert first.status_code == status.HTTP_200_OK
        assert again.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert 0 < int(again["Retry-After"]) <= settings.OTP_RESEND_COOLDOWN_SECONDS
        assert again.data["detail"].startswith("Ya te enviamos un código.")
        assert otp_sent.call_count == 1

    def test_the_cooldown_also_applies_to_an_unknown_email(
        self, api_client, otp_sent
    ) -> None:
        codes = [
            api_client.post(RESEND, {"email": UNKNOWN}, format="json").status_code
            for _ in range(2)
        ]

        assert codes == [status.HTTP_200_OK, status.HTTP_429_TOO_MANY_REQUESTS]
        assert otp_sent.call_count == 0

    def test_known_and_unknown_emails_wait_the_same(self, api_client, user) -> None:
        for email in (user.email, UNKNOWN):
            api_client.post(RESET, {"email": email}, format="json")

        known = api_client.post(RESET, {"email": user.email}, format="json")
        unknown = api_client.post(RESET, {"email": UNKNOWN}, format="json")

        assert known.status_code == unknown.status_code == 429
        assert known.json() == unknown.json()
        assert known["Retry-After"] == unknown["Retry-After"]

    def test_the_quota_comes_before_looking_up_the_account(
        self, api_client, user, mocker
    ) -> None:
        """Dentro de la espera ni se busca la cuenta: el tiempo de respuesta no
        depende de si existe."""
        api_client.post(RESET, {"email": user.email}, format="json")
        lookup = mocker.spy(services, "find_user")

        response = api_client.post(RESET, {"email": user.email}, format="json")

        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        lookup.assert_not_called()

    def test_after_the_cooldown_a_new_code_goes_out(
        self, api_client, user_factory, otp_sent, settings
    ) -> None:
        settings.OTP_RESEND_COOLDOWN_SECONDS = 0
        pending = user_factory(is_email_verified=False)

        for _ in range(2):
            response = api_client.post(RESEND, {"email": pending.email}, format="json")
            assert response.status_code == status.HTTP_200_OK

        assert otp_sent.call_count == 2

    def test_resending_does_not_reset_the_hourly_budget(
        self, api_client, user_factory, otp_sent, settings
    ) -> None:
        settings.OTP_RESEND_COOLDOWN_SECONDS = 0
        settings.OTP_MAX_CODES_PER_HOUR = 3
        pending = user_factory(is_email_verified=False)

        answers = [
            api_client.post(RESEND, {"email": pending.email}, format="json")
            for _ in range(4)
        ]

        assert [r.status_code for r in answers] == [200, 200, 200, 429]
        assert int(answers[-1]["Retry-After"]) > 0
        assert otp_sent.call_count == 3

    def test_the_quota_is_per_destination_and_purpose(
        self, api_client, user_factory, otp_sent
    ) -> None:
        """Mismo correo para otro propósito, u otro correo: cada uno su cuota."""
        pending = user_factory(is_email_verified=False)
        other = user_factory(is_email_verified=False)

        answers = [
            api_client.post(RESEND, {"email": pending.email}, format="json"),
            api_client.post(RESET, {"email": pending.email}, format="json"),
            api_client.post(RESEND, {"email": other.email.upper()}, format="json"),
        ]

        assert [r.status_code for r in answers] == [200, 200, 200]
        assert otp_sent.call_count == 3

    def test_the_cooldown_ignores_how_the_email_is_written(
        self, api_client, user_factory
    ) -> None:
        pending = user_factory(is_email_verified=False)
        api_client.post(RESEND, {"email": pending.email}, format="json")

        response = api_client.post(
            RESEND, {"email": f"  {pending.email.upper()} "}, format="json"
        )

        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS

    def test_the_registration_code_does_not_count(self, api_client, otp_sent) -> None:
        """El primer código sale con el registro y «Reenviar código» sirve de
        inmediato; el siguiente espera."""
        api_client.post(
            REGISTER,
            {"email": "ana@estudio.mx", "password": NEW_PASSWORD, **accepted()},
            format="json",
        )

        answers = [
            APIClient().post(RESEND, {"email": "ana@estudio.mx"}, format="json")
            for _ in range(2)
        ]

        assert [r.status_code for r in answers] == [200, 429]
        assert otp_sent.call_count == 2

    def test_an_unverified_login_within_the_cooldown_still_says_why(
        self, api_client, user_factory, otp_sent
    ) -> None:
        """El 403 de una cuenta sin verificar no se vuelve 429: el código de hace
        un momento sigue sirviendo y no sale otro."""
        pending = user_factory(is_email_verified=False, password=PASSWORD)
        body = {"email": pending.email, "password": PASSWORD}

        answers = [api_client.post(LOGIN, body, format="json") for _ in range(2)]

        assert [r.status_code for r in answers] == [403, 403]
        assert answers[1].data["code"] == "phone_not_verified"
        assert otp_sent.call_count == 1

    def test_the_new_email_code_waits_its_cooldown(
        self, authenticated_client, otp_sent
    ) -> None:
        asked = authenticated_client.post(
            EMAIL, {"email": "nuevo@estudio.mx"}, format="json"
        )
        again = authenticated_client.post(EMAIL_RESEND, format="json")

        assert asked.status_code == status.HTTP_200_OK
        assert again.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert int(again["Retry-After"]) > 0
        assert otp_sent.call_count == 1


@pytest.mark.django_db
class TestSinEnumeracion:
    """CRD-04.2 · iteracion-26 #14 — Ni pedir ni usar un código dice si el correo
    tiene cuenta."""

    @pytest.mark.parametrize("url", [RESEND, RESET], ids=["resend-otp", "reset"])
    def test_known_and_unknown_emails_get_the_same_answer(
        self, api_client, user_factory, otp_sent, url
    ) -> None:
        known = api_client.post(
            url, {"email": user_factory(is_email_verified=False).email}, format="json"
        )
        sent = otp_sent.call_count
        unknown = api_client.post(url, {"email": UNKNOWN}, format="json")

        assert (unknown.status_code, unknown.json()) == (200, known.json())
        assert sent == otp_sent.call_count == 1  # nada sale hacia el desconocido

    def test_verifying_an_unknown_email_is_the_400_of_a_wrong_code(
        self, api_client, user_factory
    ) -> None:
        pending = user_factory(is_email_verified=False)
        code = issue_otp(user=pending, purpose=OtpCode.Purpose.SIGNUP)

        bad = api_client.post(
            VERIFY, {"email": pending.email, "code": wrong(code)}, format="json"
        )
        unknown = api_client.post(
            VERIFY, {"email": UNKNOWN, "code": code}, format="json"
        )

        assert bad.status_code == status.HTTP_400_BAD_REQUEST
        assert (unknown.status_code, unknown.json()) == (400, bad.json())

    def test_verifying_an_already_verified_email_is_the_same_400(
        self, api_client, user, user_factory
    ) -> None:
        pending = user_factory(is_email_verified=False)
        code = issue_otp(user=pending, purpose=OtpCode.Purpose.SIGNUP)
        bad = api_client.post(
            VERIFY, {"email": pending.email, "code": wrong(code)}, format="json"
        )

        verified = api_client.post(
            VERIFY, {"email": user.email, "code": "123456"}, format="json"
        )

        assert (verified.status_code, verified.json()) == (400, bad.json())

    def test_recovering_an_unknown_email_is_the_400_of_a_wrong_code(
        self, api_client, user
    ) -> None:
        code = issue_otp(user=user, purpose=OtpCode.Purpose.PASSWORD_RESET)
        body = {"password": NEW_PASSWORD}

        bad = api_client.post(
            RESET_CONFIRM,
            {**body, "email": user.email, "code": wrong(code)},
            format="json",
        )
        unknown = api_client.post(
            RESET_CONFIRM, {**body, "email": UNKNOWN, "code": code}, format="json"
        )

        assert bad.status_code == status.HTTP_400_BAD_REQUEST
        assert (unknown.status_code, unknown.json()) == (400, bad.json())
        user.refresh_from_db()
        assert user.check_password(PASSWORD)

    def test_a_weak_password_answers_the_same_with_or_without_an_account(
        self, api_client, user
    ) -> None:
        """La contraseña se revisa antes que el código, con o sin cuenta: su 400
        tampoco dice si el correo existe."""
        body = {"password": "password123", "code": "123456"}

        known = api_client.post(
            RESET_CONFIRM, {**body, "email": user.email}, format="json"
        )
        unknown = api_client.post(
            RESET_CONFIRM, {**body, "email": UNKNOWN}, format="json"
        )

        assert known.status_code == status.HTTP_400_BAD_REQUEST
        assert "password" in known.data
        assert (unknown.status_code, unknown.json()) == (400, known.json())
