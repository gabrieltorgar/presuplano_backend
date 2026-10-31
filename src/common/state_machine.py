"""Tablas de transiciones con estados terminales (SEC-03, iteracion-26 #20).

Cada modelo con un estado de opciones registra aquí la suya, en el servicio que
lo cambia (``register(Quote, Transitions(...))``): de qué estado se pasa a
cuál, y cuáles son finales. Todo estado es una llave; uno final mapea a un
conjunto vacío, así que no tiene salida, y una fila en él ya no se edita.

El servicio revisa la tabla sobre la fila releída con ``select_for_update``
dentro de su transacción, nunca sobre la que la petición leyó antes. Los
errores son el ``ValidationError`` de DRF, como el resto de los servicios: el
400 conserva la forma de siempre (``["mensaje"]`` o ``{"campo": [...]}``).
"""

from collections.abc import Mapping
from dataclasses import dataclass

from django.db.models import Model
from rest_framework.exceptions import ValidationError

#: Lo que se responde cuando la tabla no tiene ese paso.
NOT_ALLOWED = "Transición no permitida."

#: Lo que se responde al editar una fila en un estado final.
CLOSED = "El registro ya está cerrado y no se puede modificar."


@dataclass(frozen=True)
class Transitions:
    """Cada estado es una llave de ``allowed``; los de ``terminal`` no tienen salida."""

    field: str
    allowed: Mapping[str, frozenset[str]]
    terminal: frozenset[str]

    def check(self, current: str, to: str, *, message: str | None = None) -> None:
        """Rechaza el paso de ``current`` a ``to`` si la tabla no lo tiene.

        Raises:
            ValidationError: con ``message`` si el servicio lo dice en sus
                palabras; si no, «Transición no permitida.» en el campo.
        """
        if to not in self.allowed.get(current, frozenset()):
            raise ValidationError(message or {self.field: [NOT_ALLOWED]})

    def ensure_editable(self, obj: Model, *, message: str | None = None) -> None:
        """Las filas en un estado final no cambian: editar y borrar lo revisan antes.

        Raises:
            ValidationError: la fila está en un estado final.
        """
        if getattr(obj, self.field) in self.terminal:
            raise ValidationError(message or CLOSED)


#: La tabla de cada modelo con estado; la línea base de plataforma la recorre.
REGISTRY: dict[type[Model], Transitions] = {}


def register(model: type[Model], transitions: Transitions) -> Transitions:
    """Guarda la tabla de ``model`` y la devuelve, para nombrarla en su servicio."""
    REGISTRY[model] = transitions
    return transitions
