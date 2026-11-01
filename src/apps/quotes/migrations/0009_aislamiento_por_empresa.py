"""Aislamiento por empresa en la base: las cotizaciones, sus partidas y su desglose por habitación (iteracion-26 #22 · SEC-01).

ENABLE + FORCE ROW LEVEL SECURITY y sus políticas (common/rls.py): cada fila se
ve y se escribe sólo con el contexto de su empresa (``app.company_id``); el
operador de plataforma sólo lee. Sólo en PostgreSQL: en SQLite no hace nada.
"""

from django.db import migrations

from common.rls import IsolateCompanies

POLICIES = {
    "quotes_quote": "owner_id = NULLIF(current_setting('app.company_id', true), '')::uuid",
    "quotes_quote_item": (
        "EXISTS (SELECT 1 FROM quotes_quote q "
        "WHERE q.id = quotes_quote_item.quote_id AND q.owner_id = NULLIF(current_setting('app.company_id', true), '')::uuid)"
    ),
    "quotes_quote_item_room": (
        "EXISTS (SELECT 1 FROM quotes_quote_item i "
        "JOIN quotes_quote q ON q.id = i.quote_id "
        "WHERE i.id = quotes_quote_item_room.quote_item_id AND q.owner_id = NULLIF(current_setting('app.company_id', true), '')::uuid)"
    ),
}


class Migration(migrations.Migration):
    dependencies = [
        ("quotes", "0008_desglose_por_habitacion"),
    ]

    operations = [IsolateCompanies(POLICIES)]
