"""Accounts serializers (input validation only; no business logic)."""

from rest_framework import serializers

from apps.accounts.models import HEX_COLOR_VALIDATOR, Organization, Subscription, User

MIN_PASSWORD_LENGTH = 8


class IdentitySerializer(serializers.Serializer):
    """Una identidad: el teléfono, el correo, o los dos.

    Se valida aquí, y no en cada pantalla, que venga al menos uno: una cuenta
    sin ninguno de los dos no tendría por dónde entrar nunca más.
    """

    phone = serializers.CharField(
        max_length=20, required=False, allow_blank=True, allow_null=True
    )
    email = serializers.EmailField(required=False, allow_blank=True, allow_null=True)

    def validate(self, attrs: dict) -> dict:
        if (
            not (attrs.get("phone") or "").strip()
            and not (attrs.get("email") or "").strip()
        ):
            raise serializers.ValidationError(
                "Escribe tu teléfono o tu correo para continuar"
            )
        return attrs


class RegisterSerializer(IdentitySerializer):
    """Validates registration input: identity, uniqueness and password length."""

    password = serializers.CharField(write_only=True, style={"input_type": "password"})

    def validate_phone(self, value: str) -> str:
        if value and User.objects.filter(phone=value.strip()).exists():
            raise serializers.ValidationError("Ese teléfono ya está registrado")
        return value

    def validate_email(self, value: str) -> str:
        if value and User.objects.filter(email__iexact=value.strip()).exists():
            raise serializers.ValidationError("Ese correo ya está registrado")
        return value

    def validate_password(self, value: str) -> str:
        if len(value) < MIN_PASSWORD_LENGTH:
            raise serializers.ValidationError(
                "La contraseña debe tener al menos 8 caracteres"
            )
        return value


class IdentifierSerializer(serializers.Serializer):
    """Quién dice ser: un teléfono o un correo, en un solo campo.

    Acepta ``identifier`` y también el viejo ``phone``: las pantallas
    publicadas siguen mandando ese nombre y no hay por qué dejarlas fuera.
    """

    identifier = serializers.CharField(max_length=254, required=False)
    phone = serializers.CharField(max_length=254, required=False)
    email = serializers.CharField(max_length=254, required=False)

    def validate(self, attrs: dict) -> dict:
        identifier = (
            attrs.get("identifier") or attrs.get("email") or attrs.get("phone") or ""
        ).strip()
        if not identifier:
            raise serializers.ValidationError(
                "Escribe tu teléfono o tu correo para continuar"
            )
        return {"identifier": identifier}


class VerifyOtpSerializer(IdentifierSerializer):
    """Validates OTP verification input."""

    code = serializers.CharField(max_length=6)

    def validate(self, attrs: dict) -> dict:
        code = attrs.get("code", "")
        return {**super().validate(attrs), "code": code}


class ResendOtpSerializer(IdentifierSerializer):
    """Reenviar el código: basta con la identidad de la cuenta."""


class PasswordResetRequestSerializer(IdentifierSerializer):
    """Pedir recuperar: sólo hace falta la identidad de la cuenta."""


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


class LoginSerializer(IdentifierSerializer):
    """Validates login input."""

    password = serializers.CharField(write_only=True, style={"input_type": "password"})

    def validate(self, attrs: dict) -> dict:
        password = attrs.get("password", "")
        return {**super().validate(attrs), "password": password}


class UpdateMyAccountSerializer(serializers.Serializer):
    """Lo que el perfil deja cambiar de la cuenta: cómo se entra a ella."""

    phone = serializers.CharField(
        max_length=20, required=False, allow_blank=True, allow_null=True
    )
    email = serializers.EmailField(required=False, allow_blank=True, allow_null=True)


class UserAccountSerializer(serializers.ModelSerializer):
    """Public representation of an account."""

    class Meta:
        model = User
        fields = ["id", "phone", "email", "is_phone_verified", "is_email_verified"]
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
            "email",
            "is_phone_verified",
            "is_email_verified",
            "created_at",
            "subscription",
            "organization",
        ]
        read_only_fields = fields
