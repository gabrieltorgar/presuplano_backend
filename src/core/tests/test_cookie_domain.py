"""El dominio de la cookie CSRF sale de la SPA y la API (SEC-04.4 · iteracion-30 #1).

La SPA lee la cookie CSRF para repetirla en ``X-CSRFToken``: la cookie va en el
dominio que comparte con la API, el sufijo común más largo de un host de la SPA
(``CORS_ALLOWED_ORIGINS``) y uno de la API (``ALLOWED_HOSTS``). La función es pura
(``core/cookie_domain.py``); aquí, sus casos. Cómo la usa ``core.settings``, en
``apps/accounts/tests/test_session_cookies.py``.
"""

import pytest

from core.cookie_domain import (
    PLATFORM_PUBLIC_SUFFIXES,
    api_hosts,
    app_hosts,
    covers,
    csrf_cookie_domain,
    is_valid_cookie_domain,
)

ITZAKA_SPA = "https://itzaka.grupotorresmucino.com"
ITZAKA_API = "api-itzaka.grupotorresmucino.com"


def deducido(origenes: list[str], hosts: list[str]) -> str | None:
    return csrf_cookie_domain(None, origenes, hosts)


class TestElCalculo:
    """SEC-04.4 · iteracion-30 #1 — el sufijo común más largo, por etiquetas."""

    def test_the_itzaka_pair_shares_grupotorresmucino(self) -> None:
        """La SPA y la API de Itzaka, hoy en producción."""
        assert deducido([ITZAKA_SPA], [ITZAKA_API]) == ".grupotorresmucino.com"

    def test_the_tlakio_pair_shares_grupotorresmucino(self) -> None:
        """El de Tlakio vive en el mismo dominio."""
        assert (
            deducido(
                ["https://tlakio.grupotorresmucino.com"],
                ["api-tlakio.grupotorresmucino.com"],
            )
            == ".grupotorresmucino.com"
        )

    def test_spa_on_the_domain_and_api_on_its_subdomain(self) -> None:
        """tlakio.com con api.tlakio.com → .tlakio.com (y los de antes de Itzaka)."""
        assert deducido(["https://tlakio.com"], ["api.tlakio.com"]) == ".tlakio.com"
        assert deducido(["https://itzaka.com"], ["api.itzaka.com"]) == ".itzaka.com"
        assert (
            deducido(["https://dev.itzaka.com"], ["api-dev.itzaka.com"])
            == ".itzaka.com"
        )

    def test_the_longest_common_suffix(self) -> None:
        """Comparten b.example.com, no sólo example.com."""
        assert (
            deducido(["https://app.b.example.com"], ["api.b.example.com"])
            == ".b.example.com"
        )

    def test_the_vercel_hosts_the_settings_adds_do_not_count(self) -> None:
        """Los *.vercel.app del despliegue no cambian el dominio."""
        hosts = [ITZAKA_API, "itzaka-api-abc.vercel.app", "itzaka-api.vercel.app"]

        assert deducido([ITZAKA_SPA], hosts) == ".grupotorresmucino.com"

    def test_spa_and_api_on_vercel_app_have_no_domain(self) -> None:
        """Dos proyectos en *.vercel.app siempre son sitios distintos."""
        assert (
            deducido(["https://cuotreka.vercel.app"], ["itzaka-api.vercel.app"]) is None
        )

    @pytest.mark.parametrize("sufijo", PLATFORM_PUBLIC_SUFFIXES)
    def test_no_platform_public_suffix_is_the_domain(self, sufijo) -> None:
        """El navegador rechaza una cookie con Domain de un sufijo público."""
        assert deducido([f"https://app.{sufijo}"], [f"api.{sufijo}"]) is None
        assert not is_valid_cookie_domain(f".{sufijo}")

    def test_locally_there_is_no_domain(self) -> None:
        """localhost y las IPs dejan la cookie en su host."""
        hosts = ["localhost", "127.0.0.1", "[::1]"]

        assert deducido(["http://localhost:5173"], hosts) is None
        assert deducido(["https://localhost:5173"], hosts) is None
        assert deducido(["https://app.localhost"], ["api.localhost"]) is None
        assert deducido(["https://10.0.0.4"], ["10.0.0.5"]) is None

    def test_only_https_origins_of_the_spa(self) -> None:
        """La cookie es Secure fuera de DEBUG: un origen http no cuenta."""
        assert deducido(["http://itzaka.com"], ["api.itzaka.com"]) is None

    def test_without_origins_or_hosts_there_is_no_domain(self) -> None:
        assert deducido([], [ITZAKA_API]) is None
        assert deducido([ITZAKA_SPA], []) is None
        assert deducido([], []) is None

    def test_a_single_common_label_is_not_a_domain(self) -> None:
        """Nunca .com."""
        assert deducido(["https://itzaka.com"], ["api.otro.com"]) is None
        assert not is_valid_cookie_domain(".com")

    @pytest.mark.parametrize("pais", ["com.mx", "org.mx", "gob.mx", "edu.mx", "com.ar"])
    def test_a_country_second_level_needs_another_label(self, pais) -> None:
        """com.mx es un sufijo público; estudio.com.mx sí es un dominio."""
        assert deducido([f"https://estudio.{pais}"], [f"api.otro.{pais}"]) is None
        assert not is_valid_cookie_domain(f".{pais}")
        assert deducido([f"https://estudio.{pais}"], [f"api.estudio.{pais}"]) == (
            f".estudio.{pais}"
        )

    def test_a_country_domain_with_another_second_level_is_valid(self) -> None:
        """itzaka.mx (dos etiquetas) es un dominio registrable."""
        assert deducido(["https://itzaka.mx"], ["api.itzaka.mx"]) == ".itzaka.mx"

    def test_allowed_hosts_wildcards_do_not_count(self) -> None:
        """«*» y «.dominio» no son el host de la API."""
        origenes = ["https://itzaka.com"]

        assert deducido(origenes, ["*"]) is None
        assert deducido(origenes, [".itzaka.com"]) is None
        assert deducido(origenes, ["*.itzaka.com"]) is None

    def test_origins_on_two_domains_take_the_api_one(self) -> None:
        """La SPA en dos dominios; sólo uno lo comparte con la API."""
        origenes = ["https://itzaka.mx", "https://itzaka.com"]

        assert deducido(origenes, ["api.itzaka.com"]) == ".itzaka.com"

    def test_with_several_pairs_the_one_covering_most_origins_wins(self) -> None:
        """Dos orígenes de la SPA viven en otro.mx y uno en example.com."""
        origenes = ["https://a.example.com", "https://b.otro.mx", "https://c.otro.mx"]

        assert deducido(origenes, ["api.example.com", "api.otro.mx"]) == ".otro.mx"

    def test_on_a_tie_the_first_of_the_list_wins(self) -> None:
        """El primer origen de CORS_ALLOWED_ORIGINS decide."""
        origenes = ["https://app.uno.com", "https://app.dos.com"]
        hosts = ["api.dos.com", "api.uno.com"]

        assert deducido(origenes, hosts) == ".uno.com"
        assert deducido(list(reversed(origenes)), hosts) == ".dos.com"

    def test_case_and_spaces_do_not_change_the_domain(self) -> None:
        assert (
            deducido(
                [" https://Itzaka.Grupotorresmucino.com "],
                [" API-Itzaka.GRUPOTORRESMUCINO.com "],
            )
            == ".grupotorresmucino.com"
        )


class TestLaVariableAMano:
    """SEC-04.4 · iteracion-30 #1 — CSRF_COOKIE_DOMAIN puesta a mano gana siempre."""

    @pytest.mark.parametrize("configurado", [".itzaka.com", "  .itzaka.com  "])
    def test_the_configured_domain_wins(self, configurado) -> None:
        assert csrf_cookie_domain(configurado, [ITZAKA_SPA], [ITZAKA_API]) == (
            ".itzaka.com"
        )

    @pytest.mark.parametrize("vacia", [None, "", "   "])
    def test_an_empty_one_does_not_count(self, vacia) -> None:
        """Vacía es como no ponerla: se deduce."""
        assert csrf_cookie_domain(vacia, [ITZAKA_SPA], [ITZAKA_API]) == (
            ".grupotorresmucino.com"
        )


class TestLasPiezasDeLaRevision:
    """SEC-04.4 · iteracion-30 #1 — lo que también usa common.E005–E007."""

    def test_spa_hosts_come_from_its_https_origins(self) -> None:
        origenes = [
            "https://itzaka.com",
            "https://itzaka.com",
            "http://localhost:5173",
            "https://app.itzaka.com:8443",
        ]

        assert app_hosts(origenes) == ["itzaka.com", "app.itzaka.com"]

    def test_api_hosts_without_wildcards_local_ips_or_vercel(self) -> None:
        hosts = [
            "API.itzaka.com",
            "*",
            ".itzaka.com",
            "localhost",
            "127.0.0.1",
            "[::1]",
            "itzaka-api-abc.vercel.app",
            "api.itzaka.com",
            "",
        ]

        assert api_hosts(hosts) == ["api.itzaka.com"]

    def test_a_domain_covers_its_host_and_its_subdomains(self) -> None:
        assert covers(".grupotorresmucino.com", "itzaka.grupotorresmucino.com")
        assert covers(".grupotorresmucino.com", "grupotorresmucino.com")
        assert covers(".Itzaka.com", "API.itzaka.com")
        assert not covers(".grupotorresmucino.com", "grupotorresmucino.com.mx")
        assert not covers(".itzaka.com", "itzaka.grupotorresmucino.com")
        assert not covers(".com", "itzaka.com"), "el navegador rechaza Domain=.com"
        assert not covers(None, "itzaka.com")
