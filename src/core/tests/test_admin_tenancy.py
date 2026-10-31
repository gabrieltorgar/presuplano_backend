"""El admin con la RLS (SEC-01 · iteracion-26 #22).

El admin entra con la sesión de Django: el usuario se conoce después de
``AuthenticationMiddleware``, y ahí ``AdminTenantContextMiddleware`` abre la
transacción y fija el contexto. Quien entra ve y escribe lo de su propia
empresa; leer las de todas pide el permiso ``accounts.view_all_companies``
(operador de plataforma, se otorga a mano y queda en el admin), nunca ser
staff. Ese permiso sólo lee: las políticas no dejan escribir fuera del
contexto. Lo que hace la base con él se prueba en ``tests/security/test_rls.py``.
"""

import pytest
from django.conf import settings
from django.contrib.auth.models import Permission

from apps.accounts.tests.factories import UserFactory
from common.tenancy import PLATFORM_OPERATOR_PERM


@pytest.fixture
def context(mocker):
    import core.middleware

    return mocker.spy(core.middleware, "set_tenant_context")


def _operator(user):
    app_label, codename = PLATFORM_OPERATOR_PERM.split(".")
    user.user_permissions.add(
        Permission.objects.get(content_type__app_label=app_label, codename=codename)
    )
    return type(user).objects.get(pk=user.pk)  # sin la caché de permisos


def test_the_middleware_runs_after_the_session_is_known():
    """SEC-01 · Antes de AuthenticationMiddleware no hay usuario que poner."""
    middleware = list(settings.MIDDLEWARE)

    assert middleware.index("core.middleware.AdminTenantContextMiddleware") > (
        middleware.index("django.contrib.auth.middleware.AuthenticationMiddleware")
    )


def test_the_operator_permission_is_not_staff():
    """SEC-01 · El permiso de leer entre empresas es explícito y auditado."""
    assert PLATFORM_OPERATOR_PERM == "accounts.view_all_companies"


@pytest.mark.django_db
class TestTheAdminContext:
    def test_staff_works_on_its_own_company(self, client, context) -> None:
        staff = UserFactory(is_staff=True)
        client.force_login(staff)

        response = client.get("/admin/clients/client/")

        assert response.status_code in (200, 403)
        context.assert_called_once_with(company_id=staff.pk, platform_operator=False)

    def test_staff_without_own_company_works_on_none(self, client, context) -> None:
        staff = UserFactory(is_staff=True, has_own_workspace=False)
        client.force_login(staff)

        client.get("/admin/")

        context.assert_called_once_with(company_id=None, platform_operator=False)

    def test_only_the_operator_permission_reads_every_company(
        self, client, context
    ) -> None:
        operator = _operator(UserFactory(is_staff=True))
        client.force_login(operator)

        client.get("/admin/")

        context.assert_called_once_with(company_id=operator.pk, platform_operator=True)

    def test_the_api_and_the_login_page_are_left_alone(self, client, context) -> None:
        """La API fija su contexto en la vista (TenantContextMixin); el login
        del admin no tiene usuario todavía."""
        client.get("/admin/login/")
        client.get("/api/health/")

        context.assert_not_called()
