"""Quotes serializers (input validation + read shapes)."""

from decimal import Decimal

from rest_framework import serializers

from apps.catalog.models import Tariff
from apps.clients.models import Client
from apps.quotes.models import Quote, QuoteItem


class QuoteItemInputSerializer(serializers.Serializer):
    """Validates one input line item (tariff + quantity).

    Tariff/client ownership is enforced in the service layer.
    """

    tariff = serializers.PrimaryKeyRelatedField(queryset=Tariff.objects.all())
    quantity = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        error_messages={"invalid": "La cantidad debe ser mayor a 0"},
    )

    def validate_quantity(self, value: Decimal) -> Decimal:
        if value <= 0:
            raise serializers.ValidationError("La cantidad debe ser mayor a 0")
        return value


class QuoteWriteSerializer(serializers.Serializer):
    """Validates a quote create/update payload (client + items)."""

    client = serializers.PrimaryKeyRelatedField(queryset=Client.objects.all())
    items = QuoteItemInputSerializer(many=True)

    def validate_items(self, value: list) -> list:
        if not value:
            raise serializers.ValidationError(
                "Agrega al menos una partida a la cotización"
            )
        return value


class QuoteItemSerializer(serializers.ModelSerializer):
    """Read shape of a line item, including its computed subtotal."""

    subtotal = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model = QuoteItem
        fields = [
            "id",
            "tariff",
            "name",
            "unit_type",
            "unit_price",
            "quantity",
            "subtotal",
        ]


class QuoteSerializer(serializers.ModelSerializer):
    """Read shape of a quote with its items and automatic total."""

    items = QuoteItemSerializer(many=True, read_only=True)
    client_name = serializers.CharField(source="client.name", read_only=True)
    total = serializers.SerializerMethodField()

    class Meta:
        model = Quote
        fields = [
            "id",
            "client",
            "client_name",
            "status",
            "items",
            "total",
            "created_at",
        ]

    def get_total(self, obj: Quote) -> Decimal:
        return sum((item.subtotal for item in obj.items.all()), Decimal("0"))
