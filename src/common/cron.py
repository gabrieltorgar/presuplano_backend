"""Las tareas programadas de Vercel: un secreto, no una sesión (iteracion-26 #11).

El cron de Vercel llama a su ruta con ``Authorization: Bearer <CRON_SECRET>``
(la variable del proyecto). Sólo ese secreto la abre, comparado en tiempo
constante; sin ``CRON_SECRET`` configurado no la abre nadie (401) y la tarea
nunca corre. Una cookie de sesión, por válida que sea, no cuenta.
"""

import secrets

from django.conf import settings
from rest_framework import exceptions
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.permissions import IsAuthenticated


class CronJob:
    """Quien llama con el secreto del cron. No es una cuenta: no alcanza otra ruta."""

    pk = "cron"
    is_authenticated = True
    is_anonymous = False


class CronSecretAuthentication(BaseAuthentication):
    """``Authorization: Bearer <CRON_SECRET>``; sin cabecera Bearer, nadie (401)."""

    def authenticate(self, request):
        parts = get_authorization_header(request).split()
        if not parts or parts[0].lower() != b"bearer":
            return None
        expected = settings.CRON_SECRET.encode()
        if (
            not expected
            or len(parts) != 2
            or not secrets.compare_digest(parts[1], expected)
        ):
            raise exceptions.AuthenticationFailed("El secreto del cron no es válido.")
        return CronJob(), None

    def authenticate_header(self, request) -> str:
        # Con cabecera de autenticación DRF responde 401 (no 403) sin el secreto.
        return 'Bearer realm="cron"'


class IsCronJob(IsAuthenticated):
    """Sólo el cron. Hereda de IsAuthenticated: sin el secreto, 401."""

    def has_permission(self, request, view) -> bool:
        return super().has_permission(request, view) and isinstance(
            request.user, CronJob
        )
