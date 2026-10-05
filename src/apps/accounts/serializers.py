"""Accounts serializers (input validation only; no business logic)."""

from rest_framework import serializers

from apps.accounts.models import HEX_COLOR_VALIDATOR, Organization, Subscription, User
from apps.legal.serializers import AcceptanceSerializer
from apps.legal.services import check_versions, status_for

MIN_PASSWORD_LENGTH = 8


class RegisterSerializer(AcceptanceSerializer):
    """Validates registration input: email, uniqueness, password length and the
    acceptance of the legal documents in force."""

    email = serializers.EmailField(
        error_messages={
            "required": "Escribe tu correo para registrarte",
            "blank": "Escribe tu correo para registrarte",
            "invalid": "Escribe un correo válido",
        }
    )
    password = serializers.CharField(write_only=True, style={"input_type": "password"})

    def validate_email(self, value: str) -> str:
        if User.objects.filter(email__iexact=value.strip()).exists():
            raise serializers.ValidationError("Ese correo ya está registrado")
        return value

    def validate_password(self, value: str) -> str:
        if len(value) < MIN_PASSWORD_LENGTH:
            raise serializers.ValidationError(
                "La contraseña debe tener al menos 8 caracteres"
            )
        return value

    def validate(self, attrs: dict) -> dict:
        # Lo aceptado tiene que ser lo que rige: si cambió mientras se llenaba
        # el formulario, se vuelve a pedir en vez de registrar otro texto.
        check_versions(
            terms_version=attrs["terms_version"],
            privacy_version=attrs["privacy_version"],
        )
        return attrs


class EmailIdentitySerializer(serializers.Serializer):
    """Quién dice ser: su correo.

    Acepta también ``identifier``, el nombre del campo cuando se podía entrar
    con teléfono: una pantalla vieja todavía abierta no se queda fuera, y un
    correo escrito ahí sirve igual.
    """

    email = serializers.CharField(max_length=254, required=False)
    identifier = serializers.CharField(max_length=254, required=False)

    def validate(self, attrs: dict) -> dict:
        email = (attrs.get("email") or attrs.get("identifier") or "").strip()
        if not email:
            raise serializers.ValidationError({"email": "Escribe tu correo"})
        try:
            serializers.EmailField().run_validation(email)
        except serializers.ValidationError:
            raise serializers.ValidationError(
                {"email": "Escribe un correo válido"}
            ) from None
        return {"email": email}


class VerifyOtpSerializer(EmailIdentitySerializer):
    """Validates OTP verification input."""

    code = serializers.CharField(max_length=6)

    def validate(self, attrs: dict) -> dict:
        code = attrs.get("code", "")
        return {**super().validate(attrs), "code": code}


class ResendOtpSerializer(EmailIdentitySerializer):
    """Reenviar el código: basta con el correo de la cuenta."""


class PasswordResetRequestSerializer(EmailIdentitySerializer):
    """Pedir recuperar: sólo hace falta el correo de la cuenta."""


class PasswordResetConfirmSerializer(VerifyOtpSerializer):
    """Confirmar la recuperación con el código y la contraseña nueva."""

    password = serializers.CharField(write_only=True, style={"input_type": "password"})

    def validate_password(self, value: str) -> str:
        if len(value) < MIN_PASSWORD_LENGTH:
            raise serializers.ValidationError(
                "La contraseña debe tener al menos 8 caracteres"
            )
        return value

    def validate(self, attrs: dict) -> dict:
        password = attrs.get("password", "")
        return {**super().validate(attrs), "password": password}


class LoginSerializer(EmailIdentitySerializer):
    """Validates login input."""

    password = serializers.CharField(write_only=True, style={"input_type": "password"})

    def validate(self, attrs: dict) -> dict:
        password = attrs.get("password", "")
        return {**super().validate(attrs), "password": password}


class EmailChangeSerializer(serializers.Serializer):
    """El correo nuevo al que se quiere cambiar la cuenta."""

    email = serializers.EmailField(
        error_messages={
            "required": "Escribe el correo nuevo",
            "blank": "Escribe el correo nuevo",
            "invalid": "Escribe un correo válido",
        }
    )


class EmailChangeConfirmSerializer(serializers.Serializer):
    """El código que llegó al correo nuevo."""

    code = serializers.CharField(
        max_length=6,
        error_messages={
            "required": "Escribe el código que te llegó",
            "blank": "Escribe el código que te llegó",
        },
    )


class PasswordChangeSerializer(serializers.Serializer):
    """La contraseña de ahora y la nueva."""

    current_password = serializers.CharField(
        write_only=True,
        error_messages={
            "required": "Escribe tu contraseña actual",
            "blank": "Escribe tu contraseña actual",
        },
    )
    new_password = serializers.CharField(
        write_only=True,
        error_messages={
            "required": "Escribe la contraseña nueva",
            "blank": "Escribe la contraseña nueva",
        },
    )

    def validate_new_password(self, value: str) -> str:
        if len(value) < MIN_PASSWORD_LENGTH:
            raise serializers.ValidationError(
                "La contraseña debe tener al menos 8 caracteres"
            )
        return value


class DeleteAccountSerializer(serializers.Serializer):
    """Borrar la cuenta se confirma con la contraseña."""

    password = serializers.CharField(
        write_only=True,
        error_messages={
            "required": "Escribe tu contraseña para confirmar",
            "blank": "Escribe tu contraseña para confirmar",
        },
    )


class UserAccountSerializer(serializers.ModelSerializer):
    """Public representation of an account."""

    class Meta:
        model = User
        fields = ["id", "email", "is_email_verified"]
        read_only_fields = fields


class SubscriptionSerializer(serializers.ModelSerializer):
    """The account's plan and whether it is active."""

    class Meta:
        model = Subscription
        fields = ["plan", "status", "created_at"]
        read_only_fields = fields


#: Lo que puede pesar un logotipo. Es una marca, no una fotografía.
LOGO_MAX_BYTES = 2 * 1024 * 1024


class OrganizationSerializer(serializers.ModelSerializer):
    """The letterhead: name, color, logo and the contact the documents print.

    Every field is optional on input so the screen can save one without
    touching the others (``PATCH`` with just a color). The contact email and
    phone may be cleared: empty means the documents print no contact line.
    """

    name = serializers.CharField(
        max_length=120, required=False, allow_blank=True, trim_whitespace=True
    )
    color = serializers.CharField(
        max_length=7, required=False, validators=[HEX_COLOR_VALIDATOR]
    )

    email = serializers.EmailField(
        max_length=254,
        required=False,
        allow_blank=True,
        error_messages={"invalid": "Escribe un correo válido"},
    )
    phone = serializers.CharField(
        max_length=30, required=False, allow_blank=True, trim_whitespace=True
    )

    # Sube un archivo y se lee como dirección: el documento no carga bytes,
    # carga una imagen que ya está en la cuenta.
    logo = serializers.ImageField(required=False, allow_null=True)

    class Meta:
        model = Organization
        fields = ["name", "color", "logo", "email", "phone", "updated_at"]
        read_only_fields = ["updated_at"]

    def validate_logo(self, value):
        """Un logotipo es una imagen, y no una de varios megas."""
        if value in (None, ""):
            return None
        if value.size > LOGO_MAX_BYTES:
            raise serializers.ValidationError(
                f"El logotipo pesa más de {LOGO_MAX_BYTES // (1024 * 1024)} MB"
            )
        return value

    def to_representation(self, instance: Organization) -> dict:
        data = super().to_representation(instance)
        data["logo"] = instance.logo.url if instance.logo else None
        return data

    def validate_color(self, value: str) -> str:
        """One color, one spelling: #0f766e and #0F766E are the same ink."""
        return value.upper()


class MyAccountSerializer(serializers.ModelSerializer):
    """What the profile screen shows: the account, its plan and its letterhead.

    An account with no subscription reports ``null`` rather than failing: the
    screen has to be able to say «sin suscripción» instead of breaking. The
    organization is reported the same way — accounts created before it existed
    have none until they save one.
    """

    subscription = SubscriptionSerializer(read_only=True)
    organization = OrganizationSerializer(read_only=True)
    legal = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "is_email_verified",
            "pending_email",
            "legal",
            "created_at",
            "subscription",
            "organization",
        ]
        read_only_fields = fields

    def get_legal(self, obj: User) -> dict:
        """Qué documentos rigen, cuáles aceptó y si le falta aceptar alguno."""
        return status_for(obj)
