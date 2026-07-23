"""Factories for catalog tests."""

from decimal import Decimal

import factory

from apps.accounts.tests.factories import UserFactory
from apps.catalog.models import Tariff


class TariffFactory(factory.django.DjangoModelFactory):
    """Builds a tariff owned by a (new by default) user."""

    class Meta:
        model = Tariff

    owner = factory.SubFactory(UserFactory)
    name = factory.Sequence(lambda n: f"Tarifa {n}")
    unit_type = Tariff.UnitType.SQUARE_METER
    unit_price = Decimal("350.00")
