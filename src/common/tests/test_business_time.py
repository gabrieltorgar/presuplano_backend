"""El «hoy» y el mes en curso del negocio, con la hora de México (iteracion-27 #11).

``TIME_ZONE`` sigue en UTC: los momentos se guardan y se comparan en UTC. Lo que
decide un día o un mes de negocio —el mes en curso de los ingresos de Inicio,
el tope diario de fotos de plano— se calcula en ``BUSINESS_TIME_ZONE``
(``America/Mexico_City`` por omisión, del entorno). Con UTC, a las 18:00 de
México ya era el día siguiente, y el último día del mes ya contaba el siguiente.

El reloj se fija con ``monkeypatch`` sobre ``django.utils.timezone.now`` (el
proyecto no usa freezegun): las 23:30 de México del último día de septiembre,
que en UTC ya son las 05:30 del 1 de octubre.
"""

import os
import subprocess
import sys
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from django.utils import timezone

import core.settings as core_settings
from apps.dashboard.selectors import monthly_income
from apps.payments.services import register_payment
from apps.payments.tests.test_payments import make_project_with_advance
from apps.planner import photo_conversion
from apps.planner.models import PhotoConversion
from common.business_time import business_day_start, business_today

#: 2026-09-30 23:30 en Ciudad de México (UTC-6): en UTC ya es 1 de octubre.
MEXICO_LAST_NIGHT_OF_SEPTEMBER = datetime(2026, 10, 1, 5, 30, tzinfo=UTC)
SRC = Path(core_settings.__file__).resolve().parents[1]


@pytest.fixture
def reloj_a_las_2330_de_mexico(monkeypatch):
    """El reloj de Django en el último día de septiembre, 23:30 en México."""
    monkeypatch.setattr(timezone, "now", lambda: MEXICO_LAST_NIGHT_OF_SEPTEMBER)
    return MEXICO_LAST_NIGHT_OF_SEPTEMBER


class TestLaZonaDeNegocio:
    def test_the_default_is_mexico_city_and_storage_stays_utc(self) -> None:
        """Flujo principal - México por omisión; TIME_ZONE no cambia."""
        assert core_settings.BUSINESS_TIME_ZONE == "America/Mexico_City"
        assert core_settings.TIME_ZONE == "UTC"

    @pytest.mark.parametrize(
        ("valor", "esperado"),
        [("America/Tijuana", "America/Tijuana"), ("", "America/Mexico_City")],
    )
    def test_it_comes_from_the_environment(self, valor, esperado) -> None:
        """Flujo principal - Del entorno; vacía (.env.example), la de omisión."""
        salida = subprocess.run(  # noqa: S603 -- el mismo intérprete, sin shell
            [
                sys.executable,
                "-c",
                "from django.conf import settings as s; print(s.BUSINESS_TIME_ZONE)",
            ],
            cwd=SRC,
            env={
                **os.environ,
                "DJANGO_SETTINGS_MODULE": "core.settings",
                "BUSINESS_TIME_ZONE": valor,
            },
            capture_output=True,
            text=True,
            check=True,
        )

        assert salida.stdout.strip() == esperado

    def test_an_unknown_zone_does_not_load(self) -> None:
        """Caso de borde - Una zona que no existe no deja arrancar (falla cerrado)."""
        salida = subprocess.run(  # noqa: S603 -- el mismo intérprete, sin shell
            [
                sys.executable,
                "-c",
                "from django.conf import settings as s; print(s.BUSINESS_TIME_ZONE)",
            ],
            cwd=SRC,
            env={
                **os.environ,
                "DJANGO_SETTINGS_MODULE": "core.settings",
                "BUSINESS_TIME_ZONE": "Mexico/Ninguna",
            },
            capture_output=True,
            text=True,
        )

        assert salida.returncode != 0
        assert "BUSINESS_TIME_ZONE" in salida.stderr


@pytest.mark.usefixtures("reloj_a_las_2330_de_mexico")
class TestHoyEnMexico:
    def test_today_is_still_the_30th(self) -> None:
        """Bug iteracion-27 #11 - A las 23:30 de México sigue siendo el 30."""
        assert business_today() == date(2026, 9, 30)

    def test_the_business_day_starts_at_mexican_midnight(self) -> None:
        """Bug iteracion-27 #11 - El día empieza a las 00:00 de México (06:00 UTC)."""
        assert business_day_start() == datetime(2026, 9, 30, 6, 0, tzinfo=UTC)

    @pytest.mark.django_db
    def test_the_current_month_of_income_is_september(self, user) -> None:
        """Bug iteracion-27 #11 - Inicio: el último mes de los ingresos es
        septiembre, con lo cobrado el 30, aunque en UTC ya sea octubre."""
        project = make_project_with_advance(user)
        register_payment(
            owner=user, project=project, amount=Decimal("1500"), date=date(2026, 9, 30)
        )

        months = monthly_income(owner=user)

        assert months[-1] == {"month": "2026-09", "amount": "1500.00"}
        assert months[0]["month"] == "2026-04"

    @pytest.mark.django_db
    def test_a_photo_read_this_morning_counts_for_today(self, user) -> None:
        """Bug iteracion-27 #11 - El tope diario de fotos cuenta el día de México:
        una foto de las 10:00 del 30 sigue contando a las 23:30 del 30."""
        conversion = PhotoConversion.objects.create(owner=user)
        PhotoConversion.objects.filter(pk=conversion.pk).update(
            created_at=datetime(2026, 9, 30, 16, 0, tzinfo=UTC)  # 10:00 en México
        )
        yesterday = PhotoConversion.objects.create(owner=user)
        PhotoConversion.objects.filter(pk=yesterday.pk).update(
            created_at=datetime(2026, 9, 30, 6, 0, tzinfo=UTC) - timedelta(minutes=1)
        )

        assert photo_conversion.conversions_today(user) == 1
