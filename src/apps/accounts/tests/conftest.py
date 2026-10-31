"""Fixtures de las pruebas de cuentas y del código de un solo uso."""

import pytest
from django.db import connections


@pytest.fixture
def otp_sent(settings, mocker):
    """El correo configurado y el envío del código interceptado (la frontera)."""
    settings.RESEND_API_KEY = "re_test"
    return mocker.patch("apps.accounts.services.send_otp_email", return_value=True)


@pytest.fixture
def atomic_requests(monkeypatch):
    """Cada petición en su transacción, como con ``ATOMIC_REQUESTS = True`` (#22).

    En su lugar: Django lee el mismo diccionario de la conexión en cada petición
    (``BaseHandler.make_view_atomic``), y DRF revierte la transacción de una
    respuesta que sale de una excepción.
    """
    monkeypatch.setitem(connections["default"].settings_dict, "ATOMIC_REQUESTS", True)
