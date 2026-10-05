"""Quotes serializers (input validation + read shapes)."""

from decimal import Decimal

from rest_framework import serializers

from apps.catalog.models import Tariff
from apps.clients.models import Client
from apps.quotes.models import (
    MAX_VALIDITY_DAYS,
    NOTES_MAX_LENGTH,
    Quote,
    QuoteItem,
)


class QuoteItemInputSerializer(serializers.Serializer):
    """Validates one input line item (service + quantity + optional price).

    ``unit_price`` is what this quote charges for the service, which is not
    always its catalogue price: a negotiated figure, or a total agreed with the
    client and split across the quantity — hence six decimals, because that
    split does not always land on a whole cent.  Omitted, the catalogue price
    stands.

    Tariff/client ownership is enforced in the service layer.
    """

    tariff = serializers.PrimaryKeyRelatedField(queryset=Tariff.objects.all())
    quantity = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        error_messages={"invalid": "La cantidad debe ser mayor a 0"},
    )
    unit_price = serializers.DecimalField(
        max_digits=16,
        decimal_places=6,
        required=False,
        error_messages={"invalid": "El precio debe ser mayor a 0"},
    )

    def validate_quantity(self, value: Decimal) -> Decimal:
        if value <= 0:
            raise serializers.ValidationError("La cantidad debe ser mayor a 0")
        return value

    def validate_unit_price(self, value: Decimal) -> Decimal:
        if value <= 0:
            raise serializers.ValidationError("El precio debe ser mayor a 0")
        return value


class QuoteWriteSerializer(serializers.Serializer):
    """Validates a quote create/update payload (client, items and its terms).

    ``notes`` and ``validity_days`` are optional: a screen that does not send
    them —an older one still open— leaves what the quote already had.
    """

    client = serializers.PrimaryKeyRelatedField(queryset=Client.objects.all())
    items = QuoteItemInputSerializer(many=True)
    notes = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=NOTES_MAX_LENGTH,
        error_messages={
            "max_length": (
                f"Las observaciones no pueden pasar de {NOTES_MAX_LENGTH} caracteres"
            )
        },
    )
    validity_days = serializers.IntegerField(
        required=False,
        min_value=1,
        max_value=MAX_VALIDITY_DAYS,
        error_messages={
            "min_value": "La vigencia debe ser de al menos 1 día",
            "max_value": f"La vigencia no puede pasar de {MAX_VALIDITY_DAYS} días",
            "invalid": "La vigencia debe ser un número de días",
        },
    )

    def validate_items(self, value: list) -> list:
        if not value:
            raise serializers.ValidationError(
                "Agrega al menos una partida a la cotización"
            )
        return value


class QuoteItemSerializer(serializers.ModelSerializer):
    """Read shape of a line item, including its computed subtotal."""

    subtotal = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True)

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
            "notes",
            "validity_days",
            "created_at",
        ]

    def get_total(self, obj: Quote) -> Decimal:
        return sum((item.subtotal for item in obj.items.all()), Decimal("0"))
