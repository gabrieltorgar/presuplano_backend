"""Las bases de toda vista de la API: cada una fija la empresa de la RLS.

DRF autentica dentro de la vista, ya en la transacción de la petición
(``ATOMIC_REQUESTS``): ahí, en cuanto se sabe quién pide y antes de los permisos
y los límites, ``TenantContextMixin`` pone la empresa de ``account_of``. Una
vista que no la ponga ve cero filas de las tablas de trabajo (y responde 404),
así que toda vista de ``apps/`` hereda de una de estas bases (SEC-01 ·
iteracion-26 #22; lo exige ``common/tests/test_tenancy.py``).

La API nunca lee entre empresas: el operador de plataforma lo hace sólo en el
admin (``core.middleware.AdminTenantContextMiddleware``).
"""

from rest_framework import viewsets
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.team.tenancy import CompanyAccessDenied, account_of
from common.tenancy import set_tenant_context


class TenantContextMixin:
    """Fija la empresa de la petición justo después de autenticarla."""

    def perform_authentication(self, request) -> None:
        super().perform_authentication(request)
        if not isinstance(request.user, User):  # sin sesión, o el cron
            return
        try:
            company = account_of(request)
        except CompanyAccessDenied:
            # Sin empresa no ve nada; la vista responde su 403 al pedirla.
            company = None
        set_tenant_context(company_id=company.pk if company else None)


class TenantAPIView(TenantContextMixin, APIView):
    """``APIView`` con el contexto de la empresa."""


class TenantViewSet(TenantContextMixin, viewsets.ViewSet):
    """``ViewSet`` con el contexto de la empresa."""


class TenantGenericViewSet(TenantContextMixin, viewsets.GenericViewSet):
    """``GenericViewSet`` con el contexto de la empresa."""


class TenantReadOnlyModelViewSet(TenantContextMixin, viewsets.ReadOnlyModelViewSet):
    """``ReadOnlyModelViewSet`` con el contexto de la empresa."""


class TenantModelViewSet(TenantContextMixin, viewsets.ModelViewSet):
    """``ModelViewSet`` con el contexto de la empresa."""
