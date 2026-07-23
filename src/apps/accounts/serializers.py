"""Accounts serializers (input validation only; no business logic)."""

from rest_framework import serializers

from apps.accounts.models import User

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


class UserAccountSerializer(serializers.ModelSerializer):
    """Public representation of an account."""

    class Meta:
        model = User
        fields = ["id", "phone", "is_phone_verified"]
        read_only_fields = fields
