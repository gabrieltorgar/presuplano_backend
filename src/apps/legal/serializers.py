"""Legal serializers (input validation only; no business logic)."""

from rest_framework import serializers


class AcceptanceSerializer(serializers.Serializer):
    """Las versiones que la persona leyó y acepta."""

    terms_version = serializers.CharField(
        max_length=40,
        error_messages={
            "required": "Acepta los términos y condiciones para continuar.",
            "blank": "Acepta los términos y condiciones para continuar.",
        },
    )
    privacy_version = serializers.CharField(
        max_length=40,
        error_messages={
            "required": "Acepta la política de privacidad para continuar.",
            "blank": "Acepta la política de privacidad para continuar.",
        },
    )
