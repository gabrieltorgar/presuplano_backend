"""Pruebas del módulo de personal (US-96, US-97, US-98).

Quién hace el trabajo, cuánto de cada partida le tocó, cuánto ha ejecutado y
cuánto se le debe. El dinero que entra ya se llevaba; esto es el que sale.
"""

from decimal import Decimal

import pytest
from rest_framework import status

from apps.catalog.tests.factories import TariffFactory
from apps.clients.tests.factories import ClientFactory
from apps.projects.services import start_project
from apps.quotes.services import create_quote
from apps.staff.tests.factories import WorkerFactory

WORKERS_URL = "/api/workers/"
ASSIGNMENTS_URL = "/api/assignments/"
WORKER_PAYMENTS_URL = "/api/worker-payments/"


def make_project(user):
    """Proyecto con 100 m² de muro a 480 y 20 ml de castillo a 350."""
    client = ClientFactory(owner=user, name="Constructora Reyes")
    muro = TariffFactory(owner=user, name="Muro de block", unit_price="480")
    castillo = TariffFactory(
        owner=user, name="Castillo armado", unit_type="linear_meter", unit_price="350"
    )
    quote = create_quote(
        owner=user,
        client=client,
        items_data=[
            {"tariff": muro, "quantity": Decimal("100")},
            {"tariff": castillo, "quantity": Decimal("20")},
        ],
    )
    project = start_project(owner=user, quote=quote)
    return project, quote.items.get(tariff=muro), quote.items.get(tariff=castillo), muro


@pytest.mark.django_db
class TestWorkerRegistry:
    """US-96: dar de alta a quien hace el trabajo, con lo que sabe hacer."""

    def test_registers_a_person_with_the_services_they_do(
        self, authenticated_client, user
    ) -> None:
        """Flujo principal - Alta de personal con sus servicios."""
        aplanado = TariffFactory(owner=user, name="Aplanado fino")
        payload = {
            "name": "Juan Pérez",
            "kind": "person",
            "phone": "5512345678",
            "services": [{"tariff": str(aplanado.id), "unit_price": "180.00"}],
        }

        response = authenticated_client.post(WORKERS_URL, payload, format="json")

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["name"] == "Juan Pérez"
        assert response.data["services"][0]["tariff_name"] == "Aplanado fino"
        # Lo que se le paga no es lo que se le cobra al cliente, y viaja como
        # cadena: el formulario que lo lee espera texto, no un flotante.
        assert response.data["services"][0]["unit_price"] == "180.00"

    def test_registers_a_company(self, authenticated_client) -> None:
        """Flujo principal - El personal también puede ser una empresa."""
        response = authenticated_client.post(
            WORKERS_URL,
            {"name": "Herrería del Norte", "kind": "company"},
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["kind"] == "company"

    def test_one_service_can_be_done_by_several_people(
        self, authenticated_client, user
    ) -> None:
        """Flujo principal - Un servicio lo hacen varios y cada quien varios."""
        aplanado = TariffFactory(owner=user, name="Aplanado fino")
        pintura = TariffFactory(owner=user, name="Pintura vinílica")
        for name, servicios in (
            ("Juan Pérez", [aplanado, pintura]),
            ("Luis Ramos", [aplanado]),
        ):
            authenticated_client.post(
                WORKERS_URL,
                {
                    "name": name,
                    "services": [
                        {"tariff": str(t.id), "unit_price": "180.00"} for t in servicios
                    ],
                },
                format="json",
            )

        listado = authenticated_client.get(WORKERS_URL)

        por_nombre = {w["name"]: w for w in listado.data}
        assert len(por_nombre["Juan Pérez"]["services"]) == 2
        assert len(por_nombre["Luis Ramos"]["services"]) == 1

    def test_only_one_self_worker_per_account(self, authenticated_client) -> None:
        """Caso de borde - «Yo» es uno solo."""
        authenticated_client.post(
            WORKERS_URL, {"name": "Yo", "is_self": True}, format="json"
        )

        segundo = authenticated_client.post(
            WORKERS_URL, {"name": "Mi despacho", "is_self": True}, format="json"
        )

        assert segundo.status_code == status.HTTP_400_BAD_REQUEST

    def test_workers_are_isolated_per_account(
        self, authenticated_client, user_factory
    ) -> None:
        """Caso de borde - El personal de otra cuenta no se ve."""
        WorkerFactory(owner=user_factory(), name="Ajeno")

        response = authenticated_client.get(WORKERS_URL)

        assert [w["name"] for w in response.data] == []


@pytest.mark.django_db
class TestDistribution:
    """US-97: repartir las partidas del proyecto entre el personal."""

    def test_assigns_part_of_an_item_to_a_worker(
        self, authenticated_client, user
    ) -> None:
        """Flujo principal - Repartir una partida."""
        project, muro_item, _, muro = make_project(user)
        juan = WorkerFactory(owner=user, name="Juan Pérez")

        response = authenticated_client.post(
            ASSIGNMENTS_URL,
            {
                "project": str(project.id),
                "quote_item": str(muro_item.id),
                "worker": str(juan.id),
                "quantity": "60",
                "unit_price": "300",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        # 60 m² a 300: eso es lo comprometido con Juan.
        assert Decimal(response.data["committed_value"]) == Decimal("18000.00")

    def test_price_comes_from_what_the_worker_charges_me(
        self, authenticated_client, user
    ) -> None:
        """Flujo principal - El precio sale de lo que ese trabajador cobra."""
        project, muro_item, _, muro = make_project(user)
        juan = WorkerFactory(owner=user, name="Juan Pérez")
        juan.services.create(tariff=muro, unit_price=Decimal("300"))

        response = authenticated_client.post(
            ASSIGNMENTS_URL,
            {
                "project": str(project.id),
                "quote_item": str(muro_item.id),
                "worker": str(juan.id),
                "quantity": "60",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert Decimal(response.data["unit_price"]) == Decimal("300.00")

    def test_without_a_price_it_asks_for_one(self, authenticated_client, user) -> None:
        """Caso de borde - Sin precio no hay reparto."""
        project, muro_item, _, _ = make_project(user)
        juan = WorkerFactory(owner=user, name="Juan Pérez")

        response = authenticated_client.post(
            ASSIGNMENTS_URL,
            {
                "project": str(project.id),
                "quote_item": str(muro_item.id),
                "worker": str(juan.id),
                "quantity": "60",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "paga" in str(response.data).lower()

    def test_cannot_hand_out_more_than_the_item_has(
        self, authenticated_client, user
    ) -> None:
        """Caso de borde - No se reparte más de lo cotizado."""
        project, muro_item, _, _ = make_project(user)
        juan = WorkerFactory(owner=user, name="Juan Pérez")
        luis = WorkerFactory(owner=user, name="Luis Ramos")
        for worker, quantity in ((juan, "60"), (luis, "30")):
            authenticated_client.post(
                ASSIGNMENTS_URL,
                {
                    "project": str(project.id),
                    "quote_item": str(muro_item.id),
                    "worker": str(worker.id),
                    "quantity": quantity,
                    "unit_price": "300",
                },
                format="json",
            )

        pasado = WorkerFactory(owner=user, name="Ana Soto")
        response = authenticated_client.post(
            ASSIGNMENTS_URL,
            {
                "project": str(project.id),
                "quote_item": str(muro_item.id),
                "worker": str(pasado.id),
                "quantity": "20",
                "unit_price": "300",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "10" in str(response.data)

    def test_the_project_shows_what_is_left_to_hand_out(
        self, authenticated_client, user
    ) -> None:
        """Flujo principal - El proyecto dice qué falta por repartir."""
        project, muro_item, _, _ = make_project(user)
        juan = WorkerFactory(owner=user, name="Juan Pérez")
        authenticated_client.post(
            ASSIGNMENTS_URL,
            {
                "project": str(project.id),
                "quote_item": str(muro_item.id),
                "worker": str(juan.id),
                "quantity": "60",
                "unit_price": "300",
            },
            format="json",
        )

        response = authenticated_client.get(f"/api/projects/{project.id}/distribution/")

        muro = next(i for i in response.data["items"] if i["name"] == "Muro de block")
        assert Decimal(muro["assigned_quantity"]) == Decimal("60.00")
        assert Decimal(muro["unassigned_quantity"]) == Decimal("40.00")
        assert muro["assignments"][0]["worker_name"] == "Juan Pérez"


@pytest.mark.django_db
class TestAccrualAndPayment:
    """US-98: lo ejecutado se devenga y se paga, con su comprobante."""

    def _assign(self, client, project, item, worker, quantity="60", price="300"):
        return client.post(
            ASSIGNMENTS_URL,
            {
                "project": str(project.id),
                "quote_item": str(item.id),
                "worker": str(worker.id),
                "quantity": quantity,
                "unit_price": price,
            },
            format="json",
        )

    def test_an_advance_says_who_did_it_and_accrues(
        self, authenticated_client, user
    ) -> None:
        """Flujo principal - El avance dice quién lo hizo y se devenga."""
        project, muro_item, _, _ = make_project(user)
        juan = WorkerFactory(owner=user, name="Juan Pérez")
        self._assign(authenticated_client, project, muro_item, juan)

        authenticated_client.post(
            f"/api/projects/{project.id}/progress/",
            {
                "quote_item": str(muro_item.id),
                "quantity": "20",
                "date": "2026-02-10",
                "worker": str(juan.id),
            },
            format="json",
        )

        response = authenticated_client.get(f"{WORKERS_URL}{juan.id}/")
        # 60 × 300 comprometidos, 20 × 300 ya trabajados.
        assert Decimal(response.data["committed_value"]) == Decimal("18000.00")
        assert Decimal(response.data["accrued_value"]) == Decimal("6000.00")
        assert Decimal(response.data["balance"]) == Decimal("6000.00")

    def test_an_advance_without_an_author_owes_nobody(
        self, authenticated_client, user
    ) -> None:
        """Caso de borde - Un avance sin autor no le debe a nadie."""
        project, muro_item, _, _ = make_project(user)
        juan = WorkerFactory(owner=user, name="Juan Pérez")
        self._assign(authenticated_client, project, muro_item, juan)

        authenticated_client.post(
            f"/api/projects/{project.id}/progress/",
            {"quote_item": str(muro_item.id), "quantity": "20", "date": "2026-02-10"},
            format="json",
        )

        response = authenticated_client.get(f"{WORKERS_URL}{juan.id}/")
        assert Decimal(response.data["accrued_value"]) == Decimal("0.00")

    def test_paying_lowers_the_balance(self, authenticated_client, user) -> None:
        """Flujo principal - Pagarle baja lo que se le debe."""
        project, muro_item, _, _ = make_project(user)
        juan = WorkerFactory(owner=user, name="Juan Pérez")
        self._assign(authenticated_client, project, muro_item, juan)
        authenticated_client.post(
            f"/api/projects/{project.id}/progress/",
            {
                "quote_item": str(muro_item.id),
                "quantity": "20",
                "date": "2026-02-10",
                "worker": str(juan.id),
            },
            format="json",
        )

        pago = authenticated_client.post(
            WORKER_PAYMENTS_URL,
            {
                "worker": str(juan.id),
                "project": str(project.id),
                "amount": "2500",
                "date": "2026-02-15",
                "method": "cash",
            },
            format="json",
        )

        assert pago.status_code == status.HTTP_201_CREATED
        resumen = authenticated_client.get(
            f"{WORKER_PAYMENTS_URL}summary/", {"worker": str(juan.id)}
        )
        assert Decimal(resumen.data["total_paid"]) == Decimal("2500.00")
        assert Decimal(resumen.data["balance"]) == Decimal("3500.00")
        assert len(resumen.data["payments"]) == 1

    def test_a_payment_can_be_general(self, authenticated_client, user) -> None:
        """Caso alternativo - Un pago de la semana no es de un proyecto."""
        juan = WorkerFactory(owner=user, name="Juan Pérez")

        response = authenticated_client.post(
            WORKER_PAYMENTS_URL,
            {"worker": str(juan.id), "amount": "1000", "date": "2026-02-15"},
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["project"] is None

    def test_nobody_pays_themselves(self, authenticated_client, user) -> None:
        """Caso de borde - A «Yo» no se le paga."""
        yo = WorkerFactory(owner=user, name="Yo", is_self=True)

        response = authenticated_client.post(
            WORKER_PAYMENTS_URL,
            {"worker": str(yo.id), "amount": "1000", "date": "2026-02-15"},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_self_work_is_counted_but_not_owed(
        self, authenticated_client, user
    ) -> None:
        """Flujo principal - Lo que hago yo se reparte, pero no se debe."""
        project, muro_item, _, _ = make_project(user)
        yo = WorkerFactory(owner=user, name="Yo", is_self=True)

        self._assign(authenticated_client, project, muro_item, yo, price="0")
        authenticated_client.post(
            f"/api/projects/{project.id}/progress/",
            {
                "quote_item": str(muro_item.id),
                "quantity": "20",
                "date": "2026-02-10",
                "worker": str(yo.id),
            },
            format="json",
        )

        response = authenticated_client.get(f"{WORKERS_URL}{yo.id}/")
        assert Decimal(response.data["balance"]) == Decimal("0.00")

    def test_payments_are_isolated_per_account(
        self, authenticated_client, user_factory
    ) -> None:
        """Caso de borde - No se le paga al personal de otra cuenta."""
        ajeno = WorkerFactory(owner=user_factory())

        response = authenticated_client.post(
            WORKER_PAYMENTS_URL,
            {"worker": str(ajeno.id), "amount": "1000", "date": "2026-02-15"},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
