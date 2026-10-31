"""Máquinas de estado con estados terminales (iteracion-26 #20 · SEC-03.1).

Cada modelo con un estado de opciones registra su tabla: de qué estado se pasa
a cuál, y cuáles son finales. Un estado final no tiene salida, y una fila en él
ya no cambia. Las tablas se revisan aquí, en su forma; que cada servicio las
consulte sobre la fila bloqueada se prueba en la app de cada modelo.
"""

from importlib import import_module

import pytest
from rest_framework.exceptions import ValidationError

from common.state_machine import CLOSED, NOT_ALLOWED, REGISTRY, Transitions, register

#: Los servicios que registran una tabla al importarse.
STATEFUL_SERVICES = (
    "apps.quotes.services",
    "apps.projects.services",
    "apps.team.services",
)

TABLE = Transitions(
    field="status",
    allowed={
        "draft": frozenset({"sent"}),
        "sent": frozenset({"closed"}),
        "closed": frozenset(),
    },
    terminal=frozenset({"closed"}),
)


class _Row:
    def __init__(self, status: str) -> None:
        self.status = status


class TestTransitions:
    def test_an_allowed_transition_passes(self) -> None:
        TABLE.check("draft", "sent")

    def test_a_transition_out_of_the_table_is_a_400_on_its_field(self) -> None:
        with pytest.raises(ValidationError) as error:
            TABLE.check("draft", "closed")

        assert error.value.detail == {"status": [NOT_ALLOWED]}

    def test_a_terminal_state_has_no_way_out(self) -> None:
        with pytest.raises(ValidationError):
            TABLE.check("closed", "draft")

    def test_the_service_can_say_it_in_its_own_words(self) -> None:
        with pytest.raises(ValidationError) as error:
            TABLE.check("closed", "sent", message="Ya está cerrada")

        assert error.value.detail == ["Ya está cerrada"]

    def test_a_row_in_a_terminal_state_is_not_editable(self) -> None:
        TABLE.ensure_editable(_Row("sent"))

        with pytest.raises(ValidationError) as error:
            TABLE.ensure_editable(_Row("closed"))

        assert error.value.detail == [CLOSED]

    def test_register_keeps_the_table_of_its_model(self) -> None:
        class Ticket:
            """Un modelo cualquiera: register no lo instancia ni lo consulta."""

        try:
            assert register(Ticket, TABLE) is TABLE
            assert REGISTRY[Ticket] is TABLE
        finally:
            REGISTRY.pop(Ticket, None)


def test_each_stateful_model_names_every_state_and_closes_its_terminals() -> None:
    """Lo equivalente en apps a la línea base de plataforma (va en #29)."""
    for module in STATEFUL_SERVICES:
        import_module(module)
    labels = {model._meta.label for model in REGISTRY}

    assert {"quotes.Quote", "projects.Project", "team.Invitation"} <= labels
    for model, table in REGISTRY.items():
        states = {value for value, _label in model._meta.get_field(table.field).choices}
        assert set(table.allowed) == states, model._meta.label
        assert table.terminal, model._meta.label
        assert all(not table.allowed[state] for state in table.terminal), (
            model._meta.label
        )
