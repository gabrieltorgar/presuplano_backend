"""El acceso al admin con un tope de intentos fallidos (iteracion-26 #16 · BOT-03.4).

Los límites de DRF no llegan a las vistas de Django, y ésta es la puerta con más
poder: tras ``ADMIN_LOGIN_MAX_FAILURES`` intentos fallidos desde una dirección o
para un usuario, 15 minutos de espera (429 con ``Retry-After``). Los contadores
viven en la caché compartida (la tabla de la base).

El candado por usuario deja que alguien mantenga bloqueada 15 minutos una cuenta
del equipo: se acepta (la cuenta sigue a salvo).
"""

from django.conf import settings
from django.contrib import admin
from django.core.cache import cache
from django.http import HttpResponse
from django.utils.crypto import salted_hmac
from rest_framework.throttling import BaseThrottle

LOCK_SECONDS = 900


def _keys(request) -> list[str]:
    # BaseThrottle respeta NUM_PROXIES (la dirección que agregó el proxy de
    # Vercel); SimpleRateThrottle() fallaría sin alcance.
    ip = BaseThrottle().get_ident(request)
    username = request.POST.get("username", "").strip().lower()
    user_key = salted_hmac("admin-login", username).hexdigest()
    return [f"admin-login:ip:{ip}", f"admin-login:user:{user_key}"]


def admin_login(request, extra_context=None):
    """``admin.site.login``, cerrado 15 minutos tras los intentos fallidos."""
    keys = _keys(request) if request.method == "POST" else []
    if any((cache.get(key) or 0) >= settings.ADMIN_LOGIN_MAX_FAILURES for key in keys):
        return HttpResponse(
            "Demasiados intentos. Espera 15 minutos.",
            status=429,
            headers={"Retry-After": str(LOCK_SECONDS)},
        )
    response = admin.site.login(request, extra_context)
    if keys and not request.user.is_authenticated:
        for key in keys:
            cache.add(key, 0, LOCK_SECONDS)
            cache.incr(key)
    return response
