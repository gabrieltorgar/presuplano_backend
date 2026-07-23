"""Factories for accounts tests."""

import factory

from apps.accounts.models import User


class UserFactory(factory.django.DjangoModelFactory):
    """Builds a verified, active user with a unique phone."""

    class Meta:
        model = User
        skip_postgeneration_save = True

    phone = factory.Sequence(lambda n: f"55100000{n:03d}")
    is_phone_verified = True
    is_active = True

    @factory.post_generation
    def password(self, create: bool, extracted: str | None, **kwargs) -> None:
        password = extracted or "testpass123"
        self.set_password(password)
        if create:
            self.save()
