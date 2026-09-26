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
    quotes_count = serializers.SerializerMethodField()

    class Meta:
        model = Client
        fields = [
            "id",
            "name",
            "phone",
            "email",
            "quotes_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_quotes_count(self, obj: Client) -> int:
        """En cuántas cotizaciones está; mientras sea más de cero, no se borra."""
        annotated = getattr(obj, "quotes_count", None)
        return annotated if annotated is not None else obj.quotes.count()
