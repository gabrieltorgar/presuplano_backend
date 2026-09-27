"""Accounts models: the account, its subscription and its letterhead.

Each ``User`` is a tenant: all domain data (tariffs, clients, quotes,
projects, payments) is scoped to the user that owns it. An account is its
email: por ahí se entra, por ahí llega el código que la verifica y por ahí
salen los comprobantes. El teléfono dejó de ser una forma de entrar —no había
cómo mandarle un código— y el de los documentos es el de la organización.
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
    """User authenticated by email; owns a tenant workspace."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(
        unique=True,
        db_index=True,
        verbose_name=_("correo"),
    )
    is_email_verified = models.BooleanField(
        default=False,
        verbose_name=_("correo verificado"),
    )
    # El correo nuevo espera aquí hasta que se demuestra con su código: la
    # cuenta sigue entrando con el de siempre, y un error de dedo no la deja
    # sin acceso.
    pending_email = models.EmailField(
        blank=True,
        default="",
        verbose_name=_("correo por confirmar"),
    )
    is_active = models.BooleanField(default=True, verbose_name=_("activo"))
    is_staff = models.BooleanField(default=False, verbose_name=_("es staff"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("creado en"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("actualizado en"))

    objects = UserManager()

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    class Meta:
        db_table = "account_user"
        verbose_name = _("usuario")
        verbose_name_plural = _("usuarios")

    def __str__(self) -> str:
        return self.email

    @property
    def is_verified(self) -> bool:
        """Si puede entrar: cuando demostró que el correo es suyo."""
        return self.is_email_verified

    @property
    def verification_identity(self) -> str:
        """A dónde va su código: su correo."""
        return self.email


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
    """The identity an account signs its documents with: name, color, contact.

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
    # El contacto que imprimen los documentos. No es el de la cuenta: el correo
    # con el que se entra no tiene por qué ser el que se le da a un cliente.
    email = models.EmailField(
        blank=True,
        default="",
        verbose_name=_("correo de contacto"),
        help_text=_("Sale en los documentos; vacío no sale nada."),
    )
    phone = models.CharField(
        max_length=30,
        blank=True,
        default="",
        verbose_name=_("teléfono de contacto"),
        help_text=_("Sale en los documentos; vacío no sale nada."),
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
        EMAIL_CHANGE = "email_change", _("Cambio de correo")

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
