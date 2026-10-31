"""Aislamiento por empresa en la base: los proyectos, sus avances y sus evidencias (iteracion-26 #22 · SEC-01).

ENABLE + FORCE ROW LEVEL SECURITY y sus políticas (common/rls.py): cada fila se
ve y se escribe sólo con el contexto de su empresa (``app.company_id``); el
operador de plataforma sólo lee. Sólo en PostgreSQL: en SQLite no hace nada.
"""

from django.db import migrations

from common.rls import IsolateCompanies

POLICIES = {
    "projects_project": "owner_id = NULLIF(current_setting('app.company_id', true), '')::uuid",
    "projects_progress": (
        "EXISTS (SELECT 1 FROM projects_project p "
        "WHERE p.id = projects_progress.project_id AND p.owner_id = NULLIF(current_setting('app.company_id', true), '')::uuid)"
    ),
    "projects_evidence": (
        "EXISTS (SELECT 1 FROM projects_progress g "
        "JOIN projects_project p ON p.id = g.project_id "
        "WHERE g.id = projects_evidence.progress_id AND p.owner_id = NULLIF(current_setting('app.company_id', true), '')::uuid)"
    ),
}


class Migration(migrations.Migration):
    dependencies = [
        ("projects", "0005_project_folio"),
    ]

    operations = [IsolateCompanies(POLICIES)]
