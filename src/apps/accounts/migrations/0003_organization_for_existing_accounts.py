"""Give the accounts that predate the letterhead an empty one.

``GET /api/auth/organization/`` creates the row on demand, but ``/auth/me/``
only reports it, so without this the accounts that already existed would read
their letterhead as ``null`` until they opened that screen.
"""

from django.db import migrations


def create_missing_organizations(apps, schema_editor) -> None:
    User = apps.get_model("accounts", "User")
    Organization = apps.get_model("accounts", "Organization")
    missing = User.objects.filter(organization__isnull=True)
    Organization.objects.bulk_create(
        [Organization(user=user) for user in missing.iterator()]
    )


def drop_empty_organizations(apps, schema_editor) -> None:
    Organization = apps.get_model("accounts", "Organization")
    Organization.objects.filter(name="").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0002_organization"),
    ]

    operations = [
        migrations.RunPython(create_missing_organizations, drop_empty_organizations),
    ]
