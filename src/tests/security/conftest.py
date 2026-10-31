"""Fixtures de las pruebas de seguridad por criterio (qa-tdd-testing).

``rls`` marca las que prueban la RLS en PostgreSQL (SEC-01 · iteracion-26 #22).
Se registra aquí y no en ``pyproject.toml`` (configuración del gate). Corren en
el quality gate de CI (``postgres:16``); en SQLite se saltan con su motivo.
"""

import pytest
from django.db import connection

#: El rol de la prueba: como el de ``DATABASE_URL`` en Neon, sin superusuario
#: ni BYPASSRLS. El ``postgres`` de CI es superusuario y se saltaría las
#: políticas: cada prueba cambia a éste dentro de su transacción.
APP_ROLE = "app_rls"


def pytest_configure(config) -> None:
    config.addinivalue_line(
        "markers",
        "rls: RLS en PostgreSQL con un rol sin BYPASSRLS (SEC-01); corre en CI",
    )


@pytest.fixture(scope="session")
def app_rls_role(django_db_setup, django_db_blocker) -> str:
    """``app_rls`` (``NOLOGIN NOSUPERUSER NOBYPASSRLS``) con los permisos de la app."""
    with django_db_blocker.unblock(), connection.cursor() as cursor:
        cursor.execute(
            "DO $$ BEGIN "
            "IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_rls') THEN "
            "CREATE ROLE app_rls NOLOGIN NOSUPERUSER NOBYPASSRLS; "
            "END IF; END $$"
        )
        cursor.execute("GRANT USAGE ON SCHEMA public TO app_rls")
        cursor.execute(
            "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public "
            "TO app_rls"
        )
        cursor.execute(
            "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO app_rls"
        )
    return APP_ROLE
