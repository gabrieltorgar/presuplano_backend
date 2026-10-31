"""El estado de una invitación (iteracion-26 #20 · SEC-03.1, SEC-03.2).

Una invitación espera hasta que se acepta o se cancela, y de ahí ya no sale:
una aceptada no se cancela ni se reenvía, una cancelada no se acepta. Cada
cambio se revisa sobre la fila bloqueada y releída: cancelar mientras alguien
la acepta, o reenviarla mientras tanto, no deja una invitación cancelada con el
colaborador dentro ni le cambia el enlace a una que ya se usó.
"""

import pytest
from django.db import connections
from rest_framework import status

from apps.accounts.tests.factories import UserFactory
from apps.team.models import Invitation
from apps.team.services import INVITATION_TRANSITIONS
from apps.team.tests.factories import InvitationFactory
from apps.team.tests.test_invitation_actions import cancelar, como, reenviar
from common.state_machine import REGISTRY
from common.tests.concurrency import POSTGRES_ONLY, at_the_same_time


@pytest.fixture
def admin(db):
    return UserFactory()


def test_an_invitation_ends_accepted_or_cancelled_and_never_leaves() -> None:
    """SEC-03.1 - La tabla de la invitación y sus estados finales."""
    pending, accepted, cancelled = (
        Invitation.Status.PENDING,
        Invitation.Status.ACCEPTED,
        Invitation.Status.CANCELLED,
    )
    assert REGISTRY[Invitation] is INVITATION_TRANSITIONS
    assert INVITATION_TRANSITIONS.allowed == {
        pending: frozenset({accepted, cancelled}),
        accepted: frozenset(),
        cancelled: frozenset(),
    }
    assert INVITATION_TRANSITIONS.terminal == {accepted, cancelled}


@pytest.fixture
def correo_que_tarda(settings, mocker):
    """El correo sale, y mientras salía alguien hizo algo con la invitación."""
    settings.RESEND_API_KEY = "re_test"
    return mocker.patch("apps.team.emails.mail.send_email", return_value=True)


@pytest.mark.django_db
class TestResendingWhileItChanges:
    """SEC-03.1 - Lo que cuenta es la fila releída después del correo."""

    @pytest.mark.parametrize(
        ("meanwhile", "message"),
        [
            (Invitation.Status.ACCEPTED, "ya es colaborador"),
            (Invitation.Status.CANCELLED, "ya se canceló"),
        ],
    )
    def test_a_closed_invitation_keeps_its_link(
        self, admin, correo_que_tarda, meanwhile, message, monkeypatch
    ) -> None:
        # Lo de «mientras tanto» lo hizo y confirmó otra petición, pero aquí
        # corre dentro de ésta: sin su transacción (ATOMIC_REQUESTS, iteracion-26
        # #22) para que el 400 no revierta también lo que hizo la otra.
        monkeypatch.setitem(
            connections["default"].settings_dict, "ATOMIC_REQUESTS", False
        )
        invitacion = InvitationFactory(account=admin, email="mar@despacho.mx")
        huella = invitacion.token_hash

        def mientras_sale(**_kwargs) -> bool:
            Invitation.objects.filter(pk=invitacion.pk).update(status=meanwhile)
            return True

        correo_que_tarda.side_effect = mientras_sale

        response = como(admin).post(reenviar(invitacion.id))

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert message in str(response.data["detail"]).lower()
        invitacion.refresh_from_db()
        assert invitacion.status == meanwhile
        assert invitacion.token_hash == huella


@pytest.mark.django_db
class TestCancelling:
    def test_a_cancelled_invitation_is_not_cancelled_again(self, admin) -> None:
        cancelada = InvitationFactory(account=admin, status=Invitation.Status.CANCELLED)

        response = como(admin).post(cancelar(cancelada.id))

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "ya se canceló" in str(response.data["detail"]).lower()


@POSTGRES_ONLY
@pytest.mark.django_db(transaction=True)
def test_concurrent_cancellations_cancel_once(admin) -> None:
    """SEC-03.2 - La segunda espera el bloqueo y encuentra la invitación cerrada."""
    invitacion = InvitationFactory(account=admin)

    def cancel(client):
        return client.post(cancelar(invitacion.id)).status_code

    codes = at_the_same_time(admin, cancel, cancel)

    assert sorted(codes) == [204, 400]
    invitacion.refresh_from_db()
    assert invitacion.status == Invitation.Status.CANCELLED
