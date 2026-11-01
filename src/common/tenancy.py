"""El contexto de empresa de la RLS (SEC-01 · iteracion-26 #22).

PostgreSQL aísla cada empresa (``common/rls.py``): una tabla de datos de trabajo
deja ver y escribir sólo las filas de la empresa que dice ``app.company_id``, y
sin contexto ninguna. La empresa es la cuenta dueña de los datos que eligió la
petición (``apps.team.tenancy.account_of``).

El contexto se fija con ``set_config(..., true)``, que es ``SET LOCAL``: vive lo
que la transacción en curso. Por eso cada petición corre en la suya
(``ATOMIC_REQUESTS``) y lo fijan, dentro de ella, ``common.views``
(``TenantContextMixin``, la API) y ``core.middleware`` (el admin). Funciona con
el pooler de Neon en modo transacción por lo mismo: nada sobrevive al commit.
"""

from django.core.exceptions import ImproperlyConfigured
from django.db import connection

#: Leer las filas de todas las empresas, sólo en el admin y sólo leer. Es un
#: permiso que se otorga a mano (queda en el admin); ser staff no lo da. El
#: superusuario, como todo permiso, lo tiene.
PLATFORM_OPERATOR_PERM = "accounts.view_all_companies"


def set_tenant_context(
    *, company_id: object | None, platform_operator: bool = False
) -> None:
    """Pone la empresa (y si se lee como operador) hasta el fin de la transacción.

    Raises:
        ImproperlyConfigured: fuera de una transacción. En autocommit el
            ``SET LOCAL`` muere con su propia sentencia y la consulta siguiente
            correría sin contexto: mejor fallar fuerte que no aislar.
    """
    if not connection.in_atomic_block:
        raise ImproperlyConfigured(
            "set_tenant_context necesita una transacción "
            "(ATOMIC_REQUESTS o transaction.atomic())."
        )
    if connection.vendor != "postgresql":
        return  # SQLite (la suite local): no hay políticas que alimentar.
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT set_config('app.company_id', %s, true), "
            "set_config('app.platform_operator', %s, true)",
            [str(company_id or ""), "true" if platform_operator else "false"],
        )
