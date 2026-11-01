"""US-67: la lista de proyectos del servidor (iteracion-17 #7).

Fuente: backlog 4.9 → US-67 list_spec y su cambio «iteracion-17».
"""

from datetime import date
from decimal import Decimal

import pytest

from apps.catalog.tests.factories import TariffFactory
from apps.clients.tests.factories import ClientFactory
from apps.projects.models import Project
from apps.projects.services import register_progress, start_project
from apps.quotes.services import create_quote

URL = "/api/projects/"


def obra(
    user,
    *,
    cliente: str = "Constructora Reyes",
    precio: str = "100",
    avanzado: str = "0",
) -> Project:
    """Un proyecto de ``cliente``: 10 unidades a ``precio``, ``avanzado`` hechas."""
    quote = create_quote(
        owner=user,
        client=ClientFactory(owner=user, name=cliente),
        items_data=[
            {
                "tariff": TariffFactory(owner=user, unit_price=precio),
                "quantity": Decimal("10"),
            }
        ],
    )
    project = start_project(owner=user, quote=quote)
    if Decimal(avanzado) > 0:
        register_progress(
            project=project,
            quote_item=quote.items.get(),
            quantity=Decimal(avanzado),
            date=date(2026, 10, 1),
        )
    return project


def clientes(response) -> list[str]:
    return [row["client_name"] for row in response.data["results"]]


@pytest.mark.django_db
class TestLaListaDeProyectos:
    def test_la_lista_no_trae_los_avances(self, user, authenticated_client) -> None:
        """Cambio iteracion-17 - La lista no trae los avances."""
        obra(user, cliente="Reyes", precio="350", avanzado="4")

        response = authenticated_client.get(URL)

        fila = response.data["results"][0]
        assert response.data["count"] == 1
        assert fila["client_name"] == "Reyes"
        assert Decimal(fila["quoted_value"]) == Decimal("3500.00")
        assert Decimal(fila["advanced_value"]) == Decimal("1400.00")
        assert fila["progress_percentage"] == 40.0
        assert "progresses" not in fila
        assert "items" not in fila

    def test_por_omision_el_de_menos_avance_primero(
        self, user, authenticated_client
    ) -> None:
        obra(user, cliente="Mitad", avanzado="5")
        obra(user, cliente="Nada", avanzado="0")
        obra(user, cliente="Casi", avanzado="9")

        response = authenticated_client.get(URL)

        assert clientes(response) == ["Nada", "Mitad", "Casi"]

    def test_filtrar_y_ordenar_en_todo(self, user, authenticated_client) -> None:
        """Cambio iteracion-17 - Filtrar y ordenar en todo."""
        obra(user, cliente="En curso, poco", avanzado="2")
        obra(user, cliente="En curso, mucho", avanzado="8")
        terminado = obra(user, cliente="Terminado, nada", avanzado="0")
        Project.objects.filter(pk=terminado.pk).update(status=Project.Status.FINISHED)

        en_curso = authenticated_client.get(
            URL, {"status": "in_progress", "ordering": "progress_percentage"}
        )
        mas_avance = authenticated_client.get(URL, {"ordering": "-progress_percentage"})
        ambos = authenticated_client.get(URL, {"status": "in_progress,finished"})

        assert clientes(en_curso) == ["En curso, poco", "En curso, mucho"]
        assert clientes(mas_avance)[0] == "En curso, mucho"
        assert ambos.data["count"] == 3

    def test_mayor_cotizado_y_cliente(self, user, authenticated_client) -> None:
        obra(user, cliente="Zapata", precio="50")
        obra(user, cliente="Álvarez", precio="900")
        obra(user, cliente="Muñoz", precio="300")

        cotizado = authenticated_client.get(URL, {"ordering": "-quoted_value"})
        por_cliente = authenticated_client.get(URL, {"ordering": "client_name"})
        buscado = authenticated_client.get(URL, {"search": "munoz"})

        assert clientes(cotizado) == ["Álvarez", "Muñoz", "Zapata"]
        assert clientes(por_cliente) == ["Álvarez", "Muñoz", "Zapata"]
        assert clientes(buscado) == ["Muñoz"]

    def test_abrir_un_proyecto_pide_solo_ese_proyecto(
        self, user, authenticated_client
    ) -> None:
        """Cambio iteracion-17 - Abrir un proyecto pide solo ese proyecto.

        Sus avances, a su propia lista por páginas (iteracion-28 #16).
        """
        project = obra(user, cliente="Reyes", avanzado="3")

        response = authenticated_client.get(f"{URL}{project.id}/")
        progresses = authenticated_client.get(
            "/api/progresses/", {"project": str(project.id)}
        )

        assert response.data["client_name"] == "Reyes"
        assert len(response.data["items"]) == 1
        assert "progresses" not in response.data
        assert progresses.data["count"] == 1

    def test_el_de_otra_cuenta_no_aparece(
        self, user, authenticated_client, user_factory
    ) -> None:
        obra(user_factory(), cliente="Ajeno")

        assert authenticated_client.get(URL).data["count"] == 0
