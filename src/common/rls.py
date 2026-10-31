"""Las políticas de RLS por empresa y las tablas que quedan fuera (SEC-01).

Iteracion-26 #22. Cada app con datos de trabajo tiene su migración
``*_aislamiento_por_empresa``: declara sus tablas con la condición que ata cada
fila a la empresa del contexto (``owner_id``, o el ``owner_id`` de su padre), y
``IsolateCompanies`` arma el SQL:

- ``ENABLE`` + ``FORCE ROW LEVEL SECURITY``: con ``FORCE``, el dueño de las
  tablas —el rol de ``DATABASE_URL``, que también migra— queda sujeto.
- ``tenant_isolation``: leer y escribir sólo filas de la empresa del contexto
  (``USING`` y ``WITH CHECK``). Sin contexto, ``NULL``: ninguna fila.
- ``platform_operator_read``: sólo leer, para el operador de plataforma (el
  admin con ``common.tenancy.PLATFORM_OPERATOR_PERM``).

Las hijas comparan el ``owner_id`` de su padre de forma explícita, no «las filas
del padre que veo»: el operador ve todos los padres y, si no, podría escribir
las hijas de cualquier empresa. Sólo en PostgreSQL: en SQLite (la suite local)
las migraciones no hacen nada.

Las migraciones aplicadas dependen de este SQL: no lo cambies. Una política
distinta va en una migración nueva con su propia operación.
"""

from django.db import migrations

#: La empresa del contexto (``set_config('app.company_id', …, true)``). Sin
#: contexto, ``''`` o nada: ``NULL``, y ninguna comparación deja pasar.
COMPANY = "NULLIF(current_setting('app.company_id', true), '')::uuid"
#: El operador de plataforma, que sólo lee.
PLATFORM_OPERATOR = "current_setting('app.platform_operator', true) = 'true'"

#: Las tablas de ``apps/`` que no son de una empresa, con su motivo. Las de
#: Django y las de terceros (sesiones, permisos, la lista negra de tokens, la
#: caché) tampoco: no guardan datos de trabajo.
SHARED_TABLES: dict[str, str] = {
    "account_user": "las cuentas: se leen para autenticar, antes de saber la empresa",
    "account_subscription": "el plan de la cuenta, no de la empresa donde trabaja",
    "account_organization": (
        "el membrete: companies_of lee el nombre de cada empresa donde colabora "
        "la persona, y la API lo pide con account_of"
    ),
    "account_otpcode": "los códigos de la cuenta: se leen antes de haber sesión",
    "team_membership": (
        "account_of la lee para elegir la empresa, antes de que haya contexto"
    ),
    "team_invitation": "el enlace público la lee por su token, sin sesión",
    "legal_acceptance": "las constancias son de la persona, no de una empresa",
    "leads_lead": "el contacto público: no es de ninguna cuenta y lo lee el admin",
}


def enable_statements(table: str, condition: str) -> list[str]:
    return [
        f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY",
        f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY",
        f"CREATE POLICY tenant_isolation ON {table} "
        f"USING ({condition}) WITH CHECK ({condition})",
        f"CREATE POLICY platform_operator_read ON {table} FOR SELECT "
        f"USING ({PLATFORM_OPERATOR})",
    ]


def disable_statements(table: str) -> list[str]:
    return [
        f"DROP POLICY IF EXISTS platform_operator_read ON {table}",
        f"DROP POLICY IF EXISTS tenant_isolation ON {table}",
        f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY",
        f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY",
    ]


class IsolateCompanies(migrations.RunPython):
    """Activa la RLS de esas tablas, cada una con su condición (sólo PostgreSQL)."""

    def __init__(self, policies: dict[str, str]) -> None:
        self.policies = dict(policies)
        super().__init__(self._forwards, self._backwards)

    def deconstruct(self):
        return self.__class__.__qualname__, [self.policies], {}

    def describe(self) -> str:
        return "Aislamiento por empresa (RLS) de " + ", ".join(self.policies)

    def _forwards(self, apps, schema_editor) -> None:
        if schema_editor.connection.vendor != "postgresql":
            return
        for table, condition in self.policies.items():
            for statement in enable_statements(table, condition):
                schema_editor.execute(statement, params=None)

    def _backwards(self, apps, schema_editor) -> None:
        if schema_editor.connection.vendor != "postgresql":
            return
        for table in reversed(list(self.policies)):
            for statement in disable_statements(table):
                schema_editor.execute(statement, params=None)
