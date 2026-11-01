"""La tabla de sesiones se limpia sola cada día (iteracion-26 #11).

Cada refresh emitido queda registrado (``token_blacklist``) y nada borraba los
vencidos: la tabla crecía sin límite. Un cron de Vercel llama cada día a
``GET /api/cron/flush-expired-tokens/`` con ``Authorization: Bearer
<CRON_SECRET>``; con el secreto correcto corre ``flushexpiredtokens`` y
responde 204. Sin el secreto configurado, sin la cabecera o con otro secreto
responde 401 y no borra nada. Una sesión de usuario no alcanza.
"""

import json
import re
from datetime import timedelta
from pathlib import Path

import pytest
from django.urls import resolve, reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.token_blacklist.models import (
    BlacklistedToken,
    OutstandingToken,
)
from rest_framework_simplejwt.tokens import RefreshToken

import core.settings as core_settings
from common.auth_cookies import ACCESS_COOKIE

URL = "/api/cron/flush-expired-tokens/"
SECRET = "un-secreto-de-cron-de-prueba-largo"
REPO = Path(core_settings.__file__).resolve().parents[2]


@pytest.fixture
def sesiones(db, user_factory):
    """Una sesión vencida (también en la lista negra) y una vigente."""
    cuenta = user_factory()
    vencida = OutstandingToken.objects.create(
        user=cuenta,
        jti="sesion-vencida",
        token="x",
        created_at=timezone.now() - timedelta(days=9),
        expires_at=timezone.now() - timedelta(days=2),
    )
    BlacklistedToken.objects.create(token=vencida)
    vigente = RefreshToken.for_user(cuenta)
    return {"cuenta": cuenta, "vigente": vigente["jti"]}


def quedan() -> set[str]:
    return set(OutstandingToken.objects.values_list("jti", flat=True))


@pytest.mark.django_db
class TestElCronDeLimpieza:
    def test_the_right_secret_flushes_the_expired_tokens(
        self, settings, sesiones
    ) -> None:
        """CRD-02 · iteracion-26 #11 — Con el secreto: 204 y quedan las vigentes."""
        settings.CRON_SECRET = SECRET

        response = APIClient().get(URL, HTTP_AUTHORIZATION=f"Bearer {SECRET}")

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert quedan() == {sesiones["vigente"]}
        assert not BlacklistedToken.objects.exists()

    def test_without_the_secret_configured_it_never_runs(
        self, settings, sesiones
    ) -> None:
        """CRD-02 · iteracion-26 #11 — Sin CRON_SECRET nadie lo dispara, ni con
        una cabecera vacía."""
        settings.CRON_SECRET = ""
        antes = quedan()

        for cabecera in ("Bearer ", "Bearer", f"Bearer {SECRET}"):
            response = APIClient().get(URL, HTTP_AUTHORIZATION=cabecera)
            assert response.status_code == status.HTTP_401_UNAUTHORIZED, cabecera
        assert quedan() == antes

    @pytest.mark.parametrize(
        "cabecera",
        [None, "Bearer otro-secreto", f"Token {SECRET}", f"bearer {SECRET}x"],
    )
    def test_without_the_right_header_it_is_401(
        self, settings, sesiones, cabecera
    ) -> None:
        """CRD-02 · iteracion-26 #11 — Sin la cabecera o con otro secreto: 401."""
        settings.CRON_SECRET = SECRET
        antes = quedan()
        extra = {"HTTP_AUTHORIZATION": cabecera} if cabecera else {}

        response = APIClient().get(URL, **extra)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert quedan() == antes

    def test_a_user_session_is_not_enough(self, settings, sesiones) -> None:
        """CRD-02 · iteracion-26 #11 — Ni la cookie de una cuenta verificada."""
        settings.CRON_SECRET = SECRET
        client = APIClient()
        client.cookies[ACCESS_COOKIE] = str(
            RefreshToken.for_user(sesiones["cuenta"]).access_token
        )
        antes = quedan()

        response = client.get(URL)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert quedan() == antes


def test_vercel_schedules_it_once_a_day() -> None:
    """CRD-02 · iteracion-26 #11 — vercel.json programa la ruta, a diario."""
    config = json.loads((REPO / "vercel.json").read_text(encoding="utf-8"))

    crons = config["crons"]

    assert [cron["path"] for cron in crons] == [URL]
    assert reverse("cron-flush-expired-tokens") == URL
    assert resolve(URL).url_name == "cron-flush-expired-tokens"
    minute, hour, day, month, weekday = crons[0]["schedule"].split()
    assert re.fullmatch(r"\d{1,2}", minute) and re.fullmatch(r"\d{1,2}", hour)
    assert (day, month, weekday) == ("*", "*", "*")
