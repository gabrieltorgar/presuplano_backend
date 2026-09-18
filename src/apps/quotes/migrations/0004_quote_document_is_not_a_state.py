"""«Documento generado» deja de ser un estado de la cotización.

El documento se construye a partir de la cotización cada vez que se pide, así
que una cotización documentada no era otra cosa que un borrador con el papel ya
impreso. Las que están en ese estado vuelven a borrador, que es lo que son, y
así siguen pudiéndose editar hasta que se conviertan en proyecto.
"""

from django.db import migrations, models


def back_to_draft(apps, schema_editor) -> None:
    Quote = apps.get_model("quotes", "Quote")
    Quote.objects.filter(status="document_generated").update(status="draft")


def noop(apps, schema_editor) -> None:
    """Volver atrás no puede adivinar cuáles tenían el papel impreso."""


class Migration(migrations.Migration):
    dependencies = [
        ("quotes", "0003_alter_quoteitem_unit_price"),
    ]

    operations = [
        migrations.RunPython(back_to_draft, noop),
        migrations.AlterField(
            model_name="quote",
            name="status",
            field=models.CharField(
                choices=[("draft", "Borrador"), ("in_project", "En proyecto")],
                default="draft",
                max_length=20,
                verbose_name="estado",
            ),
        ),
    ]
