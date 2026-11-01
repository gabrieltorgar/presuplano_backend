"""El contexto de empresa de la RLS (SEC-01 · iteracion-26 #22).

La base aísla cada empresa (PostgreSQL, ``ROW LEVEL SECURITY``): una consulta
ve las filas de la empresa que dice ``app.company_id``, y sin contexto ninguna.
Ese contexto vive lo que la transacción de la petición (``SET LOCAL``), así que
se fija dentro de ella, en cuanto DRF sabe quién pide y antes de los permisos y
los límites. Lo que sí se prueba aquí, sin PostgreSQL: la guarda fuera de una
transacción, qué empresa recibe cada petición y que toda vista de la API la
fije. Las políticas mismas se prueban en ``tests/security/test_rls.py`` (CI).
"""

import pytest
from django.core.exceptions import ImproperlyConfigured
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.tests.factories import UserFactory
from apps.team.tests.factories import MembershipFactory
from common.tenancy import set_tenant_context
from tests.platform.routes import api_routes, is_format_twin


def _as(user, company=None) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=user)
    if company is not None:
        client.credentials(HTTP_X_EMPRESA=str(company))
    return client


@pytest.fixture
def context(mocker):
    """Lo que la vista pasa a ``set_tenant_context`` (la función sigue corriendo)."""
    import common.views

    return mocker.spy(common.views, "set_tenant_context")


@pytest.mark.django_db(transaction=True)
def test_set_tenant_context_outside_atomic_raises():
    """SEC-01 · En autocommit el ``SET LOCAL`` moriría antes de la consulta
    siguiente: fuera de una transacción, falla fuerte en vez de no aislar."""
    with pytest.raises(ImproperlyConfigured, match="transacción"):
        set_tenant_context(company_id=UserFactory().pk)


@pytest.mark.django_db
def test_set_tenant_context_inside_a_transaction_does_not_fail():
    """SEC-01 · Dentro de la transacción corre (en SQLite no hay RLS que fijar)."""
    assert set_tenant_context(company_id=None) is None


@pytest.mark.django_db
class TestTheRequestSetsItsCompany:
    """SEC-01 · Cada petición con sesión fija la empresa de ``account_of``."""

    def test_the_own_company_by_default(self, context) -> None:
        admin = UserFactory()

        response = _as(admin).get("/api/clients/")

        assert response.status_code == status.HTTP_200_OK
        context.assert_called_once_with(company_id=admin.pk)

    def test_the_company_chosen_with_x_empresa(self, context) -> None:
        membership = MembershipFactory()

        response = _as(membership.user, membership.account_id).get("/api/clients/")

        assert response.status_code == status.HTTP_200_OK
        context.assert_called_once_with(company_id=membership.account_id)

    def test_a_denied_company_gets_no_rows_and_keeps_its_403(self, context) -> None:
        stranger = UserFactory()

        response = _as(UserFactory(), stranger.pk).get("/api/clients/")

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert response.json()["code"] == "company_access"
        context.assert_called_once_with(company_id=None)

    def test_staff_never_reads_other_companies_through_the_api(self, context) -> None:
        """El operador de plataforma lee entre empresas sólo en el admin."""
        staff = UserFactory(is_staff=True, is_superuser=True)

        _as(staff).get("/api/clients/")

        context.assert_called_once_with(company_id=staff.pk)

    def test_an_anonymous_request_sets_nothing(self, context) -> None:
        response = APIClient().get("/api/clients/")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        context.assert_not_called()


def test_every_api_view_of_apps_sets_the_tenant_context():
    """SEC-01 · Una vista que olvide el contexto vería 0 filas (404) en
    producción: toda vista de ``apps/`` hereda ``TenantContextMixin``."""
    from common.views import TenantContextMixin

    offenders = sorted(
        {
            f"{route.cls.__module__}.{route.cls.__name__}"
            for route in api_routes()
            if not is_format_twin(route)
            and route.cls.__module__.startswith("apps.")
            and not issubclass(route.cls, TenantContextMixin)
        }
    )
    assert not offenders, (
        "hereda de common.views (TenantAPIView, TenantModelViewSet…):\n"
        + "\n".join(offenders)
    )
