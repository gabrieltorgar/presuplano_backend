"""Cada petición en su transacción (``ATOMIC_REQUESTS``, iteracion-26 #22).

La RLS lo necesita (el contexto vive lo que la transacción), y con él todo 4xx
que maneja DRF revierte lo que la petición escribió. Los límites de intentos
viven en la caché de base de datos: si escribiera por la conexión de la
petición, una contraseña equivocada (401) revertiría su propio intento y el
límite nunca llegaría. La caché escribe por su alias, fuera de la transacción
(BOT-03.3). Aquí se prueba con la caché de verdad, no con la de memoria de la
suite.
"""

import pytest
from django.core.cache import cache
from rest_framework import status
from rest_framework.test import APIClient

import core.settings as core_settings
from apps.accounts.tests.factories import UserFactory

LOGIN = "/api/auth/login/"
ME_PASSWORD = "/api/auth/me/password/"


@pytest.fixture
def db_cache(settings):
    """La caché que se despliega (tabla en la base), vacía."""
    settings.CACHES = {"default": dict(core_settings.CACHES["default"])}
    cache.clear()
    yield
    cache.clear()


@pytest.mark.django_db(transaction=True, databases=["default", "cache"])
def test_failed_logins_still_reach_the_limit(db_cache) -> None:
    """BOT-03.3 · CRD-04 — Diez contraseñas equivocadas por minuto, y la
    siguiente es 429 aunque cada una respondiera 401 y revirtiera la petición."""
    user = UserFactory()
    client = APIClient()
    payload = {"email": user.email, "password": "no-es-esta"}

    failed = [client.post(LOGIN, payload, format="json") for _ in range(10)]
    response = client.post(LOGIN, payload, format="json")

    assert {r.status_code for r in failed} == {status.HTTP_401_UNAUTHORIZED}
    assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS


@pytest.mark.django_db(transaction=True, databases=["default", "cache"])
def test_wrong_current_passwords_still_reach_the_limit(db_cache) -> None:
    """BOT-03.3 — Con una sesión robada no se adivina la contraseña actual:
    cinco intentos por hora (``password_change``) aunque cada uno sea un 400."""
    user = UserFactory()
    client = APIClient()
    client.force_authenticate(user=user)
    payload = {"current_password": "no-es-esta", "new_password": "Teja-Roja-81"}

    failed = [client.post(ME_PASSWORD, payload, format="json") for _ in range(5)]
    response = client.post(ME_PASSWORD, payload, format="json")

    assert {r.status_code for r in failed} == {status.HTTP_400_BAD_REQUEST}
    assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
