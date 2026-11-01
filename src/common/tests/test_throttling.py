"""Throttling por cuenta, tasas de auth y acciones costosas (iteracion-26 #16).

Hasta 4.0.0 el límite era sólo por dirección (rotar la IP lo reiniciaba), las
vistas de auth compartían el alcance ``otp`` (5 por minuto para pedir y para
verificar), las acciones que mandan correo o llaman un servicio de pago tenían
cada una el suyo o ninguno, y la caché de base de datos borraba contadores vivos
al pasar de 300 entradas. Ahora cada vista de auth tiene su alcance por
dirección y, donde se escribe un correo, uno por cuenta
(``common.throttling.IdentifierRateThrottle``); las costosas usan ``costly``.
"""

import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

import core.settings as core_settings
from apps.accounts import views as accounts
from apps.documents.views import SendDocumentView
from apps.planner.views import PlanViewSet
from apps.team.views import InvitationResendView, InvitationsView
from common.throttling import IdentifierRateThrottle
from tests.platform.routes import api_routes

EMAIL = "ana@estudio.mx"
NEW_PASSWORD = "Teja-Roja-81"

#: Las tasas de la skill (django-backend-conventions security.md §1).
SKILL_RATES = {
    "login": "10/min",
    "register": "5/hour",
    "otp_request": "3/min",
    "otp_verify": "10/min",
    "password_reset": "5/hour",
    "password_change": "5/hour",
    "contact": "5/hour",
    "costly": "20/hour",
    "bulk": "30/min",
    "upload": "30/hour",
    "dj_rest_auth": "10/min",
    "login_email": "20/hour",
    "otp_email": "10/hour",
    "password_reset_email": "3/hour",
}

#: Cada vista de auth: (alcance por dirección, alcance por cuenta).
AUTH_VIEWS = {
    accounts.LoginView: ("login", "login_email"),
    accounts.RegisterView: ("register", None),
    accounts.VerifyOtpView: ("otp_verify", "otp_email"),
    accounts.ResendOtpView: ("otp_request", None),
    accounts.PasswordResetRequestView: ("password_reset", "password_reset_email"),
    # Recuperar es verificar un código de seis dígitos: sus mismos límites.
    accounts.PasswordResetConfirmView: ("otp_verify", "otp_email"),
    accounts.MyEmailView: ("otp_request", None),
    accounts.MyEmailVerifyView: ("otp_verify", "otp_email"),
    accounts.MyEmailResendView: ("otp_request", None),
    accounts.MyPasswordView: ("password_change", None),
    # Borrar la cuenta pide la contraseña: no es un oráculo para probarla.
    accounts.MyAccountDeleteView: ("password_change", None),
}


def limit(monkeypatch, scope: str, rate: str = "2/min") -> None:
    """Las tasas que leen los throttles (los settings no llegan a su atributo)."""
    monkeypatch.setitem(ScopedRateThrottle.THROTTLE_RATES, scope, rate)


def third_call(send) -> object:
    for _ in range(2):
        send()
    return send()


class TestConfiguracion:
    """BOT-03 · iteracion-26 #16"""

    def test_the_per_account_throttle_is_on_by_default(self) -> None:
        assert core_settings.REST_FRAMEWORK["DEFAULT_THROTTLE_CLASSES"] == (
            "rest_framework.throttling.AnonRateThrottle",
            "rest_framework.throttling.UserRateThrottle",
            "rest_framework.throttling.ScopedRateThrottle",
            "common.throttling.IdentifierRateThrottle",
        )

    def test_the_rates_are_the_skill_ones(self) -> None:
        rates = core_settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]

        assert {scope: rates.get(scope) for scope in SKILL_RATES} == SKILL_RATES
        # El enlace público de una invitación conserva el suyo; los que nadie
        # usa ya no están (otp, documents, invitations, signup).
        assert rates["invitation"] == "30/min"
        assert not {"otp", "documents", "invitations", "signup"} & set(rates)

    def test_the_costly_rate_comes_from_the_environment(self) -> None:
        env = {k: v for k, v in os.environ.items() if k != "THROTTLE_COSTLY"}
        env.update(THROTTLE_COSTLY="40/hour", DJANGO_SETTINGS_MODULE="core.settings")
        read = (
            "from django.conf import settings as s;"
            "print(s.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']['costly'])"
        )

        run = subprocess.run(  # noqa: S603 -- el mismo intérprete, sin shell
            [sys.executable, "-c", read],
            cwd=Path(core_settings.__file__).resolve().parents[1],
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )

        assert run.stdout.strip() == "40/hour"

    def test_db_cache_does_not_cull_throttles(self) -> None:
        """BOT-03 — Con 300 entradas (lo de Django) la tabla borraba contadores
        de throttle vivos; la suite usa memoria, así que se lee del módulo."""
        default = core_settings.CACHES["default"]

        assert default["BACKEND"].endswith("DatabaseCache")
        assert default["OPTIONS"]["MAX_ENTRIES"] >= 10_000
        assert default["OPTIONS"]["CULL_FREQUENCY"] > 1

    @pytest.mark.parametrize(
        ("view", "scopes"),
        list(AUTH_VIEWS.items()),
        ids=lambda v: getattr(v, "__name__", ""),
    )
    def test_each_auth_view_has_its_scopes(self, view, scopes) -> None:
        """BOT-03.1 — Ninguna comparte el alcance genérico de antes."""
        declared = (
            getattr(view, "throttle_scope", None),
            getattr(view, "identifier_throttle_scope", None),
        )

        assert declared == scopes

    def test_every_scope_a_route_declares_has_a_rate(self) -> None:
        """BOT-03.1 — También los por cuenta: sin tasa, la vista responde 500."""
        rates = core_settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]
        missing = [
            f"{route.name}: {scope}"
            for route in api_routes()
            for scope in (
                route.scope,
                getattr(route.cls, "identifier_throttle_scope", None),
            )
            if scope and scope not in rates
        ]

        assert not missing

    @pytest.mark.parametrize(
        "scope",
        [
            SendDocumentView.throttle_scope,
            InvitationsView.throttle_scope,
            InvitationResendView.throttle_scope,
            PlanViewSet.photo_conversions.kwargs.get("throttle_scope"),
        ],
        ids=["documents-send", "invitations", "invitation-resend", "photo-conversions"],
    )
    def test_costly_actions_use_the_costly_scope(self, scope) -> None:
        """BOT-03.2 — Mandan correo o llaman un servicio de pago."""
        assert scope == "costly"


class _Probe(APIView):
    authentication_classes = []
    permission_classes = []


class TestPorCuenta:
    """BOT-03 · iteracion-26 #16 — ``IdentifierRateThrottle`` en sí."""

    def _key(self, body: dict, view: APIView | None = None) -> str | None:
        request = Request(
            APIRequestFactory().post("/x/", body, format="json"),
            parsers=[*APIView().get_parsers()],
        )
        throttle = IdentifierRateThrottle()
        throttle.scope = "login_email"
        return throttle.get_cache_key(request, view or _Probe())

    def test_a_view_without_the_scope_is_never_limited(self) -> None:
        request = Request(APIRequestFactory().post("/x/", {}, format="json"))

        assert IdentifierRateThrottle().allow_request(request, _Probe()) is True

    def test_the_key_is_the_normalized_email(self) -> None:
        assert self._key({"email": f" {EMAIL.upper()} "}) == self._key({"email": EMAIL})
        assert self._key({"email": EMAIL}) != self._key({"email": "otra@estudio.mx"})

    def test_the_old_identifier_field_shares_the_bucket(self) -> None:
        """Las pantallas de antes mandan el correo en «identifier»."""
        assert self._key({"identifier": EMAIL}) == self._key({"email": EMAIL})

    def test_the_email_never_appears_in_the_key(self) -> None:
        assert EMAIL not in self._key({"email": EMAIL})

    def test_without_an_email_there_is_nothing_to_count(self) -> None:
        assert self._key({}) is None


#: (url, cuerpo, alcance por dirección) de las puertas públicas de auth.
THROTTLED = [
    ("/api/auth/login/", {"email": EMAIL, "password": "x"}, "login"),
    ("/api/auth/register/", {"email": EMAIL, "password": "x"}, "register"),
    ("/api/auth/resend-otp/", {"email": EMAIL}, "otp_request"),
    ("/api/auth/verify-otp/", {"email": EMAIL, "code": "000000"}, "otp_verify"),
    ("/api/auth/password-reset/", {"email": EMAIL}, "password_reset"),
    (
        "/api/auth/password-reset/confirm/",
        {"email": EMAIL, "code": "000000", "password": NEW_PASSWORD},
        "otp_verify",
    ),
    ("/api/contact/", {"name": "Ana", "email": EMAIL, "message": "Hola"}, "contact"),
]

#: (url, cuerpo, alcance por cuenta): rotar la dirección no reinicia la cuenta.
IDENTIFIER = [
    ("/api/auth/login/", {"email": EMAIL, "password": "x"}, "login_email"),
    ("/api/auth/verify-otp/", {"email": EMAIL, "code": "000000"}, "otp_email"),
    ("/api/auth/password-reset/", {"email": EMAIL}, "password_reset_email"),
    (
        "/api/auth/password-reset/confirm/",
        {"email": EMAIL, "code": "000000", "password": NEW_PASSWORD},
        "otp_email",
    ),
]


@pytest.mark.django_db
class TestLas429:
    """BOT-03 · BOT-03.1 · iteracion-26 #16"""

    @pytest.fixture(autouse=True)
    def _no_cooldown(self, settings) -> None:
        # Responde el alcance, no la espera del código (que tiene sus pruebas).
        settings.OTP_RESEND_COOLDOWN_SECONDS = 0

    @pytest.mark.parametrize(
        ("url", "body", "scope"), THROTTLED, ids=[t[0] for t in THROTTLED]
    )
    def test_the_third_call_is_429_with_retry_after(
        self, api_client, monkeypatch, url, body, scope
    ) -> None:
        limit(monkeypatch, scope)

        response = third_call(lambda: api_client.post(url, body, format="json"))

        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert int(response["Retry-After"]) > 0
        assert response.json()["detail"]

    @pytest.mark.parametrize(
        ("url", "body", "scope"), IDENTIFIER, ids=[t[0] for t in IDENTIFIER]
    )
    def test_one_email_from_many_addresses_is_throttled(
        self, api_client, monkeypatch, url, body, scope
    ) -> None:
        """También para un correo sin cuenta."""
        limit(monkeypatch, scope)

        codes = [
            api_client.post(
                url, body, format="json", REMOTE_ADDR=f"203.0.113.{n}"
            ).status_code
            for n in range(3)
        ]

        assert codes[-1] == status.HTTP_429_TOO_MANY_REQUESTS

    def test_a_spoofed_forwarded_for_does_not_reset_the_bucket(
        self, api_client, monkeypatch
    ) -> None:
        """NUM_PROXIES: cuenta la dirección que agregó el proxy, no la inventada."""
        limit(monkeypatch, "login")
        body = {"email": EMAIL, "password": "x"}

        codes = [
            api_client.post(
                "/api/auth/login/",
                body,
                format="json",
                HTTP_X_FORWARDED_FOR=f"10.0.0.{n}, 203.0.113.7",
            ).status_code
            for n in range(3)
        ]

        assert codes[-1] == status.HTTP_429_TOO_MANY_REQUESTS

    def test_checking_the_new_email_code_counts_per_account(
        self, authenticated_client, monkeypatch
    ) -> None:
        limit(monkeypatch, "otp_email")

        codes = [
            authenticated_client.post(
                "/api/auth/me/email/verify/",
                {"code": "000000"},
                format="json",
                REMOTE_ADDR=f"203.0.113.{n}",
            ).status_code
            for n in range(3)
        ]

        assert codes[-1] == status.HTTP_429_TOO_MANY_REQUESTS

    @pytest.mark.parametrize(
        ("method", "url", "body", "scope"),
        [
            ("post", "/api/auth/me/password/", {}, "password_change"),
            ("post", "/api/auth/me/delete/", {"password": "x"}, "password_change"),
            ("post", "/api/auth/me/email/resend/", {}, "otp_request"),
        ],
        ids=["me-password", "me-delete", "me-email-resend"],
    )
    def test_the_session_auth_doors_have_their_limit(
        self, authenticated_client, monkeypatch, method, url, body, scope
    ) -> None:
        limit(monkeypatch, scope)

        response = third_call(
            lambda: getattr(authenticated_client, method)(url, body, format="json")
        )

        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert int(response["Retry-After"]) > 0

    def test_asking_for_a_new_email_is_limited_on_both_routes(
        self, authenticated_client, monkeypatch, settings, mocker
    ) -> None:
        """``POST me/email/`` y ``PATCH me/`` mandan el código: el mismo alcance.
        ``GET me/`` (lo pide la SPA al arrancar) no lo gasta."""
        settings.RESEND_API_KEY = "re_test"
        mocker.patch("apps.accounts.services.send_otp_email", return_value=True)
        limit(monkeypatch, "otp_request")

        answers = [
            authenticated_client.post(
                "/api/auth/me/email/", {"email": "uno@estudio.mx"}, format="json"
            ),
            authenticated_client.patch(
                "/api/auth/me/", {"email": "dos@estudio.mx"}, format="json"
            ),
            authenticated_client.patch(
                "/api/auth/me/", {"email": "tres@estudio.mx"}, format="json"
            ),
        ]

        assert [r.status_code for r in answers] == [200, 200, 429]
        assert authenticated_client.get("/api/auth/me/").status_code == 200


@pytest.mark.django_db
class TestAccionesCostosas:
    """BOT-03.2 · iteracion-26 #16 — Mandan correo o llaman un servicio de pago:
    el tercer intento en el minuto (con la tasa a 2/min) es un 429."""

    @pytest.fixture(autouse=True)
    def _costly(self, monkeypatch, settings, mocker) -> None:
        limit(monkeypatch, "costly")
        settings.RESEND_API_KEY = "re_test"
        mocker.patch("common.mail.send_email", return_value=True)
        mocker.patch("common.mail.send_batch", return_value=True)

    def test_sending_a_document(self, authenticated_client) -> None:
        response = third_call(
            lambda: authenticated_client.post(
                "/api/documents/send/",
                {
                    "kind": "quote",
                    "to": "cliente@correo.mx",
                    "file": SimpleUploadedFile("c.pdf", b"%PDF-1.4", "application/pdf"),
                },
                format="multipart",
            )
        )

        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert int(response["Retry-After"]) > 0

    def test_inviting_and_resending_share_the_bucket(
        self, authenticated_client
    ) -> None:
        invite = authenticated_client.post(
            "/api/collaborators/invitations/",
            {"emails": ["luis@obra.mx"]},
            format="json",
        )
        resend = authenticated_client.post(
            f"/api/collaborators/invitations/{uuid.uuid4()}/resend/", format="json"
        )
        third = authenticated_client.post(
            "/api/collaborators/invitations/",
            {"emails": ["bea@obra.mx"]},
            format="json",
        )

        assert invite.status_code == status.HTTP_201_CREATED
        assert resend.status_code == status.HTTP_404_NOT_FOUND
        assert third.status_code == status.HTTP_429_TOO_MANY_REQUESTS

    def test_converting_a_photo(self, authenticated_client) -> None:
        response = third_call(
            lambda: authenticated_client.post(
                "/api/plans/photo-conversions/", {}, format="multipart"
            )
        )

        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
