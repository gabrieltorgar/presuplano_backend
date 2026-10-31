"""Por qué conexión va cada modelo (iteracion-26 #22 · BOT-03.3)."""


class CacheRouter:
    """La caché de base de datos (``django_cache``) lee y escribe por ``cache``.

    Con ``ATOMIC_REQUESTS`` la petición corre en una transacción que un 4xx
    revierte: por ``default``, el contador del intento fallido se iría con ella
    y el límite nunca llegaría. El alias ``cache`` es otra conexión a la misma
    base, en autocommit.

    Sin ``allow_migrate``: los dos alias son la misma base, así que la tabla que
    crea el build (``createcachetable``, en el alias ``default``) es la que lee
    ``cache``; la receta que la limita a ``cache`` haría que ese comando no
    creara nada en una base nueva.
    """

    def db_for_read(self, model, **hints):
        return "cache" if model._meta.app_label == "django_cache" else None

    def db_for_write(self, model, **hints):
        return "cache" if model._meta.app_label == "django_cache" else None
