"""Catalog serializers (input validation only)."""

from rest_framework import serializers

from apps.catalog.models import Tariff


class TariffSerializer(serializers.ModelSerializer):
    """Serializes a tariff; enforces name and positive price messages."""

    name = serializers.CharField(
        max_length=150,
        error_messages={
            "blank": "El nombre es obligatorio",
            "required": "El nombre es obligatorio",
        },
    )
    unit_price = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        error_messages={"invalid": "El precio debe ser un número mayor a 0"},
    )

    class Meta:
        model = Tariff
        fields = ["id", "name", "unit_type", "unit_price", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_unit_price(self, value):
        if value <= 0:
            raise serializers.ValidationError("El precio debe ser mayor a 0")
        return value
