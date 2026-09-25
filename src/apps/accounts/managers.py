"""User manager: una cuenta se identifica por su teléfono, su correo, o ambos."""

from django.contrib.auth.base_user import BaseUserManager


class UserManager(BaseUserManager):
    """Manager for the custom user (phone and/or email)."""

    use_in_migrations = True

    def create_user(
        self,
        phone: str | None = None,
        password: str | None = None,
        email: str | None = None,
        **extra_fields,
    ):
        """Create and save a user identified by a phone, an email, or both."""
        if not phone and not email:
            raise ValueError("The account needs a phone number or an email.")
        user = self.model(
            phone=phone or None,
            email=self.normalize_email(email) or None,
            **extra_fields,
        )
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(
        self, phone: str | None = None, password: str | None = None, **extra_fields
    ):
        """Create and save a superuser."""
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        extra_fields.setdefault("is_phone_verified", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self.create_user(phone, password, **extra_fields)
