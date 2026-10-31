"""El permiso por omisión de la API: sesión y correo verificado (iteracion-26 #8).

Una cuenta recién registrada ya tiene sesión (#12), pero hasta escribir su
código sólo alcanza lo que necesita para verificarse: saber quién es
(``GET /api/auth/me/``), el código y su reenvío, renovar, salir y la cookie
CSRF. Esas vistas declaran ``IsAuthenticated`` o ``AllowAny`` con su motivo;
todas las demás usan ``IsVerifiedUser``, también las que declaran sus propios
permisos (una lista en la vista reemplaza la de omisión).
"""

from rest_framework.permissions import IsAuthenticated

#: El ``code`` del 403: la SPA lo reconoce y lleva a la pantalla del código.
EMAIL_NOT_VERIFIED = "email_not_verified"


class IsVerifiedUser(IsAuthenticated):
    """Con sesión y con el correo verificado. Sin sesión, 401; sin verificar, 403."""

    message = {
        "detail": "Verifica tu correo para continuar.",
        "code": EMAIL_NOT_VERIFIED,
    }
    code = EMAIL_NOT_VERIFIED

    def has_permission(self, request, view) -> bool:
        return super().has_permission(request, view) and bool(
            getattr(request.user, "is_email_verified", False)
        )
