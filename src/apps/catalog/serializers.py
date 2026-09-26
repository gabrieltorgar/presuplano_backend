"""Catalog serializers (input validation only)."""

from rest_framework import serializers

from apps.catalog.models import Tariff
from apps.catalog.services import quotes_using


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

    description = serializers.CharField(
        required=False, allow_blank=True, default="", trim_whitespace=False
    )
    quotes_count = serializers.SerializerMethodField()

    class Meta:
        model = Tariff
        fields = [
            "id",
            "name",
            "description",
            "unit_type",
            "unit_price",
            "in_catalog",
            "quotes_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_quotes_count(self, obj: Tariff) -> int:
        """En cuántas cotizaciones está; mientras sea más de cero, no se borra."""
        annotated = getattr(obj, "quotes_count", None)
        return annotated if annotated is not None else quotes_using(obj)

    def validate_unit_price(self, value):
        if value <= 0:
            raise serializers.ValidationError("El precio debe ser mayor a 0")
        return value
