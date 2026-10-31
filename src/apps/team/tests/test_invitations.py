"""Invitar colaboradores por correo (iteracion-14 #1, US-135).

El administrador —quien creó la cuenta— escribe uno o varios correos; a cada
uno le llega un enlace que vence en 7 días. El enlace es un secreto: en la base
sólo queda su huella, y quien lo tiene es quien recibió el correo.
"""

import os
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

import pytest
from django.utils import timezone
from rest_framework import status

import core.settings as core_settings
from apps.accounts.services import get_my_organization
from apps.team.models import Invitation
from apps.team.services import hash_token
from apps.team.tests.factories import InvitationFactory, MembershipFactory

URL = "/api/collaborators/invitations/"


@pytest.fixture
def correo(settings, mocker):
    """El correo configurado, con la tanda interceptada (una sola petición)."""
    settings.RESEND_API_KEY = "re_test"
    settings.APP_BASE_URL = "https://cuotreka.vercel.app"
    return mocker.patch("apps.team.emails.mail.send_batch", return_value=True)


def mensajes(correo):
    """Los correos de todas las tandas enviadas, en orden."""
    return [mensaje for llamada in correo.call_args_list for mensaje in llamada.args[0]]


def enlaces(correo):
    """El token de cada correo enviado, sacado del enlace del botón."""
    tokens = []
    for mensaje in mensajes(correo):
        inicio = mensaje.html.index("/invitacion/") + len("/invitacion/")
        tokens.append(mensaje.html[inicio : mensaje.html.index('"', inicio)])
    return tokens


@pytest.mark.django_db
class TestInvitarAVarios:
    """Flujo principal - Invitar a varios."""

    def test_each_email_gets_its_own_link(self, authenticated_client, user, correo):
        response = authenticated_client.post(
            URL,
            {"emails": ["Ana@Estudio.mx", "luis@obra.mx"]},
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert [i["email"] for i in response.data["invited"]] == [
            "ana@estudio.mx",
            "luis@obra.mx",
        ]
        assert response.data["skipped"] == []
        assert correo.call_count == 1
        assert {m.to for m in mensajes(correo)} == {
            "ana@estudio.mx",
            "luis@obra.mx",
        }
        invitaciones = Invitation.objects.filter(account=user)
        assert invitaciones.count() == 2
        assert set(invitaciones.values_list("status", flat=True)) == {"pending"}

    def test_the_link_is_valid_for_seven_days(
        self, authenticated_client, user, correo
    ) -> None:
        authenticated_client.post(URL, {"emails": ["ana@estudio.mx"]}, format="json")

        invitacion = Invitation.objects.get()
        vigencia = invitacion.expires_at - timezone.now()
        assert timedelta(days=6, hours=23) < vigencia <= timedelta(days=7)
        assert "vence en 7 días" in mensajes(correo)[0].html

    def test_only_a_fingerprint_of_the_link_is_kept(
        self, authenticated_client, correo
    ) -> None:
        authenticated_client.post(URL, {"emails": ["ana@estudio.mx"]}, format="json")

        [token] = enlaces(correo)
        invitacion = Invitation.objects.get()
        assert len(token) >= 40
        assert invitacion.token_hash == hash_token(token)
        assert token not in invitacion.token_hash

    def test_the_email_speaks_for_the_company(
        self, authenticated_client, user, correo
    ) -> None:
        organizacion = get_my_organization(user=user)
        organizacion.name = "Estudio Reyes"
        organizacion.save()

        authenticated_client.post(URL, {"emails": ["ana@estudio.mx"]}, format="json")

        [mensaje] = mensajes(correo)
        assert "Estudio Reyes" in mensaje.subject
        assert "Estudio Reyes" in mensaje.html
        assert "https://cuotreka.vercel.app/invitacion/" in mensaje.html

    def test_the_same_email_twice_in_one_go_is_one_invitation(
        self, authenticated_client, correo
    ) -> None:
        response = authenticated_client.post(
            URL, {"emails": ["ana@estudio.mx", " ANA@estudio.mx "]}, format="json"
        )

        assert len(response.data["invited"]) == 1
        assert len(mensajes(correo)) == 1


@pytest.mark.django_db
class TestCorreoQueYaEsta:
    """Caso alternativo - Correo que ya está: no se manda una segunda."""

    def test_a_collaborator_is_not_invited_again(
        self, authenticated_client, user, correo
    ) -> None:
        miembro = MembershipFactory(account=user)

        response = authenticated_client.post(
            URL, {"emails": [miembro.user.email, "nuevo@obra.mx"]}, format="json"
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["skipped"] == [
            {"email": miembro.user.email, "reason": "Ya es colaborador."}
        ]
        assert [i["email"] for i in response.data["invited"]] == ["nuevo@obra.mx"]
        assert [m.to for m in mensajes(correo)] == ["nuevo@obra.mx"]

    def test_a_pending_invitation_is_not_sent_twice(
        self, authenticated_client, user, correo
    ) -> None:
        InvitationFactory(account=user, email="ana@estudio.mx")

        response = authenticated_client.post(
            URL, {"emails": ["ana@estudio.mx"]}, format="json"
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["invited"] == []
        assert response.data["skipped"] == [
            {
                "email": "ana@estudio.mx",
                "reason": "Ya tiene una invitación pendiente; puedes reenviarla.",
            }
        ]
        correo.assert_not_called()

    def test_an_expired_invitation_is_sent_again(
        self, authenticated_client, user, correo
    ) -> None:
        """Caso de borde - Vencida: se reenvía con un enlace nuevo, no se duplica."""
        vieja = InvitationFactory(
            account=user,
            email="ana@estudio.mx",
            expires_at=timezone.now() - timedelta(days=1),
        )

        response = authenticated_client.post(
            URL, {"emails": ["ana@estudio.mx"]}, format="json"
        )

        assert response.status_code == status.HTTP_201_CREATED
        vieja.refresh_from_db()
        assert Invitation.objects.count() == 1
        assert vieja.expires_at > timezone.now()
        assert vieja.token_hash == hash_token(enlaces(correo)[0])

    def test_another_company_inviting_the_same_person_is_fine(
        self, authenticated_client, correo
    ) -> None:
        """Una persona puede colaborar en varias empresas."""
        InvitationFactory(email="ana@estudio.mx")

        response = authenticated_client.post(
            URL, {"emails": ["ana@estudio.mx"]}, format="json"
        )

        assert response.status_code == status.HTTP_201_CREATED


@pytest.mark.django_db
class TestCasosDeBorde:
    def test_your_own_email_is_not_invited(
        self, authenticated_client, user, correo
    ) -> None:
        response = authenticated_client.post(
            URL, {"emails": [user.email.upper()]}, format="json"
        )

        assert response.data["skipped"] == [
            {
                "email": user.email,
                "reason": "Es tu propio correo: ya eres el administrador.",
            }
        ]
        assert not Invitation.objects.exists()
        correo.assert_not_called()

    def test_a_malformed_email_stops_them_all(
        self, authenticated_client, correo
    ) -> None:
        response = authenticated_client.post(
            URL, {"emails": ["ana@estudio.mx", "luis@"]}, format="json"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.json()["emails"] == {
            "1": ["Revisa este correo: no parece válido."]
        }
        assert not Invitation.objects.exists()
        correo.assert_not_called()

    @pytest.mark.parametrize("emails", [[], [f"p{n}@obra.mx" for n in range(21)]])
    def test_between_one_and_twenty_at_a_time(
        self, authenticated_client, correo, emails
    ) -> None:
        response = authenticated_client.post(URL, {"emails": emails}, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_without_a_session_nobody_is_invited(self, api_client, correo) -> None:
        response = api_client.post(URL, {"emails": ["ana@estudio.mx"]}, format="json")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_a_mail_that_did_not_go_out_keeps_the_invitation(
        self, authenticated_client, correo
    ) -> None:
        """El administrador puede reenviarla: lo que falló fue el correo."""
        correo.return_value = False

        response = authenticated_client.post(
            URL, {"emails": ["ana@estudio.mx"]}, format="json"
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["invited"][0]["email_sent"] is False
        assert Invitation.objects.filter(status="pending").count() == 1


@pytest.mark.django_db
class TestTanda:
    """Bug iteracion-16 - Una tanda sale de una vez.

    Veinte correos uno por uno, con 10 s de espera cada uno, podían pasar del
    tiempo de la función; si se cortaba a media tanda quedaban invitaciones
    pendientes que nunca recibieron su correo.
    """

    def test_twenty_go_out_in_one_send(self, authenticated_client, user, correo):
        emails = [f"p{n:02d}@obra.mx" for n in range(20)]

        response = authenticated_client.post(URL, {"emails": emails}, format="json")

        assert response.status_code == status.HTTP_201_CREATED
        correo.assert_called_once()
        assert [m.to for m in mensajes(correo)] == emails
        assert len(set(enlaces(correo))) == 20
        assert all(i["email_sent"] for i in response.data["invited"])
        assert Invitation.objects.filter(account=user).count() == 20

    def test_if_the_send_is_cut_no_invitation_is_left_without_its_email(
        self, authenticated_client, correo
    ) -> None:
        correo.side_effect = RuntimeError("la función se cortó a media tanda")

        with pytest.raises(RuntimeError):
            authenticated_client.post(
                URL, {"emails": ["ana@estudio.mx", "luis@obra.mx"]}, format="json"
            )

        assert not Invitation.objects.exists()


class TestEnlaceDeLaMarca:
    """Sin APP_BASE_URL configurada, el enlace va al dominio de Itzaka."""

    def test_the_default_base_url_is_the_brand_domain(self) -> None:
        """SEC-04 · iteracion-26 #9 — En producción (Vercel, sin DEBUG), itzaka.com."""
        entorno = {
            k: v
            for k, v in os.environ.items()
            if k not in ("APP_BASE_URL", "DEBUG") and not k.startswith("VERCEL")
        }
        entorno["DJANGO_SETTINGS_MODULE"] = "core.settings"
        entorno["VERCEL"] = "1"
        entorno["SECRET_KEY"] = "x" * 50
        salida = subprocess.run(  # noqa: S603 -- el mismo intérprete, sin shell
            [
                sys.executable,
                "-c",
                "from django.conf import settings as s; print(s.APP_BASE_URL)",
            ],
            cwd=Path(core_settings.__file__).resolve().parents[1],
            env=entorno,
            capture_output=True,
            text=True,
            check=True,
        )

        assert salida.stdout.strip() == "https://itzaka.com"


@pytest.mark.django_db
class TestDosEnviosAlMismoTiempo:
    """Bug iteracion-16 - Dos envíos al mismo tiempo, sin error del sistema."""

    def test_the_second_one_says_it_is_already_pending(
        self, authenticated_client, user, correo, mocker
    ) -> None:
        # La otra petición ya guardó la invitación, pero ésta no alcanzó a verla.
        InvitationFactory(account=user, email="ana@estudio.mx")
        mocker.patch("apps.team.services.pending_invitation", return_value=None)

        response = authenticated_client.post(
            URL, {"emails": ["ana@estudio.mx"]}, format="json"
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["skipped"] == [
            {
                "email": "ana@estudio.mx",
                "reason": "Ya tiene una invitación pendiente; puedes reenviarla.",
            }
        ]
        assert Invitation.objects.filter(account=user).count() == 1
        correo.assert_not_called()
