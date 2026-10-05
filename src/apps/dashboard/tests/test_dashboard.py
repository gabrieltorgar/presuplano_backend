"""Pruebas del inicio: el resumen de la cuenta (US-99).

Lo que el arquitecto quiere ver al abrir: qué hay en marcha, cuánto de lo que
cotiza se vuelve obra, qué le deben, qué debe, y qué se vende.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from rest_framework import status

from apps.catalog.tests.factories import TariffFactory
from apps.clients.tests.factories import ClientFactory
from apps.payments.services import register_payment
from apps.projects.services import register_progress, start_project
from apps.quotes.services import create_quote
from apps.staff.services import assign_service, pay_worker
from apps.staff.tests.factories import WorkerFactory

URL = "/api/dashboard/"


def make_account(user):
    """Dos obras en marcha, una cotización sin vender y un albañil trabajando."""
    reyes = ClientFactory(owner=user, name="Constructora Reyes")
    mena = ClientFactory(owner=user, name="Laura Mena")
    muro = TariffFactory(owner=user, name="Muro de block", unit_price="480")
    castillo = TariffFactory(
        owner=user, name="Castillo armado", unit_type="linear_meter", unit_price="350"
    )
    piso = TariffFactory(owner=user, name="Firme de concreto", unit_price="300")

    vendida = create_quote(
        owner=user,
        client=reyes,
        items_data=[
            {"tariff": muro, "quantity": Decimal("100")},  # 48 000
            {"tariff": castillo, "quantity": Decimal("20")},  # 7 000
        ],
    )
    segunda = create_quote(
        owner=user,
        client=mena,
        items_data=[{"tariff": piso, "quantity": Decimal("50")}],  # 15 000
    )
    # Cotizada y no vendida: cuenta en lo cotizado, no en lo convertido.
    create_quote(
        owner=user,
        client=reyes,
        items_data=[{"tariff": muro, "quantity": Decimal("10")}],  # 4 800
    )

    obra = start_project(owner=user, quote=vendida)
    otra = start_project(owner=user, quote=segunda)

    hoy = date.today()
    register_payment(owner=user, project=obra, amount=Decimal("20000"), date=hoy)
    register_payment(owner=user, project=otra, amount=Decimal("5000"), date=hoy)

    juan = WorkerFactory(owner=user, name="Juan Pérez")
    yo = WorkerFactory(owner=user, name="Mi despacho", is_self=True)
    muro_item = vendida.items.get(tariff=muro)
    assign_service(
        project=obra,
        quote_item=muro_item,
        worker=juan,
        quantity=Decimal("60"),
        unit_price=Decimal("300"),
    )
    register_progress(
        project=obra,
        quote_item=muro_item,
        quantity=Decimal("20"),
        date=hoy,
        worker=juan,
    )
    pay_worker(owner=user, worker=juan, amount=Decimal("2500"), date=hoy)

    # La casa también trabaja: se reparte y se avanza, pero no se le debe ni
    # se le cuenta entre el personal.
    castillo_item = vendida.items.get(tariff=castillo)
    assign_service(
        project=obra,
        quote_item=castillo_item,
        worker=yo,
        quantity=Decimal("20"),
        unit_price=Decimal("0"),
    )
    register_progress(
        project=obra,
        quote_item=castillo_item,
        quantity=Decimal("20"),
        date=hoy,
        worker=yo,
    )
    return {"obra": obra, "juan": juan, "yo": yo, "muro_item": muro_item}


@pytest.mark.django_db
class TestDashboard:
    """US-99: el inicio resume la cuenta."""

    def test_the_summary_counts_what_is_in_progress(
        self, authenticated_client, user
    ) -> None:
        """Flujo principal - Lo que hay en marcha."""
        make_account(user)

        response = authenticated_client.get(URL)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["active_projects"] == 2
        assert response.data["quotes_total"] == 3
        assert response.data["quotes_in_project"] == 2

    def test_it_says_how_much_of_what_is_quoted_becomes_work(
        self, authenticated_client, user
    ) -> None:
        """Flujo principal - Cuánto de lo cotizado se vuelve obra."""
        make_account(user)

        data = authenticated_client.get(URL).data

        # 55 000 + 15 000 vendidos, de 74 800 cotizados.
        assert Decimal(data["quoted_value"]) == Decimal("74800.00")
        assert Decimal(data["converted_value"]) == Decimal("70000.00")
        assert data["conversion_rate"] == pytest.approx(93.58, abs=0.01)

    def test_it_says_what_is_owed_to_me_and_what_i_owe(
        self, authenticated_client, user
    ) -> None:
        """Flujo principal - Cuentas por cobrar y por pagar."""
        make_account(user)

        data = authenticated_client.get(URL).data

        # Cobrar: (55 000 − 20 000) + (15 000 − 5 000).
        assert Decimal(data["receivable"]) == Decimal("45000.00")
        # Pagar: 20 m² × 300 trabajados, menos 2 500 ya pagados.
        assert Decimal(data["payable"]) == Decimal("3500.00")

    def test_income_is_the_last_six_months_ending_today(
        self, authenticated_client, user
    ) -> None:
        """Flujo principal - Ingresos de los últimos seis meses."""
        make_account(user)

        data = authenticated_client.get(URL).data

        meses = data["monthly_income"]
        assert len(meses) == 6
        assert meses[-1]["month"] == date.today().strftime("%Y-%m")
        # Lo cobrado este mes: 20 000 + 5 000.
        assert Decimal(meses[-1]["amount"]) == Decimal("25000.00")
        assert Decimal(meses[0]["amount"]) == Decimal("0.00")

    def test_an_old_payment_lands_on_its_month(
        self, authenticated_client, user
    ) -> None:
        """Caso de borde - Un cobro viejo no se cuenta en este mes."""
        cuenta = make_account(user)
        viejo = date.today() - timedelta(days=400)
        register_payment(
            owner=user, project=cuenta["obra"], amount=Decimal("9000"), date=viejo
        )

        data = authenticated_client.get(URL).data

        assert Decimal(data["monthly_income"][-1]["amount"]) == Decimal("25000.00")
        assert all(
            mes["month"] != viejo.strftime("%Y-%m") for mes in data["monthly_income"]
        )

    def test_the_best_sellers_are_what_was_sold(
        self, authenticated_client, user
    ) -> None:
        """Flujo principal - Los servicios más vendidos."""
        make_account(user)

        data = authenticated_client.get(URL).data

        servicios = data["top_services"]
        assert servicios[0]["name"] == "Muro de block"
        # Sólo los 100 m² vendidos; los 10 de la cotización sin vender, no.
        assert Decimal(servicios[0]["quantity"]) == Decimal("100.00")
        assert Decimal(servicios[0]["amount"]) == Decimal("48000.00")
        assert [s["name"] for s in servicios] == [
            "Muro de block",
            "Firme de concreto",
            "Castillo armado",
        ]

    def test_the_best_clients_are_the_ones_who_bought(
        self, authenticated_client, user
    ) -> None:
        """Flujo principal - Los clientes que más compran."""
        make_account(user)

        data = authenticated_client.get(URL).data

        assert data["top_clients"][0]["name"] == "Constructora Reyes"
        assert Decimal(data["top_clients"][0]["amount"]) == Decimal("55000.00")
        assert data["top_clients"][0]["projects"] == 1

    def test_the_hardest_working_staff(self, authenticated_client, user) -> None:
        """Flujo principal - El personal con más trabajos."""
        make_account(user)

        data = authenticated_client.get(URL).data

        assert data["top_workers"][0]["name"] == "Juan Pérez"
        assert data["top_workers"][0]["jobs"] == 1
        assert Decimal(data["top_workers"][0]["amount"]) == Decimal("6000.00")
        # «Yo» no es personal a quien contar trabajos.
        assert all(w["name"] != "Mi despacho" for w in data["top_workers"])

    def test_an_empty_account_reads_as_zero(self, authenticated_client) -> None:
        """Caso de borde - Una cuenta recién abierta no se rompe."""
        data = authenticated_client.get(URL).data

        assert data["active_projects"] == 0
        assert Decimal(data["quoted_value"]) == Decimal("0.00")
        assert data["conversion_rate"] == 0
        assert len(data["monthly_income"]) == 6
        assert data["top_services"] == []

    def test_another_account_is_not_summarized_here(
        self, authenticated_client, user_factory
    ) -> None:
        """Caso de borde - El resumen es de esta cuenta."""
        make_account(user_factory())

        data = authenticated_client.get(URL).data

        assert data["active_projects"] == 0
        assert Decimal(data["receivable"]) == Decimal("0.00")

    def test_without_a_session_there_is_no_summary(self, api_client) -> None:
        """Caso de borde - Sin sesión no hay resumen."""
        assert api_client.get(URL).status_code == status.HTTP_401_UNAUTHORIZED
