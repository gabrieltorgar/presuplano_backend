"""Factories for accounts tests."""

import factory

from apps.accounts.models import User


class UserFactory(factory.django.DjangoModelFactory):
    """Builds a verified, active user with a unique email."""

    class Meta:
        model = User
        skip_postgeneration_save = True

    email = factory.Sequence(lambda n: f"cuenta{n:03d}@cuotreka.test")
    is_email_verified = True
    is_active = True

    @factory.post_generation
    def password(self, create: bool, extracted: str | None, **kwargs) -> None:
        password = extracted or "testpass123"
        self.set_password(password)
        if create:
            self.save()
