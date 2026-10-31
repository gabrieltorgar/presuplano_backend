"""Aislamiento por empresa en la base: el personal, sus servicios, el reparto y sus pagos (iteracion-26 #22 · SEC-01).

ENABLE + FORCE ROW LEVEL SECURITY y sus políticas (common/rls.py): cada fila se
ve y se escribe sólo con el contexto de su empresa (``app.company_id``); el
operador de plataforma sólo lee. Sólo en PostgreSQL: en SQLite no hace nada.
"""

from django.db import migrations

from common.rls import IsolateCompanies

POLICIES = {
    "staff_worker": "owner_id = NULLIF(current_setting('app.company_id', true), '')::uuid",
    "staff_workerservice": (
        "EXISTS (SELECT 1 FROM staff_worker w "
        "WHERE w.id = staff_workerservice.worker_id AND w.owner_id = NULLIF(current_setting('app.company_id', true), '')::uuid)"
    ),
    "staff_assignment": (
        "EXISTS (SELECT 1 FROM projects_project p "
        "WHERE p.id = staff_assignment.project_id AND p.owner_id = NULLIF(current_setting('app.company_id', true), '')::uuid)"
    ),
    "staff_workerpayment": "owner_id = NULLIF(current_setting('app.company_id', true), '')::uuid",
}


class Migration(migrations.Migration):
    dependencies = [
        ("staff", "0003_workerpayment_folio"),
    ]

    operations = [IsolateCompanies(POLICIES)]
