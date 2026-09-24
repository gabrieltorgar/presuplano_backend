"""Factories for staff tests."""

import factory

from apps.accounts.tests.factories import UserFactory
from apps.staff.models import Worker


class WorkerFactory(factory.django.DjangoModelFactory):
    """Builds a worker owned by a (new by default) user."""

    class Meta:
        model = Worker

    owner = factory.SubFactory(UserFactory)
    name = factory.Sequence(lambda n: f"Trabajador {n}")
    kind = Worker.Kind.PERSON
    phone = "555-9000"
