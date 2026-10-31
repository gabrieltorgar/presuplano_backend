"""Corregir un reparto no lo cambia de dueño (iteracion-26 #20 · SEC-03.3).

Repartir de nuevo lo mismo es corregirlo: la cantidad, el precio o la nota. El
proyecto, la partida y la persona de un reparto son los suyos; si el cuerpo
manda otros, se ignoran —para repartir a alguien más se crea otro—. Y lo que
queda por repartir se cuenta con el proyecto bloqueado, así que dos repartos a
la vez no superan la partida.
"""

from decimal import Decimal

import pytest
from rest_framework import status

from apps.staff.models import Assignment
from apps.staff.services import assign_service
from apps.staff.tests.factories import WorkerFactory
from apps.staff.tests.test_staff import ASSIGNMENTS_URL, make_project
from common.tests.concurrency import POSTGRES_ONLY, at_the_same_time


def _handed(project, item, worker, quantity: str = "60") -> Assignment:
    return assign_service(
        project=project,
        quote_item=item,
        worker=worker,
        quantity=Decimal(quantity),
        unit_price=Decimal("300"),
    )


@pytest.mark.django_db
class TestCorrectingAHandOut:
    @pytest.mark.parametrize("method", ["put", "patch"])
    def test_its_project_item_and_worker_stay_its_own(
        self, authenticated_client, user, method
    ) -> None:
        """SEC-03.3 - Con control positivo: la cantidad sí cambia."""
        project, muro_item, castillo_item, _muro = make_project(user)
        juan = WorkerFactory(owner=user, name="Juan Pérez")
        luis = WorkerFactory(owner=user, name="Luis Ramos")
        assignment = _handed(project, muro_item, juan)
        other_project, *_rest = make_project(user)

        response = getattr(authenticated_client, method)(
            f"{ASSIGNMENTS_URL}{assignment.id}/",
            {
                "quantity": "40",
                "worker": str(luis.id),
                "quote_item": str(castillo_item.id),
                "project": str(other_project.id),
            },
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        assignment.refresh_from_db()
        assert assignment.quantity == Decimal("40")
        assert assignment.worker_id == juan.id
        assert assignment.quote_item_id == muro_item.id
        assert assignment.project_id == project.id
        assert Assignment.objects.count() == 1


@POSTGRES_ONLY
@pytest.mark.django_db(transaction=True)
def test_concurrent_hand_outs_never_exceed_the_item(user) -> None:
    """SEC-03.2 - 60 y 60 de una partida de 100: entra uno."""
    project, muro_item, _castillo, _muro = make_project(user)
    workers = [WorkerFactory(owner=user, name=name) for name in ("Juan", "Luis")]

    def hand_out(worker):
        def request(client):
            return client.post(
                ASSIGNMENTS_URL,
                {
                    "project": str(project.id),
                    "quote_item": str(muro_item.id),
                    "worker": str(worker.id),
                    "quantity": "60",
                    "unit_price": "300",
                },
            ).status_code

        return request

    codes = at_the_same_time(user, *(hand_out(worker) for worker in workers))

    assert sorted(codes) == [201, 400]
    assert Assignment.objects.filter(quote_item=muro_item).count() == 1
