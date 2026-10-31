"""Content-Security-Policy: estricta en la API; el admin tiene la suya (SRV-01).

iteracion-26 #18, receta de django-backend-conventions (libraries.md §csp, con
django-csp 4). La API sirve sólo JSON en producción (DEFAULT_RENDERER_CLASSES):
no hay nada que cargar ni nadie que deba enmarcarla. El admin de Unfold y, con
DEBUG, la API navegable son páginas: ``core.middleware.AdminCSPMiddleware`` les
pone ``ADMIN_CSP`` en lugar de la de la API. Aplicada, nunca sólo Report-Only.
"""

from csp.constants import NONE, SELF, UNSAFE_EVAL, UNSAFE_INLINE

from .settings_storages import MEDIA_ORIGINS

CONTENT_SECURITY_POLICY = {
    "DIRECTIVES": {
        "default-src": [NONE],
        "frame-ancestors": [NONE],
        "base-uri": [NONE],
        "form-action": [SELF],
    }
}

ADMIN_URL_PREFIX = "/admin/"
# Unfold trae Alpine en su versión estándar (new Function) → 'unsafe-eval', y pone
# estilos en línea (style-src 'unsafe-inline'); scripts en línea, nunca. Revisar
# unfoldadmin/django-unfold#2129 en cada actualización de Unfold. Las imágenes:
# las del admin y la vista previa de logotipos y fotos, que salen del bucket.
ADMIN_CSP = {
    "default-src": [SELF],
    "script-src": [SELF, UNSAFE_EVAL],
    "style-src": [SELF, UNSAFE_INLINE],
    "img-src": [SELF, "data:", *MEDIA_ORIGINS],
    "font-src": [SELF, "data:"],
    "connect-src": [SELF],
    "object-src": [NONE],
    "base-uri": [SELF],
    "frame-ancestors": [NONE],
    "form-action": [SELF],
}
