"""Dos peticiones a la vez, de verdad (iteracion-26 #20 · SEC-03.2).

Sólo PostgreSQL bloquea filas (``SELECT … FOR UPDATE``): en SQLite las pruebas
que usan esto se saltan y corren en CI, que prueba contra PostgreSQL. Cada hilo
abre su conexión y la cierra al terminar; la prueba que lo usa necesita
``django_db(transaction=True)`` para que lo que hace un hilo lo vea el otro.
"""

import threading
from collections.abc import Callable

import pytest
from django.db import connection
from rest_framework.test import APIClient

POSTGRES_ONLY = pytest.mark.skipif(
    connection.vendor != "postgresql",
    reason="la concurrencia real sólo existe en PostgreSQL: corre en CI con PostgreSQL",
)


def at_the_same_time(user, *requests: Callable[[APIClient], object]) -> list:
    """Suelta todas las peticiones juntas y devuelve lo que respondió cada una."""
    barrier = threading.Barrier(len(requests))
    answers: list = [None] * len(requests)

    def run(index: int, request: Callable[[APIClient], object]) -> None:
        client = APIClient()
        client.force_authenticate(user=user)
        try:
            barrier.wait()
            answers[index] = request(client)
        finally:
            connection.close()

    threads = [
        threading.Thread(target=run, args=(index, request))
        for index, request in enumerate(requests)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return answers
