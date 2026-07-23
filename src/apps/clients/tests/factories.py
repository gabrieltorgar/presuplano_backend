"""Factories for clients tests."""

import factory

from apps.accounts.tests.factories import UserFactory
from apps.clients.models import Client


class ClientFactory(factory.django.DjangoModelFactory):
    """Builds a client owned by a (new by default) user."""

    class Meta:
        model = Client

    owner = factory.SubFactory(UserFactory)
    name = factory.Sequence(lambda n: f"Cliente {n}")
    phone = "555-1234"
    email = ""
