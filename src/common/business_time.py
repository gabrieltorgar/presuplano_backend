"""El día y el mes del negocio, en la hora de México (iteracion-27 #11).

``TIME_ZONE`` es UTC: así se guardan y se comparan los momentos (``created_at``,
vencimientos). Lo que decide un día o un mes de negocio —el mes en curso de los
ingresos, el tope diario de fotos— se calcula en ``BUSINESS_TIME_ZONE``
(``America/Mexico_City`` por omisión): con UTC, a las 18:00 de México ya era el
día siguiente.
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone


def business_zone() -> ZoneInfo:
    """La zona horaria del negocio (``BUSINESS_TIME_ZONE``)."""
    return ZoneInfo(settings.BUSINESS_TIME_ZONE)


def business_today() -> date:
    """Hoy en el calendario del negocio."""
    return timezone.localdate(timezone=business_zone())


def business_day_start() -> datetime:
    """Las 00:00 de hoy en la zona del negocio, como momento (con su zona)."""
    now = timezone.localtime(timezone=business_zone())
    return now.replace(hour=0, minute=0, second=0, microsecond=0)
