"""El correo pasa a ser la única forma de entrar; el teléfono, de la organización.

Antes de exigir el correo, cualquier cuenta que hubiera entrado sólo con
teléfono recibe uno de relleno que no existe (``.invalid`` no se resuelve
nunca), para que la columna pueda volverse obligatoria sin perder la cuenta.
"""

from django.db import migrations, models


def give_every_account_an_email(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    for user in User.objects.filter(models.Q(email__isnull=True) | models.Q(email="")):
        user.email = f"sin-correo-{user.pk}@presuplano.invalid"
        user.save(update_fields=["email"])


class Migration(migrations.Migration):
    dependencies = [
        (
            "accounts",
            "0005_user_email_user_is_email_verified_alter_user_phone_and_more",
        ),
    ]

    operations = [
        migrations.RunPython(give_every_account_an_email, migrations.RunPython.noop),
        migrations.RemoveField(model_name="user", name="phone"),
        migrations.RemoveField(model_name="user", name="is_phone_verified"),
        migrations.AlterField(
            model_name="user",
            name="email",
            field=models.EmailField(
                db_index=True, max_length=254, unique=True, verbose_name="correo"
            ),
        ),
        migrations.AddField(
            model_name="organization",
            name="email",
            field=models.EmailField(
                blank=True,
                default="",
                help_text="Sale en los documentos; vacío no sale nada.",
                max_length=254,
                verbose_name="correo de contacto",
            ),
        ),
        migrations.AddField(
            model_name="organization",
            name="phone",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Sale en los documentos; vacío no sale nada.",
                max_length=30,
                verbose_name="teléfono de contacto",
            ),
        ),
    ]
