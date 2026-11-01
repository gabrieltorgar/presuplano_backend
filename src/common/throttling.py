"""Límite por cuenta (iteracion-26 #16 · BOT-03, CRD-04): por el correo enviado.

Rotar la dirección no reinicia el contador, y el buzón de alguien no se llena de
códigos ni se prueba su contraseña desde muchas direcciones. Sólo aplica a las
vistas que declaran ``identifier_throttle_scope``; su tasa vive en
``DEFAULT_THROTTLE_RATES`` como la de cualquier alcance.
"""

from django.utils.crypto import salted_hmac
from rest_framework.throttling import SimpleRateThrottle


class IdentifierRateThrottle(SimpleRateThrottle):
    """El alcance ``identifier_throttle_scope`` de la vista, por correo normalizado."""

    scope_attr = "identifier_throttle_scope"

    def __init__(self) -> None:
        # Como ScopedRateThrottle: la tasa se resuelve por vista en allow_request.
        pass

    def allow_request(self, request, view) -> bool:
        self.scope = getattr(view, self.scope_attr, None)
        if not self.scope:
            return True
        self.rate = self.get_rate()
        self.num_requests, self.duration = self.parse_rate(self.rate)
        return super().allow_request(request, view)

    def get_cache_key(self, request, view) -> str | None:
        data = request.data if isinstance(request.data, dict) else {}
        # «identifier»: el nombre del campo en las pantallas de cuando se entraba
        # con teléfono; la API lo sigue aceptando como el correo.
        email = str(data.get("email") or data.get("identifier") or "").strip().lower()
        if not email and request.user.is_authenticated:
            email = request.user.email.lower()
        if not email:
            return None
        ident = salted_hmac(
            "throttle", f"{data.get('purpose', '')}:{email}", algorithm="sha256"
        ).hexdigest()
        return self.cache_format % {"scope": self.scope, "ident": ident}
