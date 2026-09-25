"""Accounts serializers (input validation only; no business logic)."""

from rest_framework import serializers

from apps.accounts.models import HEX_COLOR_VALIDATOR, Organization, Subscription, User

MIN_PASSWORD_LENGTH = 8


class RegisterSerializer(serializers.Serializer):
    """Validates registration input: phone uniqueness and password length."""

    phone = serializers.CharField(max_length=20)
    password = serializers.CharField(write_only=True, style={"input_type": "password"})

    def validate_phone(self, value: str) -> str:
        if User.objects.filter(phone=value).exists():
            raise serializers.ValidationError("Ese teléfono ya está registrado")
        return value

    def validate_password(self, value: str) -> str:
        if len(value) < MIN_PASSWORD_LENGTH:
            raise serializers.ValidationError(
                "La contraseña debe tener al menos 8 caracteres"
            )
        return value


class VerifyOtpSerializer(serializers.Serializer):
    """Validates OTP verification input."""

    phone = serializers.CharField(max_length=20)
    code = serializers.CharField(max_length=6)


class ResendOtpSerializer(serializers.Serializer):
    """Reenviar el código: basta el teléfono, que es la identidad de la cuenta."""

    phone = serializers.CharField(max_length=20)


class PasswordResetRequestSerializer(serializers.Serializer):
    """Pedir recuperar: solo hace falta el teléfono, que es la identidad."""

    phone = serializers.CharField(max_length=20)


class PasswordResetConfirmSerializer(serializers.Serializer):
    """Confirmar la recuperación con el código y la contraseña nueva."""

    phone = serializers.CharField(max_length=20)
    code = serializers.CharField(max_length=6)
    password = serializers.CharField(write_only=True, style={"input_type": "password"})

    def validate_password(self, value: str) -> str:
        if len(value) < MIN_PASSWORD_LENGTH:
            raise serializers.ValidationError(
                "La contraseña debe tener al menos 8 caracteres"
            )
        return value


class LoginSerializer(serializers.Serializer):
    """Validates login input."""

    phone = serializers.CharField(max_length=20)
    password = serializers.CharField(write_only=True, style={"input_type": "password"})


class UserAccountSerializer(serializers.ModelSerializer):
    """Public representation of an account."""

    class Meta:
        model = User
        fields = ["id", "phone", "is_phone_verified"]
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
    """The letterhead: the name and the color the documents are printed with.

    Both fields are optional on input so the screen can save one without
    touching the other (``PATCH`` with just a color).
    """

    name = serializers.CharField(
        max_length=120, required=False, allow_blank=True, trim_whitespace=True
    )
    color = serializers.CharField(
        max_length=7, required=False, validators=[HEX_COLOR_VALIDATOR]
    )

    # Sube un archivo y se lee como dirección: el documento no carga bytes,
    # carga una imagen que ya está en la cuenta.
    logo = serializers.ImageField(required=False, allow_null=True)

    class Meta:
        model = Organization
        fields = ["name", "color", "logo", "updated_at"]
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

    class Meta:
        model = User
        fields = [
            "id",
            "phone",
            "is_phone_verified",
            "created_at",
            "subscription",
            "organization",
        ]
        read_only_fields = fields
