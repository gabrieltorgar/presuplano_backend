"""Línea base del dominio: campos protegidos y máquinas de estado (TDD-B01, SEC-03).

No sale de una historia (iteracion-25 #10, iteracion-26 #29): dueño, empresa,
rol, estado y montos cambian solo por su acción, nunca porque el cliente los
mande (SEC-03), tampoco desde el admin; y cada modelo con estado registra su
tabla de transiciones con estados finales sin salida (SEC-03.1). La inspección
de los serializers es estática: ningún serializer se instancia, así que sus
querysets acotados nunca corren.
"""

import inspect
import re
from importlib import import_module
from importlib.util import find_spec

import pytest
from django.apps import apps
from django.contrib import admin
from django.test import RequestFactory
from rest_framework import serializers

from common.state_machine import REGISTRY

PROTECTED = re.compile(
    r"^(?:(?:owner|company|created_by|approved_by|status_changed_by|role)(?:_id)?"
    r"|is_staff|is_superuser|permissions"
    r"|status|[a-z]+_status|status_changed_at|subtotal|tax|total|[a-z_]+_total"
    r"|discount|discount_amount|refunded_amount|refund_amount|credit_amount|balance"
    r"|paid_at|approved_at|converted_at)$"
)
#: Campos protegidos que un serializer declara sin read_only, con el porqué.
WRITABLE_PROTECTED: dict[str, str] = {}
#: Campos protegidos que el admin edita en el formulario de cambio, con el porqué.
ADMIN_WRITABLE_PROTECTED: dict[str, str] = {
    "accounts.User.is_staff": (
        "el superusuario da o quita la entrada al admin; no hay otra puerta"
    ),
    "accounts.User.is_superuser": "el superusuario nombra a otro; no hay otra puerta",
}
#: Campos protegidos que se eligen al crear un registro desde el admin (y
#: después son de solo lectura: ProtectedFieldsAdminMixin.set_on_create_fields).
ADMIN_SET_ON_CREATE: dict[str, str] = {
    "owner": (
        "la cuenta del registro se elige al crearlo desde el admin (el documento "
        "toma su folio de esa cuenta); al editarlo ya no cambia"
    ),
}
#: Modelos con un estado de opciones que no es una máquina de estados.
EXEMPT_STATE: dict[str, str] = {
    "accounts.Subscription": (
        "nace activa al registrarse y ningún flujo la cambia todavía (no hay "
        "cobro); de solo lectura en la API y el admin. Cuando exista el cobro, "
        "su servicio registra la tabla"
    ),
}


def _app_modules(name: str):
    for config in apps.get_app_configs():
        if config.name.startswith("apps.") and find_spec(f"{config.name}.{name}"):
            yield import_module(f"{config.name}.{name}")


def _model_serializers():
    for module in _app_modules("serializers"):
        for obj in vars(module).values():
            if (
                isinstance(obj, type)
                and issubclass(obj, serializers.ModelSerializer)
                and obj.__module__ == module.__name__
            ):
                yield obj


def _read_only(cls, name: str) -> bool:
    meta, declared = cls.Meta, cls._declared_fields.get(name)
    return (
        name in getattr(meta, "read_only_fields", ())
        or getattr(meta, "extra_kwargs", {}).get(name, {}).get("read_only") is True
        or (
            declared is not None
            and (declared.read_only or isinstance(declared, serializers.HiddenField))
        )
    )


def test_protected_fields_are_read_only():
    """SEC-03: un campo protegido escribible lleva su motivo en WRITABLE_PROTECTED."""
    offenders, seen = [], set()
    for cls in _model_serializers():
        for name in getattr(cls.Meta, "fields", ()):
            key = f"{cls.__module__}.{cls.__qualname__}.{name}"
            if not PROTECTED.match(name) or _read_only(cls, name):
                continue
            seen.add(key)
            if key not in WRITABLE_PROTECTED:
                line = inspect.getsourcelines(cls)[1]
                offenders.append(f"{inspect.getsourcefile(cls)}:{line} {key}")
    assert not offenders, (
        "los campos protegidos cambian solo por su acción (security.md §3):\n"
        + "\n".join(offenders)
    )
    stale = sorted(set(WRITABLE_PROTECTED) - seen)
    assert not stale, "ya son de solo lectura; quítalos de WRITABLE_PROTECTED:\n" + (
        "\n".join(stale)
    )


@pytest.mark.django_db
def test_admin_keeps_protected_fields_read_only(admin_user):
    """SEC-03: ni al crear ni al editar; la cuenta dueña se elige sólo al crear."""
    request = RequestFactory().get("/admin/")
    request.user = admin_user
    offenders = []
    for model, model_admin in admin.site._registry.items():
        if not model.__module__.startswith("apps."):
            continue
        protected = [
            f.name for f in model._meta.concrete_fields if PROTECTED.match(f.name)
        ]
        add_form = model_admin.get_form(request).base_fields
        change_form = model_admin.get_form(request, obj=model()).base_fields
        for name in protected:
            key = f"{model._meta.label}.{name}"
            if key in ADMIN_WRITABLE_PROTECTED:
                continue
            if name in add_form and name not in ADMIN_SET_ON_CREATE:
                offenders.append(f"{key} (al crear)")
            if name in change_form:
                offenders.append(f"{key} (al editar)")
    assert not offenders, (
        "ponlos en protected_fields o set_on_create_fields "
        "(common.admin.ProtectedFieldsAdminMixin); cámbialos con su servicio:\n"
        + "\n".join(offenders)
    )


def test_state_machines_declare_terminal_states():
    """SEC-03.1: cada estado es una llave; los finales existen y no tienen salida."""
    list(_app_modules("services"))  # los servicios registran sus tablas al importarse
    assert REGISTRY, "ningún servicio registró su tabla (common/state_machine.py)"
    for model, table in REGISTRY.items():
        states = {value for value, _label in model._meta.get_field(table.field).choices}
        label = model._meta.label
        assert set(table.allowed) == states, f"{label}: cada estado es una llave"
        assert table.terminal, f"{label}: declara sus estados finales"
        assert all(not table.allowed[s] for s in table.terminal), (
            f"{label}: un estado final no tiene salida"
        )
        assert all(to in states for exits in table.allowed.values() for to in exits), (
            f"{label}: la tabla lleva a un estado que no existe"
        )


def test_every_status_field_has_a_state_machine():
    """SEC-03.1: un modelo con estado de opciones registra su tabla o su exención."""
    list(_app_modules("services"))
    missing = [
        m._meta.label
        for m in apps.get_models()
        if m.__module__.startswith("apps.")
        and any(
            (f.name == "status" or f.name.endswith("_status")) and f.choices
            for f in m._meta.concrete_fields
        )
        and m not in REGISTRY
        and m._meta.label not in EXEMPT_STATE
    ]
    assert not missing, (
        "registra su tabla de transiciones (common/state_machine.py):\n"
        + "\n".join(missing)
    )
    stale = sorted(label for label in EXEMPT_STATE if apps.get_model(label) in REGISTRY)
    assert not stale, "ya tienen tabla; quítalos de EXEMPT_STATE:\n" + "\n".join(stale)
