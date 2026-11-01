"""El dominio de la cookie CSRF sale de la SPA y la API (SEC-04.4, iteracion-30 #1).

La SPA lee la cookie CSRF para repetirla en ``X-CSRFToken``, así que la cookie va
en el dominio que comparten la SPA (los orígenes de ``CORS_ALLOWED_ORIGINS``) y la
API (los hosts de ``ALLOWED_HOSTS``): ``itzaka.grupotorresmucino.com`` y
``api-itzaka.grupotorresmucino.com`` → ``.grupotorresmucino.com``. Con un dominio
que no es el suyo (el ``.itzaka.com`` que había por omisión) el navegador tira la
cookie y cada escritura responde «CSRF token missing».

Funciones puras, sin Django: ``settings.py`` deduce el dominio cuando nadie pone
``CSRF_COOKIE_DOMAIN`` y ``common/checks.py`` revisa en producción que cubra a las
dos.
"""

from ipaddress import ip_address
from urllib.parse import urlsplit

#: Sufijos públicos de plataforma (están en la Public Suffix List): cada
#: subdominio es de otro dueño, así que dos hosts bajo uno son siempre sitios
#: distintos y el navegador rechaza una cookie con ese Domain. Nunca son el
#: dominio de la cookie, y sus hosts (como los ``*.vercel.app`` que settings suma
#: a ALLOWED_HOSTS) no cuentan para deducirlo.
PLATFORM_PUBLIC_SUFFIXES = (
    "vercel.app",
    "netlify.app",
    "pages.dev",
    "herokuapp.com",
    "onrender.com",
    "github.io",
    "web.app",
    "firebaseapp.com",
    "fly.dev",
    "up.railway.app",
)
#: Segundos niveles genéricos de un dominio de país (com.mx, org.mx, gob.mx,
#: edu.mx): también son sufijos públicos, así que el dominio necesita una
#: etiqueta más (tienda.com.mx).
COUNTRY_SECOND_LEVELS = frozenset({"com", "org", "gob", "edu"})


def _under(host: str, domain: str) -> bool:
    """``host`` es ``domain`` o uno de sus subdominios (sin punto inicial)."""
    return host == domain or host.endswith("." + domain)


def _is_ip(host: str) -> bool:
    try:
        ip_address(host.strip("[]"))
    except ValueError:
        return False
    return True


def _can_share(host: str) -> bool:
    """Un host que puede compartir la cookie con otro: no es un comodín de
    ALLOWED_HOSTS (``*``, ``.dominio``), ``localhost``, una IP ni un host bajo un
    sufijo público de plataforma."""
    return (
        bool(host)
        and "*" not in host
        and not host.startswith(".")
        and not _under(host, "localhost")
        and not _is_ip(host)
        and not any(_under(host, suffix) for suffix in PLATFORM_PUBLIC_SUFFIXES)
    )


def app_hosts(cors_allowed_origins: list[str]) -> list[str]:
    """Los hosts de la SPA: los de sus orígenes ``https``, sin repetir."""
    hosts = []
    for origin in cors_allowed_origins:
        parts = urlsplit(origin.strip())
        if parts.scheme == "https" and parts.hostname:
            hosts.append(parts.hostname)
    return list(dict.fromkeys(hosts))


def api_hosts(allowed_hosts: list[str]) -> list[str]:
    """Los hosts de la API de ALLOWED_HOSTS que pueden compartir la cookie."""
    hosts = (host.strip().lower() for host in allowed_hosts)
    return list(dict.fromkeys(host for host in hosts if _can_share(host)))


def is_valid_cookie_domain(domain: str) -> bool:
    """Un dominio que la SPA y la API pueden compartir: dos etiquetas o más,
    nunca un sufijo público (``.com``, ``.vercel.app``, ``.com.mx``)."""
    labels = domain.strip().lower().lstrip(".").split(".")
    if len(labels) < 2 or not all(labels):
        return False
    if any(_under(".".join(labels), s) for s in PLATFORM_PUBLIC_SUFFIXES):
        return False
    second, top = labels[-2], labels[-1]
    country_second_level = (
        second in COUNTRY_SECOND_LEVELS and len(top) == 2 and top.isalpha()
    )
    return not (country_second_level and len(labels) < 3)


def covers(domain: str | None, host: str) -> bool:
    """La cookie con ese Domain llega a ``host`` y el navegador la acepta."""
    if not domain or not is_valid_cookie_domain(domain):
        return False
    return _under(host.lower(), domain.strip().lower().lstrip("."))


def _common_suffix(a: str, b: str) -> str:
    """El sufijo común más largo, por etiquetas: a.b.mx y c.b.mx → b.mx."""
    common = []
    for label_a, label_b in zip(
        reversed(a.split(".")), reversed(b.split(".")), strict=False
    ):
        if label_a != label_b:
            break
        common.append(label_a)
    return ".".join(reversed(common))


def csrf_cookie_domain(
    configured: str | None, cors_allowed_origins: list[str], allowed_hosts: list[str]
) -> str | None:
    """El dominio de la cookie CSRF.

    El configurado (``CSRF_COOKIE_DOMAIN``) gana siempre. Si no hay, el sufijo
    común más largo, por etiquetas, entre un host de la SPA y uno de la API, con
    un punto al inicio; de varios pares, el que cubre a más hosts de la SPA (con
    empate, el primero en el orden de CORS_ALLOWED_ORIGINS). ``None`` si no hay
    uno válido: la cookie queda en el host de la API, como en local.
    """
    if configured and configured.strip():
        return configured.strip()
    apps = [host for host in app_hosts(cors_allowed_origins) if _can_share(host)]
    apis = api_hosts(allowed_hosts)
    best, best_count = None, 0
    for app in apps:
        for api in apis:
            suffix = _common_suffix(app, api)
            if not is_valid_cookie_domain(suffix):
                continue
            count = sum(_under(host, suffix) for host in apps)
            if count > best_count:
                best, best_count = suffix, count
    return f".{best}" if best else None
