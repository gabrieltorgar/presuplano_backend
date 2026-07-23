"""Clients serializers (input validation only)."""

from rest_framework import serializers

from apps.clients.models import Client


class ClientSerializer(serializers.ModelSerializer):
    """Serializes a client; enforces required name and valid email messages."""

    name = serializers.CharField(
        max_length=150,
        error_messages={
            "blank": "El nombre del cliente es obligatorio",
            "required": "El nombre del cliente es obligatorio",
        },
    )
    email = serializers.EmailField(
        required=False,
        allow_blank=True,
        error_messages={"invalid": "El correo no tiene un formato válido"},
    )

    class Meta:
        model = Client
        fields = ["id", "name", "phone", "email", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]
