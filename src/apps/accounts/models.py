"""Accounts models: phone-based User and per-user Subscription.

Each ``User`` is a tenant: all domain data (tariffs, clients, quotes,
projects, payments) is scoped to the user that owns it.
"""

import uuid

from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.core.validators import RegexValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.accounts.managers import UserManager

#: presuplano's own blue: what a document is painted with until the account
#: chooses its own color.
DEFAULT_ORGANIZATION_COLOR = "#1E56D6"

#: A color has to be usable as ink on paper, so only full six-digit hex passes.
HEX_COLOR_VALIDATOR = RegexValidator(
    regex=r"^#[0-9A-Fa-f]{6}$",
    message="El color debe ser hexadecimal, por ejemplo #1E56D6.",
)


class User(AbstractBaseUser, PermissionsMixin):
    """User authenticated by phone number; owns a tenant workspace."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    phone = models.CharField(
        max_length=20,
        unique=True,
        db_index=True,
        verbose_name=_("teléfono"),
    )
    is_phone_verified = models.BooleanField(
        default=False,
        verbose_name=_("teléfono verificado"),
    )
    is_active = models.BooleanField(default=True, verbose_name=_("activo"))
    is_staff = models.BooleanField(default=False, verbose_name=_("es staff"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("creado en"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("actualizado en"))

    objects = UserManager()

    USERNAME_FIELD = "phone"
    REQUIRED_FIELDS: list[str] = []

    class Meta:
        db_table = "account_user"
        verbose_name = _("usuario")
        verbose_name_plural = _("usuarios")

    def __str__(self) -> str:
        return self.phone


class Subscription(models.Model):
    """A subscription owned by a single user, created on registration."""

    class Plan(models.TextChoices):
        INITIAL = "initial", _("Plan inicial")

    class Status(models.TextChoices):
        ACTIVE = "active", _("Activa")
        INACTIVE = "inactive", _("Inactiva")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="subscription",
        verbose_name=_("usuario"),
    )
    plan = models.CharField(
        max_length=20,
        choices=Plan.choices,
        default=Plan.INITIAL,
        verbose_name=_("plan"),
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
        verbose_name=_("estado"),
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("creado en"))

    class Meta:
        db_table = "account_subscription"
        verbose_name = _("suscripción")
        verbose_name_plural = _("suscripciones")

    def __str__(self) -> str:
        return f"{self.user.phone} — {self.plan} ({self.status})"


class Organization(models.Model):
    """The identity an account signs its documents with: a name and a color.

    Accounts are one-person workspaces, so this is not a tenancy boundary —
    it is the letterhead. It stays optional: with no name the documents are
    signed by presuplano itself, which is how every account started.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="organization",
        verbose_name=_("usuario"),
    )
    name = models.CharField(
        max_length=120,
        blank=True,
        default="",
        verbose_name=_("nombre"),
        help_text=_("Nombre que llevan los documentos; vacío los firma presuplano."),
    )
    color = models.CharField(
        max_length=7,
        default=DEFAULT_ORGANIZATION_COLOR,
        validators=[HEX_COLOR_VALIDATOR],
        verbose_name=_("color"),
        help_text=_("Color hexadecimal del encabezado de los documentos."),
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("creado en"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("actualizado en"))

    class Meta:
        db_table = "account_organization"
        verbose_name = _("organización")
        verbose_name_plural = _("organizaciones")

    def __str__(self) -> str:
        return self.name or self.user.phone
