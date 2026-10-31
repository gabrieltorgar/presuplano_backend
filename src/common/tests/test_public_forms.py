"""Los cinco formularios públicos ante un bot, sin Google y con datos de más.

MAN-04 · BOT-02 · BOT-04 · iteracion-26 #17. Registro, acceso, recuperación,
contacto y aceptar una invitación: cada uno declara qué hace si Google no
contesta (las puertas de la cuenta, 503; el contacto, se queda bajo su límite y
marcado para revisar), lleva el campo trampa (la respuesta de siempre, sin
efecto) y pone tope al cuerpo (``DATA_UPLOAD_MAX_MEMORY_SIZE``) y a cada campo
de texto libre. Un cuerpo que no es un objeto JSON es un 400, nunca un 500.
"""

import json

import pytest
from rest_framework import status

from apps.accounts.models import User
from apps.accounts.serializers import PASSWORD_MAX_LENGTH
from apps.accounts.services import get_my_organization
from apps.accounts.tests.factories import UserFactory
from apps.leads.models import Lead
from apps.legal.tests.consent import accepted
from apps.team.models import Invitation, Membership
from apps.team.tests.factories import InvitationFactory
from common import recaptcha
from common.recaptcha import TOKEN_MAX_LENGTH, CaptchaUnavailable, verify_recaptcha

#: Fuerte y del largo que se quiera: pasa los cuatro validadores de Django.
STRONG = "Teja-Roja-81"


def strong_password(length: int) -> str:
    return (STRONG * (length // len(STRONG) + 1))[:length]


@pytest.fixture
def invitacion(db):
    admin = UserFactory(email="admin@estudioreyes.mx")
    organizacion = get_my_organization(user=admin)
    organizacion.name = "Estudio Reyes"
    organizacion.save()
    return InvitationFactory(account=admin, email="ana@estudio.mx", token="enlace-ana")


@pytest.fixture
def captcha(settings, mocker):
    """reCAPTCHA encendido; lo que diga Google, en las manos de la prueba."""
    settings.RECAPTCHA_ENABLED = True
    settings.RECAPTCHA_SECRET_KEY = "secreta"
    settings.RECAPTCHA_MIN_SCORE = 0.5
    settings.RECAPTCHA_HOSTNAMES = ["itzaka.com"]
    return mocker.patch.object(recaptcha, "_siteverify")


FORMS = {
    "registro": "/api/auth/register/",
    "acceso": "/api/auth/login/",
    "recuperacion": "/api/auth/password-reset/",
    "contacto": "/api/contact/",
    "invitacion": "/api/invitations/enlace-ana/accept/",
}


RESET_CONFIRM = "/api/auth/password-reset/confirm/"


def nothing_happened() -> None:
    assert not User.objects.exclude(email="admin@estudioreyes.mx").exists()
    assert not Lead.objects.exists()
    assert not Membership.objects.exists()


@pytest.mark.django_db
class TestCuerpoQueNoEsUnObjeto:
    """MAN-04 · un arreglo, un texto, un número o null: 400 y nada pasa."""

    @pytest.mark.parametrize("url", FORMS.values(), ids=FORMS.keys())
    @pytest.mark.parametrize("cuerpo", ["[]", '"hola"', "5", "null"])
    def test_a_non_object_body_is_400(self, api_client, invitacion, url, cuerpo):
        response = api_client.post(url, cuerpo, content_type="application/json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "non_field_errors" in response.data
        nothing_happened()

    def test_a_trap_with_a_non_text_email_is_still_dropped(self, api_client) -> None:
        """Caso de borde - Antes era un 500 al limpiar el correo del señuelo."""
        response = api_client.post(
            FORMS["registro"],
            {"email": 5, "password": STRONG, "website": "spam", **accepted()},
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        nothing_happened()


@pytest.mark.django_db
class TestTopePorCampo:
    """MAN-04 · cada campo de texto libre tiene tope: las contraseñas, 128."""

    def test_a_password_at_the_limit_registers(self, api_client) -> None:
        response = api_client.post(
            FORMS["registro"],
            {
                "email": "nueva@estudio.mx",
                "password": strong_password(PASSWORD_MAX_LENGTH),
                **accepted(),
            },
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED

    @pytest.mark.parametrize(
        ("url", "cuerpo"),
        [
            (FORMS["registro"], {"email": "nueva@estudio.mx", **accepted()}),
            (FORMS["acceso"], {"email": "ana@estudio.mx"}),
            (RESET_CONFIRM, {"email": "a@b.mx", "code": "123456"}),
            (FORMS["invitacion"], accepted()),
        ],
        ids=["registro", "acceso", "recuperacion-confirmar", "invitacion"],
    )
    def test_a_password_over_the_limit_is_400(
        self, api_client, invitacion, url, cuerpo
    ) -> None:
        password = strong_password(PASSWORD_MAX_LENGTH + 1)

        response = api_client.post(url, {**cuerpo, "password": password}, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "password" in response.data
        nothing_happened()

    def test_a_password_at_the_limit_accepts_the_invitation(
        self, api_client, invitacion
    ) -> None:
        response = api_client.post(
            FORMS["invitacion"],
            {"password": strong_password(PASSWORD_MAX_LENGTH), **accepted()},
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED

    def test_an_email_over_254_does_not_register(self, api_client) -> None:
        email = f"{'a' * 245}@estudio.mx"  # 255

        response = api_client.post(
            FORMS["registro"], {"email": email, "password": STRONG, **accepted()}
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "email" in response.data
        nothing_happened()

    def test_an_oversized_token_never_reaches_google(self, captcha) -> None:
        resultado = verify_recaptcha(
            token="t" * (TOKEN_MAX_LENGTH + 1), action="signup_submit", remote_ip=None
        )

        assert (resultado.ok, resultado.reason) == (False, "invalid")
        captcha.assert_not_called()

    def test_a_token_that_is_not_text_never_reaches_google(self, captcha) -> None:
        resultado = verify_recaptcha(
            token={"t": 1}, action="signup_submit", remote_ip=None
        )

        assert (resultado.ok, resultado.reason) == (False, "invalid")
        captcha.assert_not_called()


@pytest.mark.django_db
class TestSinToken:
    """BOT-01 · sin token, ninguno de los cinco pasa (400 y sin efecto)."""

    @pytest.mark.parametrize(
        ("url", "cuerpo"),
        [
            (FORMS["registro"], {"email": "nueva@estudio.mx", "password": STRONG}),
            (FORMS["contacto"], {"name": "Ana", "email": "ana@correo.mx"}),
            (FORMS["invitacion"], {"password": STRONG}),
        ],
        ids=["registro", "contacto", "invitacion"],
    )
    def test_without_a_token_it_is_refused(
        self, api_client, captcha, invitacion, url, cuerpo
    ) -> None:
        response = api_client.post(url, {**cuerpo, **accepted()}, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "No pudimos verificar" in str(response.data)
        captcha.assert_not_called()
        nothing_happened()


@pytest.mark.django_db
class TestInvitacionSinGoogle:
    """BOT-02 · la invitación crea cuentas: sin Google, 503 como el registro."""

    def test_with_google_down_accepting_answers_503(
        self, api_client, captcha, invitacion
    ) -> None:
        captcha.side_effect = CaptchaUnavailable

        response = api_client.post(
            FORMS["invitacion"],
            {"password": STRONG, "recaptcha_token": "t", **accepted()},
            format="json",
        )

        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        invitacion.refresh_from_db()
        assert invitacion.status == Invitation.Status.PENDING
        nothing_happened()


@pytest.mark.django_db
class TestSenuelos:
    """BOT-04 · lo que responde el campo trampa no se distingue de la vía real."""

    def test_the_login_bot_gets_the_wrong_password_answer(self, api_client) -> None:
        """Decisión: el acceso con trampa es el 401 de unas credenciales malas.

        Un 200 sin sesión no sería «la respuesta de siempre» (la de siempre
        trae las cookies) y dejaría a la SPA creyendo que entró; el 401 es
        idéntico al de una contraseña equivocada, así que no enseña nada.
        """
        cuenta = User.objects.create_user(email="ana@estudio.mx", password=STRONG)
        cuenta.is_email_verified = True
        cuenta.save()

        bot = api_client.post(
            FORMS["acceso"],
            {"email": "ana@estudio.mx", "password": STRONG, "website": "x"},
            format="json",
        )
        equivocada = api_client.post(
            FORMS["acceso"],
            {"email": "ana@estudio.mx", "password": "Otra-Clave-99"},
            format="json",
        )

        assert bot.status_code == equivocada.status_code == 401
        assert bot.data == equivocada.data
        assert bot["WWW-Authenticate"] == equivocada["WWW-Authenticate"]
        assert "itzaka_access" not in bot.cookies

    def test_a_trap_on_a_link_that_does_not_exist_is_404(self, api_client, db):
        """Antes el señuelo respondía 201 a un enlace inexistente; la vía real, 404."""
        url = "/api/invitations/no-existe/accept/"

        real = api_client.post(url, {"password": STRONG, **accepted()}, format="json")
        bot = api_client.post(
            url, {"password": STRONG, "website": "x", **accepted()}, format="json"
        )

        assert real.status_code == bot.status_code == status.HTTP_404_NOT_FOUND
        assert bot.data == real.data
        nothing_happened()

    @pytest.mark.parametrize(
        ("cambios", "esperado"),
        [
            ({"status": Invitation.Status.ACCEPTED}, status.HTTP_409_CONFLICT),
            ({"status": Invitation.Status.CANCELLED}, status.HTTP_410_GONE),
        ],
        ids=["usada", "cancelada"],
    )
    def test_a_trap_on_a_link_that_no_longer_works_answers_like_it(
        self, api_client, invitacion, cambios, esperado
    ) -> None:
        Invitation.objects.filter(pk=invitacion.pk).update(**cambios)

        real = api_client.post(
            FORMS["invitacion"], {"password": STRONG, **accepted()}, format="json"
        )
        bot = api_client.post(
            FORMS["invitacion"],
            {"password": STRONG, "website": "x", **accepted()},
            format="json",
        )

        assert real.status_code == bot.status_code == esperado
        assert json.loads(bot.content) == json.loads(real.content)
        nothing_happened()
