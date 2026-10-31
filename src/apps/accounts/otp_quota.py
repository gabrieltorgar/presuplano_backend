"""Espera y tope por hora del código de un solo uso (iteracion-26 #14 · CRD-04.2).

Por destino (el correo normalizado) y propósito, y antes de buscar la cuenta: un
correo que existe y uno que no esperan lo mismo, y nadie llena un buzón ajeno
pidiendo códigos. Exacta (``cache.add`` + ``cache.incr`` en la caché compartida),
a diferencia de los throttles de DRF, que son la segunda capa.
"""

import time

from django.conf import settings
from django.core.cache import cache
from django.utils.crypto import salted_hmac

#: Lo que dura la ventana del tope por hora.
HOUR = 3600


class OTPCooldown(Exception):
    """Muy pronto, o demasiados códigos para ese destino y propósito.

    ``wait`` son los segundos hasta el siguiente: ``api_exception_handler`` lo
    responde como 429 con ``Retry-After``.
    """

    def __init__(self, wait: int) -> None:
        super().__init__(wait)
        self.wait = wait


def check_request_quota(*, email: str, purpose: str) -> None:
    """Cuenta un envío para ese destino y propósito, o dice cuánto esperar.

    Raises:
        OTPCooldown: dentro de ``OTP_RESEND_COOLDOWN_SECONDS`` del anterior, o
            pasado ``OTP_MAX_CODES_PER_HOUR`` en la hora.
    """
    key = salted_hmac(
        "apps.accounts.otp-quota", f"{purpose}:{email.strip().lower()}"
    ).hexdigest()
    cooldown, now = settings.OTP_RESEND_COOLDOWN_SECONDS, int(time.time())
    if not cache.add(f"otp:cd:{key}", now, cooldown):
        started = int(cache.get(f"otp:cd:{key}", now))
        raise OTPCooldown(wait=max(1, cooldown - (now - started)))
    cache.add(f"otp:h:{key}", 0, HOUR)
    if cache.incr(f"otp:h:{key}") > settings.OTP_MAX_CODES_PER_HOUR:
        raise OTPCooldown(wait=HOUR)
