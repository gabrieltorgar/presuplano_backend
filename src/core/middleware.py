"""Middleware propio del proyecto."""

from django.conf import settings
from django.db import transaction

from common.tenancy import PLATFORM_OPERATOR_PERM, set_tenant_context


class AdminCSPMiddleware:
    """La política del admin (``ADMIN_CSP``) en lugar de la de la API (SRV-01).

    Va justo después de ``csp.middleware.CSPMiddleware`` en ``MIDDLEWARE``: su
    fase de respuesta corre antes y deja ``response._csp_replace``, que
    django-csp lee al escribir la cabecera. Bajo ``/admin/`` siempre; con DEBUG,
    también en el HTML de la API navegable (iteracion-26 #18).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        is_html = "text/html" in response.get("Content-Type", "")
        if request.path.startswith(settings.ADMIN_URL_PREFIX) or (
            settings.DEBUG and is_html
        ):
            response._csp_replace = settings.ADMIN_CSP
        return response


class AdminTenantContextMiddleware:
    """La empresa de la RLS en el admin (SEC-01 · iteracion-26 #22).

    Va justo después de ``AuthenticationMiddleware``: el admin entra con la
    sesión de Django, así que aquí ya se sabe quién es. Abre la transacción, fija
    el contexto y la vista corre dentro (su propia transacción de
    ``ATOMIC_REQUESTS`` se vuelve un savepoint; el ``SET LOCAL`` dura hasta este
    commit). Una vista que falla revierte su savepoint antes de volverse 500.

    Quien entra ve y escribe lo de su empresa propia (sin una, nada). Con
    ``PLATFORM_OPERATOR_PERM`` lee además las de todas, sin escribirlas: las
    políticas no dejan escribir fuera de la empresa del contexto. Ser staff no
    da ese permiso.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if not (
            request.path.startswith(settings.ADMIN_URL_PREFIX)
            and user is not None
            and user.is_authenticated
        ):
            return self.get_response(request)
        with transaction.atomic():
            set_tenant_context(
                company_id=user.pk if user.has_own_workspace else None,
                platform_operator=user.has_perm(PLATFORM_OPERATOR_PERM),
            )
            return self.get_response(request)
