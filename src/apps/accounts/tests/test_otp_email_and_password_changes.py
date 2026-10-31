"""Cambio de correo y de contraseña con código (iteracion-26 #14, CRD-04.5).

En Itzaka el código de un cambio de correo va al correo nuevo (es el que se
prueba) y la cuenta sigue entrando con el de siempre hasta confirmarlo; el de
antes recibe un aviso sin código. La contraseña nueva pasa por los validadores
de Django al recuperarla y al cambiarla, y las dos cosas dejan fuera a toda
sesión anterior; quien la cambió con su sesión sigue dentro con una nueva.
"""

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import OtpCode
from apps.accounts.tests.otp_helpers import code_of, wrong
from common.auth_cookies import ACCESS_COOKIE, REFRESH_COOKIE

EMAIL = "/api/auth/me/email/"
EMAIL_VERIFY = "/api/auth/me/email/verify/"
PASSWORD_CHANGE = "/api/auth/me/password/"
RESET = "/api/auth/password-reset/"
RESET_CONFIRM = "/api/auth/password-reset/confirm/"
LOGIN = "/api/auth/login/"
ME = "/api/auth/me/"
REFRESH = "/api/auth/refresh/"
PASSWORD = "testpass123"
NEW_PASSWORD = "Teja-Roja-81"
NEW_EMAIL = "nuevo@estudio.mx"


def logged_in(user) -> APIClient:
    client = APIClient()
    response = client.post(
        LOGIN, {"email": user.email, "password": PASSWORD}, format="json"
    )
    assert response.status_code == status.HTTP_200_OK
    return client


@pytest.mark.django_db
class TestCambioDeCorreo:
    """CRD-04.5 · iteracion-26 #14"""

    def test_the_code_goes_to_the_new_address_only(self, user, otp_sent) -> None:
        response = logged_in(user).post(EMAIL, {"email": NEW_EMAIL}, format="json")

        assert response.status_code == status.HTTP_200_OK
        otp_sent.assert_called_once()
        assert otp_sent.call_args.kwargs["to"] == NEW_EMAIL
        assert otp_sent.call_args.kwargs["purpose"] == OtpCode.Purpose.EMAIL_CHANGE

    @pytest.mark.parametrize("code", [None, "wrong"], ids=["sin-codigo", "equivocado"])
    def test_the_change_needs_the_new_address_code(self, user, otp_sent, code) -> None:
        client = logged_in(user)
        client.post(EMAIL, {"email": NEW_EMAIL}, format="json")
        body = {} if code is None else {"code": wrong(code_of(otp_sent))}

        response = client.post(EMAIL_VERIFY, body, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "code" in response.data
        user.refresh_from_db()
        assert user.email != NEW_EMAIL
        assert user.pending_email == NEW_EMAIL

    def test_the_previous_address_is_told_without_a_code(
        self, user, otp_sent, mocker, django_capture_on_commit_callbacks
    ) -> None:
        notice = mocker.patch("apps.accounts.emails.mail.send_email", return_value=True)
        previous = user.email
        client = logged_in(user)
        client.post(EMAIL, {"email": NEW_EMAIL}, format="json")
        code = code_of(otp_sent)

        with django_capture_on_commit_callbacks(execute=True):
            response = client.post(EMAIL_VERIFY, {"code": code}, format="json")

        assert response.status_code == status.HTTP_200_OK
        notice.assert_called_once()
        sent = notice.call_args.kwargs
        assert sent["to"] == previous
        assert code not in sent["html"] and code not in sent["subject"]


@pytest.mark.django_db
class TestContrasenaNueva:
    """CRD-04.5 · iteracion-26 #14"""

    @pytest.mark.parametrize("weak", ["password123", "12345678"])
    def test_changing_runs_the_password_validators(self, user, weak) -> None:
        client = logged_in(user)

        response = client.post(
            PASSWORD_CHANGE,
            {"current_password": PASSWORD, "new_password": weak},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "new_password" in response.data
        user.refresh_from_db()
        assert user.check_password(PASSWORD)

    def test_recovering_runs_the_password_validators(self, user, otp_sent) -> None:
        APIClient().post(RESET, {"email": user.email}, format="json")

        response = APIClient().post(
            RESET_CONFIRM,
            {"email": user.email, "code": code_of(otp_sent), "password": "password123"},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "password" in response.data
        user.refresh_from_db()
        assert user.check_password(PASSWORD)

    def test_changing_revokes_the_other_sessions_and_reissues_its_own(
        self, user
    ) -> None:
        elsewhere = logged_in(user)
        here = logged_in(user)

        changed = here.post(
            PASSWORD_CHANGE,
            {"current_password": PASSWORD, "new_password": NEW_PASSWORD},
            format="json",
        )

        assert changed.status_code == status.HTTP_200_OK
        assert changed.cookies[ACCESS_COOKIE].value
        assert changed.cookies[REFRESH_COOKIE].value
        assert elsewhere.get(ME).status_code == status.HTTP_401_UNAUTHORIZED
        assert elsewhere.post(REFRESH).status_code == status.HTTP_401_UNAUTHORIZED
        assert here.get(ME).status_code == status.HTTP_200_OK
        assert here.post(REFRESH).status_code == status.HTTP_200_OK

    def test_recovering_revokes_every_session(self, user, otp_sent) -> None:
        """Quien recupera no tiene sesión que reemitir: entra con la nueva."""
        elsewhere = logged_in(user)
        APIClient().post(RESET, {"email": user.email}, format="json")

        recovered = APIClient().post(
            RESET_CONFIRM,
            {"email": user.email, "code": code_of(otp_sent), "password": NEW_PASSWORD},
            format="json",
        )

        assert recovered.status_code == status.HTTP_200_OK
        assert elsewhere.get(ME).status_code == status.HTTP_401_UNAUTHORIZED
        assert elsewhere.post(REFRESH).status_code == status.HTTP_401_UNAUTHORIZED
        assert (
            APIClient()
            .post(LOGIN, {"email": user.email, "password": NEW_PASSWORD}, format="json")
            .status_code
            == status.HTTP_200_OK
        )
