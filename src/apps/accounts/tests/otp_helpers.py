"""Ayudas de las pruebas del código de un solo uso (iteracion-26 #13–#15).

El código se lee de lo que sale por correo, nunca de la base: ahí sólo vive su
HMAC.
"""


def code_of(otp_sent) -> str:
    """El código que llevó el último correo."""
    return otp_sent.call_args.kwargs["code"]


def wrong(code: str) -> str:
    """Un código de seis dígitos que no es ``code``."""
    return f"{(int(code) + 1) % 1_000_000:06d}"
