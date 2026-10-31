"""La sesión en cookies HttpOnly (iteracion-12 #1).

El servidor pone el access y el refresh en cookies que JavaScript no puede leer:
un XSS o una extensión ya no se llevan la sesión. El access viaja a toda la API;
el refresh, sólo a las rutas de la sesión. SameSite=Lax, y Secure fuera de
desarrollo. La SPA (itzaka.com) llama a la API en su subdominio
(api.itzaka.com): el mismo sitio, así que son cookies propias, no de terceros.
Nunca llevan Domain: sólo la API las recibe (la CSRF sí va al dominio padre).

Las cookies se llamaban como el nombre anterior (Cuotreka). Las de antes se
siguen leyendo para que nadie pierda su sesión con el cambio de marca
(iteracion-20), y se borran en cuanto la sesión se renueva o se cierra.
"""

from django.conf import settings
from django.http import HttpResponse
from rest_framework_simplejwt.tokens import RefreshToken

ACCESS_COOKIE = "itzaka_access"
REFRESH_COOKIE = "itzaka_refresh"
#: Los nombres de antes del cambio de marca: solo se leen y se borran.
LEGACY_ACCESS_COOKIE = "cuotreka_access"
LEGACY_REFRESH_COOKIE = "cuotreka_refresh"
ACCESS_PATH = "/api/"
REFRESH_PATH = "/api/auth/"


def _cookie(
    response: HttpResponse, name: str, value: str, *, path: str, max_age: int
) -> None:
    response.set_cookie(
        name,
        value,
        max_age=max_age,
        path=path,
        httponly=True,
        secure=settings.SESSION_COOKIE_SECURE,
        samesite="Lax",
    )


def access_from(request) -> str | None:
    """El access de la cookie, con el nombre de ahora o el de antes."""
    return request.COOKIES.get(ACCESS_COOKIE) or request.COOKIES.get(
        LEGACY_ACCESS_COOKIE
    )


def refresh_from(request) -> str | None:
    """El refresh de la cookie, con el nombre de ahora o el de antes."""
    return request.COOKIES.get(REFRESH_COOKIE) or request.COOKIES.get(
        LEGACY_REFRESH_COOKIE
    )


def _clear_legacy_cookies(response: HttpResponse) -> None:
    response.delete_cookie(LEGACY_ACCESS_COOKIE, path=ACCESS_PATH, samesite="Lax")
    response.delete_cookie(LEGACY_REFRESH_COOKIE, path=REFRESH_PATH, samesite="Lax")


def set_token_cookies(response: HttpResponse, *, access: str, refresh: str) -> None:
    """Pone en las cookies un par de tokens ya emitido (al renovar, por ejemplo)."""
    jwt = settings.SIMPLE_JWT
    _clear_legacy_cookies(response)
    _cookie(
        response,
        ACCESS_COOKIE,
        access,
        path=ACCESS_PATH,
        max_age=int(jwt["ACCESS_TOKEN_LIFETIME"].total_seconds()),
    )
    _cookie(
        response,
        REFRESH_COOKIE,
        refresh,
        path=REFRESH_PATH,
        max_age=int(jwt["REFRESH_TOKEN_LIFETIME"].total_seconds()),
    )


def set_session_cookies(response: HttpResponse, refresh: RefreshToken) -> None:
    """Abre (o renueva) la sesión en las cookies de la respuesta."""
    set_token_cookies(response, access=str(refresh.access_token), refresh=str(refresh))


def clear_session_cookies(response: HttpResponse) -> None:
    """Borra las cookies de la sesión."""
    response.delete_cookie(ACCESS_COOKIE, path=ACCESS_PATH, samesite="Lax")
    response.delete_cookie(REFRESH_COOKIE, path=REFRESH_PATH, samesite="Lax")
    _clear_legacy_cookies(response)
