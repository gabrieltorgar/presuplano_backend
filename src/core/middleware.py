"""Middleware propio del proyecto."""

from django.conf import settings


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
