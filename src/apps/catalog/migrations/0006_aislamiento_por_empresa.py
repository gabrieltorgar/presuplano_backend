"""Aislamiento por empresa en la base: las tarifas (iteracion-26 #22 · SEC-01).

ENABLE + FORCE ROW LEVEL SECURITY y sus políticas (common/rls.py): cada fila se
ve y se escribe sólo con el contexto de su empresa (``app.company_id``); el
operador de plataforma sólo lee. Sólo en PostgreSQL: en SQLite no hace nada.
"""

from django.db import migrations

from common.rls import IsolateCompanies

POLICIES = {
    "catalog_tariff": "owner_id = NULLIF(current_setting('app.company_id', true), '')::uuid",
}


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0005_unidad_por_lote"),
    ]

    operations = [IsolateCompanies(POLICIES)]
