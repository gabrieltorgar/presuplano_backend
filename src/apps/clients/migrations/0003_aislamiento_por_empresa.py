"""Aislamiento por empresa en la base: los clientes (iteracion-26 #22 · SEC-01).

ENABLE + FORCE ROW LEVEL SECURITY y sus políticas (common/rls.py): cada fila se
ve y se escribe sólo con el contexto de su empresa (``app.company_id``); el
operador de plataforma sólo lee. Sólo en PostgreSQL: en SQLite no hace nada.
"""

from django.db import migrations

from common.rls import IsolateCompanies

POLICIES = {
    "clients_client": "owner_id = NULLIF(current_setting('app.company_id', true), '')::uuid",
}


class Migration(migrations.Migration):
    dependencies = [
        ("clients", "0002_telefonos_e164"),
    ]

    operations = [IsolateCompanies(POLICIES)]
