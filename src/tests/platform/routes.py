"""El inventario de rutas de la API para las pruebas base (TDD-B01, iteracion-25 #10).

Recorre el URLconf y entrega cada vista de DRF bajo ``api/`` con sus acciones,
sus límites de intentos (por dirección y por cuenta, iteracion-26 #16) y sus
permisos efectivos. ``as_view`` de DRF guarda ``cls``, ``initkwargs`` y, en los
ViewSets, ``actions``; el router pasa lo de
``@action(throttle_scope=…, permission_classes=…)`` por ``initkwargs``.
"""

import re
import uuid
from collections.abc import Iterator
from types import SimpleNamespace

from django.urls import URLResolver, get_resolver
from rest_framework.views import APIView

#: Un argumento de la ruta, regex (``(?P<pk>…)``) o convertidor (``<uuid:id>``).
ROUTE_KWARG = re.compile(r"\(\?P<(\w+)>[^)]*\)|<(?:\w+:)?(\w+)>")
HTTP_METHODS = ("get", "post", "put", "patch", "delete")


def api_routes(patterns=None, prefix: str = "") -> Iterator[SimpleNamespace]:
    """Cada ruta de DRF bajo ``api/`` (también las gemelas ``.json``)."""
    for pattern in get_resolver().url_patterns if patterns is None else patterns:
        route = prefix + str(pattern.pattern).lstrip("^").rstrip("$")
        if isinstance(pattern, URLResolver):
            yield from api_routes(pattern.url_patterns, route)
            continue
        cls = getattr(pattern.callback, "cls", None)
        if not (isinstance(cls, type) and issubclass(cls, APIView)):
            continue
        if not route.startswith("api/"):
            continue
        kwargs = getattr(pattern.callback, "initkwargs", None) or {}
        actions = dict(getattr(pattern.callback, "actions", None) or {})
        yield SimpleNamespace(
            name=pattern.name or route,
            route=route,
            cls=cls,
            initkwargs=kwargs,
            # ViewSets: {"get": "list", …}; vistas simples: {}.
            actions=actions,
            methods=sorted(actions) or [m for m in HTTP_METHODS if hasattr(cls, m)],
            scope=kwargs.get("throttle_scope", getattr(cls, "throttle_scope", None)),
            identifier_scope=kwargs.get(
                "identifier_throttle_scope",
                getattr(cls, "identifier_throttle_scope", None),
            ),
            permissions=list(kwargs.get("permission_classes", cls.permission_classes)),
        )


def is_format_twin(route: SimpleNamespace) -> bool:
    """La ruta ``.json`` que DRF agrega junto a cada una del router."""
    return re.search(r"\(\?P<format>|<(?:\w+:)?format>", route.route) is not None


def sample_url(route: SimpleNamespace) -> str:
    """Una URL que resuelve a la ruta, con un UUID en cada argumento."""
    return "/" + ROUTE_KWARG.sub(str(uuid.UUID(int=1)), route.route)
