"""Qué tablas aísla la RLS, cuáles no y por qué (SEC-01 · iteracion-26 #22).

Cada tabla de ``apps/`` está en una de dos listas: las que aíslan sus
migraciones ``*_aislamiento_por_empresa`` (``IsolateCompanies``) o
``common.rls.SHARED_TABLES``, con su motivo. Un modelo nuevo que no esté en
ninguna deja esto en rojo: decide si es de una empresa. Las migraciones sólo
actúan en PostgreSQL —la suite local corre en SQLite—, y lo que hace la base
con ellas se prueba en ``tests/security/test_rls.py`` (CI, PostgreSQL 16).
"""

import re
from types import SimpleNamespace

import pytest
from django.apps import apps
from django.conf import settings
from django.db.migrations.loader import MigrationLoader

from common.rls import (
    COMPANY,
    PLATFORM_OPERATOR,
    SHARED_TABLES,
    IsolateCompanies,
)


def isolations() -> list[IsolateCompanies]:
    loader = MigrationLoader(None, ignore_no_migrations=True)
    return [
        operation
        for migration in loader.disk_migrations.values()
        for operation in migration.operations
        if isinstance(operation, IsolateCompanies)
    ]


def isolated_tables() -> dict[str, str]:
    return {
        table: condition
        for operation in isolations()
        for table, condition in operation.policies.items()
    }


def project_tables() -> dict[str, type]:
    return {
        model._meta.db_table: model
        for model in apps.get_models()
        if model.__module__.startswith("apps.")
    }


class _Recorder:
    """Un ``schema_editor`` de mentira: anota lo que se le manda ejecutar."""

    def __init__(self, vendor: str) -> None:
        self.connection = SimpleNamespace(vendor=vendor)
        self.statements: list[str] = []

    def execute(self, sql, params=()) -> None:
        self.statements.append(sql)


def test_every_project_table_is_isolated_or_shared_with_its_reason():
    """SEC-01 · Ninguna tabla queda sin decidir."""
    isolated, tables = set(isolated_tables()), set(project_tables())

    assert not isolated & set(SHARED_TABLES), "una tabla no puede estar en las dos"
    assert not tables - isolated - set(SHARED_TABLES), (
        "aíslala en una migración IsolateCompanies o anótala en SHARED_TABLES"
    )
    assert not (isolated | set(SHARED_TABLES)) - tables, "tablas que ya no existen"
    assert all(reason.strip() for reason in SHARED_TABLES.values())


def test_every_table_with_an_owner_is_isolated():
    """SEC-01 · Lo que cuelga de una cuenta dueña (``owner``) es de una empresa."""
    owned = {
        table
        for table, model in project_tables().items()
        for field in model._meta.concrete_fields
        if field.name == "owner"
        and field.is_relation
        and field.related_model._meta.label == settings.AUTH_USER_MODEL
    }

    assert owned, "¿cambió el nombre del dueño?"
    assert owned <= set(isolated_tables())


def test_every_policy_ties_rows_to_the_company_of_the_context():
    """SEC-01 · Por la empresa del contexto (nunca por ``is_staff``); sin
    contexto, ``NULL`` y ninguna fila."""
    for table, condition in isolated_tables().items():
        assert re.fullmatch(r"[a-z_]+", table)
        assert COMPANY in condition, table
        assert "is_staff" not in condition, table
    assert "NULLIF" in COMPANY and "app.company_id" in COMPANY


def test_the_migrations_only_act_on_postgresql():
    """Sin PostgreSQL local: en SQLite no ejecutan nada (la suite migra igual)."""
    for operation in isolations():
        sqlite = _Recorder("sqlite")

        operation.code(apps, sqlite)
        operation.reverse_code(apps, sqlite)

        assert sqlite.statements == []


@pytest.mark.parametrize(
    "operation", isolations(), ids=lambda op: next(iter(op.policies))
)
def test_each_table_gets_rls_forced_and_both_policies(operation):
    """SEC-01 · ``FORCE``: el dueño de las tablas (el rol de ``DATABASE_URL``)
    queda sujeto también. La del operador sólo lee (``FOR SELECT``)."""
    postgres = _Recorder("postgresql")

    operation.code(apps, postgres)

    for table, condition in operation.policies.items():
        assert f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY" in postgres.statements
        assert f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY" in postgres.statements
        assert (
            f"CREATE POLICY tenant_isolation ON {table} "
            f"USING ({condition}) WITH CHECK ({condition})"
        ) in postgres.statements
        assert (
            f"CREATE POLICY platform_operator_read ON {table} FOR SELECT "
            f"USING ({PLATFORM_OPERATOR})"
        ) in postgres.statements


@pytest.mark.parametrize(
    "operation", isolations(), ids=lambda op: next(iter(op.policies))
)
def test_each_migration_undoes_what_it_did(operation):
    postgres = _Recorder("postgresql")

    operation.reverse_code(apps, postgres)

    for table in operation.policies:
        assert f"DROP POLICY IF EXISTS tenant_isolation ON {table}" in (
            postgres.statements
        )
        assert f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY" in (
            postgres.statements
        )
        assert f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY" in (
            postgres.statements
        )
