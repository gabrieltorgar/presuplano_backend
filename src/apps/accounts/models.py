"""Accounts models: the account, its subscription and its letterhead.

Each ``User`` is a tenant: all domain data (tariffs, clients, quotes,
projects, payments) is scoped to the user that owns it. An account is
identified by a phone, by an email, or by both: the architect who works from
the site signs in with the number they already know by heart, and the one who
works from the studio with their email.
"""

import uuid

from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.core.validators import RegexValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.accounts.managers import UserManager
from common.uploads import organization_logo_upload_to

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
    # Uno de los dos basta, y ninguno se repite. Van nulos —y no en blanco—
    # cuando faltan: dos cadenas vacías chocarían contra el índice único,
    # mientras que dos nulos conviven.
    phone = models.CharField(
        max_length=20,
        unique=True,
        null=True,
        blank=True,
        db_index=True,
        verbose_name=_("teléfono"),
    )
    email = models.EmailField(
        unique=True,
        null=True,
        blank=True,
        db_index=True,
        verbose_name=_("correo"),
    )
    is_phone_verified = models.BooleanField(
        default=False,
        verbose_name=_("teléfono verificado"),
    )
    is_email_verified = models.BooleanField(
        default=False,
        verbose_name=_("correo verificado"),
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
        return self.phone or self.email or str(self.pk)

    @property
    def is_verified(self) -> bool:
        """Si demostró tener alguna de sus dos identidades.

        Con una basta para entrar: quien se registró con su correo no tiene un
        teléfono que verificar, y a quien tiene los dos no se le pide dos veces.
        """
        return self.is_phone_verified or self.is_email_verified


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
        return f"{self.user} — {self.plan} ({self.status})"


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
    logo = models.ImageField(
        upload_to=organization_logo_upload_to,
        blank=True,
        null=True,
        verbose_name=_("logotipo"),
        help_text=_("La imagen que llevan los documentos junto al nombre."),
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("creado en"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("actualizado en"))

    class Meta:
        db_table = "account_organization"
        verbose_name = _("organización")
        verbose_name_plural = _("organizaciones")

    def __str__(self) -> str:
        return self.name or str(self.user)


class OtpCode(models.Model):
    """Un código de un solo uso, con su plazo y para qué sirve.

    Hasta ahora el código era uno solo para todos (``OTP_UNIVERSAL_CODE``):
    servía para el MVP porque no había por dónde mandarlo. Con el correo sí lo
    hay, así que cada cuenta con correo recibe el suyo, se guarda cifrado —lo
    que llega a la base no sirve para entrar— y muere al usarse o al vencer.
    """

    class Purpose(models.TextChoices):
        SIGNUP = "signup", _("Verificación de la cuenta")
        PASSWORD_RESET = "password_reset", _("Cambio de contraseña")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="otp_codes",
        verbose_name=_("usuario"),
    )
    purpose = models.CharField(
        max_length=20, choices=Purpose.choices, verbose_name=_("motivo")
    )
    code_hash = models.CharField(max_length=128, verbose_name=_("código"))
    expires_at = models.DateTimeField(verbose_name=_("vence en"))
    used_at = models.DateTimeField(null=True, blank=True, verbose_name=_("usado en"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("creado en"))

    class Meta:
        db_table = "account_otpcode"
        ordering = ["-created_at"]
        verbose_name = _("código de verificación")
        verbose_name_plural = _("códigos de verificación")
        indexes = [models.Index(fields=["user", "purpose", "-created_at"])]

    def __str__(self) -> str:
        return f"{self.user} — {self.purpose}"
