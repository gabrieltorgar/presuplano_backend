"""Códigos OTP con HMAC e intentos bajo bloqueo (iteracion-26 #13).

Hasta 4.0.0 el código se guardaba con ``make_password`` (lento y pensado para
contraseñas) y se buscaba entre todos los vivos; dos intentos al mismo tiempo
podían leer el mismo código y usarlo los dos. Ahora se guarda su HMAC con la
``SECRET_KEY`` (una copia de la base no revela ningún código vivo), se genera
con ``secrets.randbelow``, se compara en tiempo constante y se verifica bajo
``select_for_update`` con el contador en la fila (``F("attempts") + 1``).

Un código equivocado no se lanza: el servicio devuelve que no sirvió y la vista
responde el 400, para que el intento cuente también con ``ATOMIC_REQUESTS``
(#22), que revierte lo escrito por una petición que termina en excepción.
"""

import threading
from datetime import timedelta
from unittest import mock

import pytest
from django.contrib import admin
from django.contrib.auth.hashers import make_password
from django.db import connection, connections
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts import services
from apps.accounts.models import OtpCode
from apps.accounts.serializers import (
    EmailChangeConfirmSerializer,
    PasswordResetConfirmSerializer,
    VerifyOtpSerializer,
)
from apps.accounts.services import check_otp, issue_otp
from apps.accounts.tests.otp_helpers import code_of, wrong

SIGNUP = OtpCode.Purpose.SIGNUP
RESET = OtpCode.Purpose.PASSWORD_RESET
EMAIL_CHANGE = OtpCode.Purpose.EMAIL_CHANGE

VERIFY = "/api/auth/verify-otp/"
RESET_CONFIRM = "/api/auth/password-reset/confirm/"
EMAIL_VERIFY = "/api/auth/me/email/verify/"
LOGIN = "/api/auth/login/"
PASSWORD = "testpass123"
NEW_PASSWORD = "Teja-Roja-81"


@pytest.fixture(autouse=True)
def _own_codes(otp_sent):
    """Con el correo configurado, cada cuenta recibe su propio código."""
    return otp_sent


def test_otp_model_stores_no_plain_code() -> None:
    """CRD-04 · iteracion-26 #13 — El modelo no tiene dónde guardar el código en
    claro: sólo su huella y el contador de intentos."""
    names = {field.name for field in OtpCode._meta.get_fields()}

    assert "code" not in names
    assert {"code_hash", "attempts"} <= names


@pytest.mark.django_db
class TestElCodigoGuardado:
    """CRD-04 · iteracion-26 #13"""

    def test_no_column_holds_the_code(self, user) -> None:
        """Ninguna columna de la fila trae el código."""
        code = issue_otp(user=user, purpose=SIGNUP)

        stored = OtpCode.objects.filter(user=user).values().get()

        assert code not in {str(value) for value in stored.values()}

    def test_the_code_is_stored_as_a_keyed_hmac(self, user, settings) -> None:
        """Su huella es el HMAC con la SECRET_KEY, no un hash de contraseña: con
        otra llave la huella es otra (una copia de la base sola no sirve)."""
        code = issue_otp(user=user, purpose=SIGNUP)
        stored = OtpCode.objects.get(user=user).code_hash

        assert "$" not in stored  # make_password: «algoritmo$iteraciones$sal$hash»
        assert stored == services.otp_digest(user_pk=user.pk, purpose=SIGNUP, raw=code)
        settings.SECRET_KEY = "otra-llave-" + "x" * 40
        assert stored != services.otp_digest(user_pk=user.pk, purpose=SIGNUP, raw=code)

    def test_the_code_is_drawn_with_secrets(self, user, mocker) -> None:
        """Seis cifras de ``secrets.randbelow``, con ceros a la izquierda."""
        draw = mocker.patch("apps.accounts.services.secrets.randbelow", return_value=42)

        code = issue_otp(user=user, purpose=SIGNUP)

        draw.assert_called_once_with(10**6)
        assert code == "000042"

    def test_the_code_is_compared_in_constant_time(self, user, mocker) -> None:
        compare = mocker.spy(services, "constant_time_compare")
        code = issue_otp(user=user, purpose=SIGNUP)

        assert check_otp(user=user, purpose=SIGNUP, code=code) is True
        assert compare.called

    def test_a_code_from_before_the_change_no_longer_opens(self, user) -> None:
        """Los códigos vivos guardados con ``make_password`` (hasta 4.0.0) no
        coinciden con ningún HMAC: sin migración, mueren al primer intento o a
        los 10 minutos, y se pide otro."""
        OtpCode.objects.create(
            user=user,
            purpose=SIGNUP,
            code_hash=make_password("246810"),
            expires_at=timezone.now() + timedelta(minutes=10),
        )

        assert check_otp(user=user, purpose=SIGNUP, code="246810") is False

    def test_a_new_code_voids_the_previous_one_without_deleting_it(self, user) -> None:
        """CRD-04.1 — Emitir otro invalida al anterior con ``.update``; la fila
        queda (con sus intentos) para el admin."""
        first = issue_otp(user=user, purpose=SIGNUP)
        second = issue_otp(user=user, purpose=SIGNUP)

        assert OtpCode.objects.filter(user=user, purpose=SIGNUP).count() == 2
        assert check_otp(user=user, purpose=SIGNUP, code=first) is False
        assert check_otp(user=user, purpose=SIGNUP, code=second) is True


@pytest.mark.django_db
class TestIntentosEnLaFila:
    """CRD-04.1 · iteracion-26 #13"""

    def test_each_wrong_try_counts_on_the_row(self, user) -> None:
        code = issue_otp(user=user, purpose=SIGNUP)

        for _ in range(2):
            assert check_otp(user=user, purpose=SIGNUP, code=wrong(code)) is False

        assert OtpCode.objects.get(user=user).attempts == 2

    def test_two_wrong_tries_that_read_before_either_writes_count_two(
        self, user, settings
    ) -> None:
        """Dos verificaciones que leyeron la fila antes de que la otra escribiera
        (lo que pasa con dos peticiones a la vez) cuentan dos: el contador sube
        en la base (F), no desde lo que cada una leyó."""
        settings.OTP_MAX_ATTEMPTS = 2
        code = issue_otp(user=user, purpose=SIGNUP)
        pk = OtpCode.objects.get(user=user).pk
        stale = [OtpCode.objects.get(pk=pk), OtpCode.objects.get(pk=pk)]

        with mock.patch.object(services, "_live_code", side_effect=stale):
            for _ in range(2):
                check_otp(user=user, purpose=SIGNUP, code=wrong(code))

        assert OtpCode.objects.get(pk=pk).attempts == 2
        # Llegó al tope: ni el correcto sirve ya.
        assert check_otp(user=user, purpose=SIGNUP, code=code) is False

    def test_at_the_limit_the_right_code_is_refused(self, user, settings) -> None:
        settings.OTP_MAX_ATTEMPTS = 3
        code = issue_otp(user=user, purpose=RESET)

        for _ in range(3):
            check_otp(user=user, purpose=RESET, code=wrong(code))

        assert check_otp(user=user, purpose=RESET, code=code) is False

    def test_a_lowered_limit_applies_to_a_live_code(self, user, settings) -> None:
        """Un código que ya pasó el tope (bajado después) no se compara."""
        code = issue_otp(user=user, purpose=SIGNUP)
        OtpCode.objects.filter(user=user).update(attempts=3)
        settings.OTP_MAX_ATTEMPTS = 3

        assert check_otp(user=user, purpose=SIGNUP, code=code) is False

    def test_an_expired_code_is_refused(self, user) -> None:
        code = issue_otp(user=user, purpose=SIGNUP)
        OtpCode.objects.update(expires_at=timezone.now() - timedelta(seconds=1))

        assert check_otp(user=user, purpose=SIGNUP, code=code) is False

    def test_a_used_code_cannot_be_reused(self, user) -> None:
        code = issue_otp(user=user, purpose=SIGNUP)

        assert check_otp(user=user, purpose=SIGNUP, code=code) is True
        assert check_otp(user=user, purpose=SIGNUP, code=code) is False


@pytest.mark.parametrize(
    ("serializer", "extra"),
    [
        (VerifyOtpSerializer, {"email": "ana@estudio.mx"}),
        (
            PasswordResetConfirmSerializer,
            {"email": "ana@estudio.mx", "password": NEW_PASSWORD},
        ),
        (EmailChangeConfirmSerializer, {}),
    ],
    ids=["verify-otp", "password-reset-confirm", "me-email-verify"],
)
@pytest.mark.parametrize(
    "code",
    ["٠١٢٣٤٥", "12345", "1234567", "12 456", "12a456", "-12345"],
    ids=["unicode-digits", "short", "long", "space", "letter", "sign"],
)
def test_the_code_field_takes_exactly_six_ascii_digits(serializer, extra, code) -> None:
    """CRD-04.1 · iteracion-26 #13 — ``^[0-9]{6}\\Z``: ni dígitos Unicode
    (``int()`` los acepta), ni otro largo, ni espacios o signos."""
    data = serializer(data={**extra, "code": code})

    assert not data.is_valid()
    assert "code" in data.errors


@pytest.mark.django_db
def test_unicode_digits_are_refused_without_spending_a_try(
    api_client, user_factory
) -> None:
    """CRD-04.1 · iteracion-26 #13 — Un código mal formado es un 400 del campo y
    no cuenta como intento."""
    account = user_factory(is_email_verified=False)
    code = issue_otp(user=account, purpose=SIGNUP)
    arabic = code.translate(str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩"))

    response = api_client.post(
        VERIFY, {"email": account.email, "code": arabic}, format="json"
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "code" in response.data
    assert OtpCode.objects.get(user=account).attempts == 0


@pytest.mark.django_db(transaction=True)
class TestElIntentoSobreviveAAtomicRequests:
    """CRD-04.1 · iteracion-26 #13 — Con cada petición en su transacción, DRF
    revierte lo escrito por una respuesta que sale de una excepción: el código
    equivocado se responde con un ``Response(400)`` para que el intento cuente,
    y el código que manda el acceso de una cuenta sin verificar (403) queda en la
    base."""

    @pytest.fixture(autouse=True)
    def _one_try(self, settings, atomic_requests, otp_sent) -> None:
        settings.OTP_MAX_ATTEMPTS = 1

    def test_the_fixture_wraps_the_view_in_a_transaction(
        self, user_factory, mocker
    ) -> None:
        """Control: la vista corre dentro de una transacción (sin el fixture, la
        prueba en modo ``transaction=True`` no tiene ninguna abierta)."""
        account = user_factory(is_email_verified=False)
        seen = {}
        real = services.verify_account

        def spy(**kwargs):
            seen["atomic"] = connection.in_atomic_block
            return real(**kwargs)

        mocker.patch("apps.accounts.views.verify_account", side_effect=spy)
        APIClient().post(
            VERIFY, {"email": account.email, "code": "000000"}, format="json"
        )

        assert seen == {"atomic": True}
        assert connection.in_atomic_block is False

    def test_a_wrong_account_code_still_counts(self, user_factory) -> None:
        account = user_factory(is_email_verified=False)
        code = issue_otp(user=account, purpose=SIGNUP)
        client = APIClient()

        bad = client.post(
            VERIFY, {"email": account.email, "code": wrong(code)}, format="json"
        )
        right = client.post(
            VERIFY, {"email": account.email, "code": code}, format="json"
        )

        assert bad.status_code == status.HTTP_400_BAD_REQUEST
        assert "Código de verificación inválido" in str(bad.data)
        assert right.status_code == status.HTTP_400_BAD_REQUEST
        account.refresh_from_db()
        assert account.is_email_verified is False
        assert OtpCode.objects.get(user=account).attempts == 1

    def test_a_wrong_recovery_code_still_counts(self, user_factory) -> None:
        account = user_factory(password=PASSWORD)
        code = issue_otp(user=account, purpose=RESET)
        client = APIClient()
        body = {"email": account.email, "password": NEW_PASSWORD}

        bad = client.post(RESET_CONFIRM, {**body, "code": wrong(code)}, format="json")
        right = client.post(RESET_CONFIRM, {**body, "code": code}, format="json")

        assert bad.status_code == status.HTTP_400_BAD_REQUEST
        assert right.status_code == status.HTTP_400_BAD_REQUEST
        account.refresh_from_db()
        assert account.check_password(PASSWORD)
        assert OtpCode.objects.get(user=account).attempts == 1

    def test_a_wrong_new_email_code_still_counts(self, user_factory) -> None:
        account = user_factory(pending_email="nuevo@estudio.mx")
        code = issue_otp(user=account, purpose=EMAIL_CHANGE)
        client = APIClient()
        client.force_authenticate(user=account)

        bad = client.post(EMAIL_VERIFY, {"code": wrong(code)}, format="json")
        right = client.post(EMAIL_VERIFY, {"code": code}, format="json")

        assert bad.status_code == status.HTTP_400_BAD_REQUEST
        assert bad.data == {"code": ["Código de verificación inválido"]}
        assert right.status_code == status.HTTP_400_BAD_REQUEST
        account.refresh_from_db()
        assert account.email != "nuevo@estudio.mx"
        assert OtpCode.objects.get(user=account).attempts == 1

    def test_the_code_sent_by_an_unverified_login_is_kept(
        self, user_factory, otp_sent
    ) -> None:
        """El acceso de una cuenta sin verificar responde 403 y manda el código:
        ese código existe en la base (antes la excepción lo revertía y el correo
        llevaba uno que no servía)."""
        account = user_factory(is_email_verified=False, password=PASSWORD)

        response = APIClient().post(
            LOGIN, {"email": account.email, "password": PASSWORD}, format="json"
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert response.data["code"] == "phone_not_verified"
        assert response.data["identity"] == account.email
        assert check_otp(user=account, purpose=SIGNUP, code=code_of(otp_sent))


@pytest.mark.django_db
class TestAdminDelCodigo:
    """CRD-04.3 · iteracion-26 #13 — El admin muestra la auditoría del código
    (para qué, intentos, vencimiento), nunca su huella, y no crea ni edita."""

    @pytest.fixture
    def otp_admin(self):
        return admin.site._registry[OtpCode]

    def test_fields_are_explicit_and_leave_out_the_hash(self, otp_admin, rf) -> None:
        request = rf.get("/admin/")

        assert otp_admin.fields
        assert "code_hash" not in otp_admin.fields
        assert "code_hash" not in otp_admin.get_fields(request)
        assert "code_hash" not in otp_admin.readonly_fields
        assert "code_hash" not in otp_admin.list_display

    def test_codes_are_neither_added_nor_changed(self, otp_admin, rf) -> None:
        request = rf.get("/admin/")

        assert otp_admin.has_add_permission(request) is False
        assert otp_admin.has_change_permission(request) is False

    def test_the_page_of_a_code_never_shows_its_hash(self, admin_client, user) -> None:
        issue_otp(user=user, purpose=SIGNUP)
        otp = OtpCode.objects.get(user=user)

        page = admin_client.get(reverse("admin:accounts_otpcode_change", args=[otp.pk]))
        listing = admin_client.get(reverse("admin:accounts_otpcode_changelist"))
        add = admin_client.get(reverse("admin:accounts_otpcode_add"))

        assert page.status_code == listing.status_code == 200
        assert otp.code_hash not in page.content.decode()
        assert otp.code_hash not in listing.content.decode()
        assert add.status_code == 403


# Bloqueo de fila de verdad: SQLite ignora FOR UPDATE (bloquea la base entera),
# así que estas dos sólo se registran contra PostgreSQL, que es la base de CI y
# de producción. No se saltan: en SQLite no existen (test_gate.py bloquea un skip).
if connection.vendor == "postgresql":

    @pytest.mark.django_db(transaction=True)
    class TestDosVerificacionesAlMismoTiempoEnPostgreSQL:
        """CRD-04.1 · iteracion-26 #13 — ``select_for_update`` sobre el código
        vivo: dos verificaciones simultáneas se forman en la fila."""

        def _at_once(self, attempt, times: int = 2) -> list:
            barrier = threading.Barrier(times)
            results, errors = [], []

            def run() -> None:
                try:
                    barrier.wait(timeout=10)
                    results.append(attempt())
                except Exception as error:  # noqa: BLE001 -- se reporta abajo
                    errors.append(error)
                finally:
                    connections.close_all()

            threads = [threading.Thread(target=run) for _ in range(times)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=30)
            assert not errors, errors
            return results

        def test_two_wrong_codes_at_once_count_two(self, user_factory) -> None:
            account = user_factory()
            code = issue_otp(user=account, purpose=SIGNUP)

            self._at_once(
                lambda: check_otp(user=account, purpose=SIGNUP, code=wrong(code))
            )

            assert OtpCode.objects.get(user=account).attempts == 2

        def test_the_right_code_twice_at_once_opens_only_once(
            self, user_factory
        ) -> None:
            account = user_factory()
            code = issue_otp(user=account, purpose=SIGNUP)

            results = self._at_once(
                lambda: check_otp(user=account, purpose=SIGNUP, code=code)
            )

            assert sorted(results) == [False, True]
