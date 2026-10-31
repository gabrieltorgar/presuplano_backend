"""La RLS por empresa en PostgreSQL, con un rol sin BYPASSRLS (SEC-01 · SEC-01.1).

Iteracion-26 #22. Corren en el quality gate de CI (``postgres:16``), con las
migraciones de verdad. El usuario de CI es superusuario y se saltaría las
políticas aun con ``FORCE``: cada prueba cambia, dentro de su transacción, a
``app_rls`` (``NOSUPERUSER NOBYPASSRLS``, como el rol de ``DATABASE_URL`` en
Neon). Las filas se crean antes, como superusuario. En SQLite —sin PostgreSQL
local— se saltan con su motivo; lo que no necesita la base (la guarda fuera de
una transacción, el registro de tablas, que toda vista fije el contexto) corre
en ``common/tests/test_tenancy.py`` y ``test_rls_tables.py``.
"""

from contextlib import contextmanager

import pytest
from django.apps import apps
from django.contrib.auth.models import Permission
from django.core.management import call_command
from django.db import DatabaseError, connection, transaction
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.deletion import purge_account
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.test_delete_account import full_account, owned_rows
from apps.clients.models import Client
from apps.clients.tests.factories import ClientFactory
from apps.quotes.models import Quote, QuoteItem
from apps.team.tests.factories import MembershipFactory
from common.tenancy import PLATFORM_OPERATOR_PERM, set_tenant_context
from common.tests.test_rls_tables import isolated_tables

pytestmark = [
    pytest.mark.rls,
    pytest.mark.skipif(
        connection.vendor != "postgresql",
        reason=(
            "RLS solo existe en PostgreSQL: corre en CI (quality-gate con postgres:16)"
        ),
    ),
]

TABLES = sorted(isolated_tables())

#: Por dónde llega cada tabla a su empresa (las demás, por ``owner``).
OWNER_PATHS = {
    "projects_progress": "project__owner",
    "projects_evidence": "progress__project__owner",
    "quotes_quote_item": "quote__owner",
    "quotes_quote_item_room": "quote_item__quote__owner",
    "staff_workerservice": "worker__owner",
    "staff_assignment": "project__owner",
}
MODELS = {
    model._meta.db_table: model
    for model in apps.get_models()
    if model._meta.db_table in TABLES
}


def owner_path(table: str) -> str:
    return OWNER_PATHS.get(table, "owner")


@contextmanager
def as_app_role(company=None, *, operator: bool = False):
    """Dentro de una transacción, como ``app_rls``, con ese contexto o sin él."""
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute("SET LOCAL ROLE app_rls")
        if company is not None or operator:
            set_tenant_context(
                company_id=getattr(company, "pk", None), platform_operator=operator
            )
        try:
            yield cursor
        finally:
            cursor.execute("RESET ROLE")


@contextmanager
def app_role_session():
    """Como ``app_rls`` toda la sesión: las peticiones abren su transacción."""
    with connection.cursor() as cursor:
        cursor.execute("SET ROLE app_rls")
    try:
        yield
    finally:
        with connection.cursor() as cursor:
            cursor.execute("RESET ROLE")


def grant(user, *perms: str):
    for perm in perms:
        app_label, codename = perm.split(".")
        user.user_permissions.add(
            Permission.objects.get(content_type__app_label=app_label, codename=codename)
        )


@pytest.fixture
def media(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    # Aquí no se prueba la contraseña: un hash rápido.
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
    return tmp_path


@pytest.fixture
def two_companies(db, media):
    a, b = UserFactory(), UserFactory()
    full_account(a)
    full_account(b)
    return a, b


@pytest.mark.django_db
def test_rls_role_cannot_bypass(app_rls_role):
    """SEC-01.1 · Un rol con BYPASSRLS o superusuario haría pasar todo."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = %s",
            [app_rls_role],
        )
        assert cursor.fetchone() == (False, False)


def test_the_registry_is_not_empty():
    """SEC-01 · Un registro vacío haría pasar la siguiente sin probar nada."""
    assert len(TABLES) >= 20 and set(TABLES) == set(MODELS)


@pytest.mark.django_db
@pytest.mark.parametrize("table", TABLES)
def test_every_tenant_table_has_rls_forced_and_its_policies(table):
    """SEC-01 · ``FORCE``: el dueño de las tablas también queda sujeto."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
            "WHERE relname = %s AND relkind = 'r'",
            [table],
        )
        assert cursor.fetchone() == (True, True)
        cursor.execute(
            "SELECT policyname, cmd FROM pg_policies WHERE tablename = %s "
            "ORDER BY policyname",
            [table],
        )
        assert cursor.fetchall() == [
            ("platform_operator_read", "SELECT"),
            ("tenant_isolation", "ALL"),
        ]


def test_without_a_company_context_no_row_is_seen(app_rls_role, two_companies):
    """SEC-01 · Lo que vería una consulta que olvidó el contexto: nada."""
    stored = {table: model.objects.count() for table, model in MODELS.items()}

    with as_app_role():
        seen = {table: model.objects.count() for table, model in MODELS.items()}

    assert sum(1 for rows in stored.values() if rows) >= 10
    assert seen == dict.fromkeys(MODELS, 0)


def test_each_company_sees_exactly_its_own_rows(app_rls_role, two_companies):
    """SEC-01 · La empresa A no ve nada de B, tampoco en las tablas hijas."""
    a, _b = two_companies
    expected = {
        table: model.objects.filter(**{owner_path(table): a}).count()
        for table, model in MODELS.items()
    }

    with as_app_role(a):
        seen = {table: model.objects.count() for table, model in MODELS.items()}
        owners = {
            table: set(model.objects.values_list(owner_path(table), flat=True))
            for table, model in MODELS.items()
        }

    assert seen == expected
    assert all(found <= {a.pk} for found in owners.values()), owners


def test_a_company_cannot_write_another_companys_rows(app_rls_role, two_companies):
    """SEC-01 · Ni cambiar, ni borrar, ni crear filas a nombre de otra empresa."""
    a, b = two_companies
    theirs = Client.objects.filter(owner=b).first()
    their_quote = Quote.objects.filter(owner=b).first()
    their_item = QuoteItem.objects.filter(quote=their_quote).first()

    with as_app_role(a):
        assert Client.objects.filter(pk=theirs.pk).update(name="Ajeno") == 0
        assert Client.objects.filter(pk=theirs.pk).delete()[0] == 0
        with pytest.raises(DatabaseError), transaction.atomic():
            Client.objects.create(owner=b, name="Colado")
        with pytest.raises(DatabaseError), transaction.atomic():
            QuoteItem.objects.create(
                quote=their_quote,
                tariff_id=their_item.tariff_id,
                name="Colada",
                unit_type=their_item.unit_type,
                unit_price=1,
                quantity=1,
            )

    theirs.refresh_from_db()
    assert theirs.name != "Ajeno"
    assert not QuoteItem.objects.filter(name="Colada").exists()


def test_the_platform_operator_reads_every_company_and_writes_none(
    app_rls_role, two_companies
):
    """SEC-01 · ``app.platform_operator`` sólo lee (nunca sale de ``is_staff``)."""
    _a, b = two_companies
    stored = Client.objects.count()

    with as_app_role(operator=True):
        seen = Client.objects.count()
        changed = Client.objects.filter(owner=b).update(name="Operador")

    assert seen == stored and stored >= 2
    assert changed == 0


@pytest.mark.django_db(transaction=True)
def test_through_the_api_a_company_sees_and_touches_only_its_rows(app_rls_role):
    """SEC-01 · El camino de la petición: el contexto vive en su transacción
    (``ATOMIC_REQUESTS``), lo fija ``TenantContextMixin`` tras autenticar y una
    consulta sin él no ve nada."""
    a, b = UserFactory(), UserFactory()
    mine = ClientFactory(owner=a, name="Cliente propio")
    theirs = ClientFactory(owner=b, name="Cliente ajeno")
    as_a = APIClient()
    as_a.force_authenticate(user=a)
    in_b = APIClient()
    in_b.force_authenticate(user=MembershipFactory(account=b).user)
    in_b.credentials(HTTP_X_EMPRESA=str(b.pk))

    with app_role_session():
        listing = as_a.get("/api/clients/")
        detail = as_a.get(f"/api/clients/{theirs.pk}/")
        edit = as_a.patch(
            f"/api/clients/{theirs.pk}/", {"name": "Hackeado"}, format="json"
        )
        delete = as_a.delete(f"/api/clients/{theirs.pk}/")
        in_company_b = in_b.get("/api/clients/")
        with transaction.atomic():
            without_context = Client.objects.count()

    assert listing.status_code == status.HTTP_200_OK
    assert [row["id"] for row in listing.json()["results"]] == [str(mine.pk)]
    assert detail.status_code == status.HTTP_404_NOT_FOUND
    assert edit.status_code == status.HTTP_404_NOT_FOUND
    assert delete.status_code == status.HTTP_404_NOT_FOUND
    assert [row["id"] for row in in_company_b.json()["results"]] == [str(theirs.pk)]
    assert without_context == 0
    theirs.refresh_from_db()
    assert theirs.name == "Cliente ajeno"


@pytest.mark.django_db(transaction=True)
def test_in_the_admin_staff_reads_its_company_and_the_operator_all(
    app_rls_role, client
):
    """SEC-01 · El admin con la misma regla: ser staff no abre otras empresas;
    el permiso auditado de operador, sí (para leer)."""
    staff = UserFactory(is_staff=True)
    grant(staff, "clients.view_client")
    operator = UserFactory(is_staff=True, has_own_workspace=False)
    grant(operator, "clients.view_client", PLATFORM_OPERATOR_PERM)
    ClientFactory(owner=staff, name="Cliente propio")
    ClientFactory(owner=UserFactory(), name="Cliente ajeno")

    client.force_login(staff)
    with app_role_session():
        own = client.get("/admin/clients/client/").content.decode()
    client.force_login(operator)
    with app_role_session():
        every = client.get("/admin/clients/client/").content.decode()

    assert "Cliente propio" in own and "Cliente ajeno" not in own
    assert "Cliente propio" in every and "Cliente ajeno" in every


def test_the_account_is_purged_with_its_own_context(app_rls_role, two_companies):
    """SEC-01 · Quien borra su cuenta trabajando en otra empresa se lleva lo
    suyo, y lo de la otra empresa se queda."""
    a, b = two_companies
    MembershipFactory(user=a, account=b)
    a_id, before_b = a.pk, owned_rows(b.pk)

    with as_app_role(b):
        purge_account(user=a)

    assert owned_rows(a_id) == dict.fromkeys(before_b, 0)
    assert owned_rows(b.pk) == before_b


@pytest.mark.django_db
def test_the_token_cron_needs_no_company(app_rls_role):
    """SEC-01 · El cron borra sesiones vencidas: tablas de la plataforma, sin RLS."""
    with as_app_role():
        call_command("flushexpiredtokens")
