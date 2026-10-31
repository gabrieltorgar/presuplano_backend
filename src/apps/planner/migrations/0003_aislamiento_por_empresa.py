"""Aislamiento por empresa en la base: los planos y sus fotos convertidas (iteracion-26 #22 · SEC-01).

ENABLE + FORCE ROW LEVEL SECURITY y sus políticas (common/rls.py): cada fila se
ve y se escribe sólo con el contexto de su empresa (``app.company_id``); el
operador de plataforma sólo lee. Sólo en PostgreSQL: en SQLite no hace nada.
"""

from django.db import migrations

from common.rls import IsolateCompanies

POLICIES = {
    "planner_plan": "owner_id = NULLIF(current_setting('app.company_id', true), '')::uuid",
    "planner_photo_conversion": "owner_id = NULLIF(current_setting('app.company_id', true), '')::uuid",
}


class Migration(migrations.Migration):
    dependencies = [
        ("planner", "0002_photo_conversion"),
    ]

    operations = [IsolateCompanies(POLICIES)]
