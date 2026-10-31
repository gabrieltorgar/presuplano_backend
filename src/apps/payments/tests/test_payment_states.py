"""Un pago no entra en un proyecto finalizado ni se reescribe (iteracion-26 #20).

El cierre del proyecto se revisa sobre su fila bloqueada: si otra petición lo
finalizó después de que ésta lo leyó, el pago no entra. Un pago registrado no
se edita ni se borra por la API: su ruta sólo lee y registra.
"""

from datetime import date
from decimal import Decimal

import pytest
from rest_framework import status
from rest_framework.exceptions import ValidationError

from apps.payments.models import Payment
from apps.payments.services import register_payment
from apps.payments.tests.test_payments import PAYMENTS_URL, make_project_with_advance
from apps.projects.models import Project


@pytest.mark.django_db
class TestAPaymentOnAFinishedProject:
    """SEC-03.1 - El proyecto cerrado se revisa en la fila releída."""

    def test_it_does_not_enter_a_project_finished_meanwhile(self, user) -> None:
        project = make_project_with_advance(user)
        Project.objects.filter(pk=project.pk).update(status=Project.Status.FINISHED)

        with pytest.raises(ValidationError, match="finalizado"):
            register_payment(
                owner=user, project=project, amount=Decimal("100"), date=date.today()
            )

        assert not Payment.objects.filter(project=project).exists()


@pytest.mark.django_db
class TestOnlyItsActionsWriteAPayment:
    """SEC-03.3 - La ruta de pagos no tiene PUT, PATCH ni DELETE."""

    @pytest.mark.parametrize("method", ["put", "patch", "delete"])
    def test_a_payment_is_not_rewritten(
        self, authenticated_client, user, method
    ) -> None:
        project = make_project_with_advance(user)
        payment = register_payment(
            owner=user, project=project, amount=Decimal("100"), date=date.today()
        )

        response = getattr(authenticated_client, method)(
            f"{PAYMENTS_URL}{payment.id}/", {"amount": "1"}, format="json"
        )

        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED
        payment.refresh_from_db()
        assert payment.amount == Decimal("100")

    def test_the_owner_sent_by_the_client_is_ignored(
        self, authenticated_client, user, user_factory
    ) -> None:
        """Control positivo: el pago se registra, en la cuenta de quien lo pide."""
        project = make_project_with_advance(user)
        other = user_factory()

        response = authenticated_client.post(
            PAYMENTS_URL,
            {
                "project": str(project.id),
                "amount": "100",
                "date": "2026-01-15",
                "owner": str(other.id),
            },
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert Payment.objects.get(pk=response.data["id"]).owner_id == user.id
