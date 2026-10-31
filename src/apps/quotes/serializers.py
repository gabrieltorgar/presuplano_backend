"""Quotes serializers (input validation + read shapes)."""

from decimal import Decimal

from rest_framework import serializers

from apps.catalog.models import Tariff
from apps.clients.models import Client
from apps.planner.models import Plan
from apps.quotes.models import (
    MAX_ROOMS_PER_ITEM,
    MAX_VALIDITY_DAYS,
    NOTES_MAX_LENGTH,
    ROOM_NAME_MAX_LENGTH,
    Quote,
    QuoteItem,
    QuoteItemRoom,
)
from common.fields import OwnedPrimaryKeyRelatedField


class QuoteItemRoomInputSerializer(serializers.Serializer):
    """How much of a line falls in one room of the plan (iteracion-25)."""

    name = serializers.CharField(
        max_length=ROOM_NAME_MAX_LENGTH,
        error_messages={
            "blank": "Escribe el nombre de la habitación",
            "max_length": (
                "El nombre de la habitación no puede pasar de "
                f"{ROOM_NAME_MAX_LENGTH} caracteres"
            ),
        },
    )
    quantity = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        error_messages={"invalid": "La cantidad debe ser mayor a 0"},
    )

    def validate_quantity(self, value: Decimal) -> Decimal:
        if value <= 0:
            raise serializers.ValidationError("La cantidad debe ser mayor a 0")
        return value


class QuoteItemInputSerializer(serializers.Serializer):
    """Validates one input line item (service + quantity + optional price).

    ``unit_price`` is what this quote charges for the service, which is not
    always its catalogue price: a negotiated figure, or a total agreed with the
    client and split across the quantity — hence six decimals, because that
    split does not always land on a whole cent.  Omitted, the catalogue price
    stands.

    Only the writer's own tariffs and clients are found (the service checks
    again).
    """

    tariff = OwnedPrimaryKeyRelatedField(
        queryset=Tariff.objects.all(), not_found="Servicio no encontrado."
    )
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
    # La midió el plano (US-95). Sin decirlo, conserva lo que la partida era.
    from_plan = serializers.BooleanField(required=False)
    # Cuánto de ella cae en cada habitación del plano (iteracion-25). Sin
    # decirlo, al editar conserva el reparto que traía si la cantidad lo alcanza.
    rooms = QuoteItemRoomInputSerializer(
        many=True, required=False, max_length=MAX_ROOMS_PER_ITEM
    )

    def validate_quantity(self, value: Decimal) -> Decimal:
        if value <= 0:
            raise serializers.ValidationError("La cantidad debe ser mayor a 0")
        return value

    def validate_unit_price(self, value: Decimal) -> Decimal:
        if value <= 0:
            raise serializers.ValidationError("El precio debe ser mayor a 0")
        return value

    def validate(self, attrs: dict) -> dict:
        """The rooms of a line are each named once and never exceed the line."""
        rooms = attrs.get("rooms") or []
        names = [room["name"] for room in rooms]
        if len(set(names)) != len(names):
            raise serializers.ValidationError(
                {"rooms": ["Cada habitación va una sola vez en la partida"]}
            )
        if sum((room["quantity"] for room in rooms), Decimal("0")) > attrs["quantity"]:
            raise serializers.ValidationError(
                {
                    "rooms": [
                        "Lo repartido entre las habitaciones no puede pasar de la "
                        "cantidad de la partida"
                    ]
                }
            )
        return attrs


class QuoteWriteSerializer(serializers.Serializer):
    """Validates a quote create/update payload (client, items and its terms).

    ``notes`` and ``validity_days`` are optional: a screen that does not send
    them —an older one still open— leaves what the quote already had.
    """

    client = OwnedPrimaryKeyRelatedField(
        queryset=Client.objects.all(), not_found="Cliente no encontrado."
    )
    items = QuoteItemInputSerializer(many=True)
    # El plano del que sale (US-95), de la cuenta de quien cotiza.
    plan = OwnedPrimaryKeyRelatedField(
        queryset=Plan.objects.all(),
        not_found="Plano no encontrado.",
        required=False,
        allow_null=True,
    )
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


class PlanSyncSerializer(serializers.Serializer):
    """What the plan measures now, to bring its quote up to date (US-95)."""

    plan = OwnedPrimaryKeyRelatedField(
        queryset=Plan.objects.all(), not_found="Plano no encontrado."
    )
    items = QuoteItemInputSerializer(many=True)


class QuoteItemRoomSerializer(serializers.ModelSerializer):
    """Read shape of a line's share in one room: its amount is the document's."""

    class Meta:
        model = QuoteItemRoom
        fields = ["name", "quantity"]


class QuoteItemSerializer(serializers.ModelSerializer):
    """Read shape of a line item, including its computed subtotal."""

    subtotal = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True)
    rooms = QuoteItemRoomSerializer(many=True, read_only=True)

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
            "from_plan",
            "rooms",
        ]


class QuoteSerializer(serializers.ModelSerializer):
    """Read shape of a quote with its items and automatic total."""

    items = QuoteItemSerializer(many=True, read_only=True)
    client_name = serializers.CharField(source="client.name", read_only=True)
    plan_name = serializers.CharField(source="plan.name", read_only=True, default=None)
    total = serializers.SerializerMethodField()

    class Meta:
        model = Quote
        fields = [
            "id",
            "folio",
            "client",
            "client_name",
            "status",
            "plan",
            "plan_name",
            "items",
            "total",
            "notes",
            "validity_days",
            "created_at",
        ]
        # Forma de lectura: crear y editar pasan por QuoteWriteSerializer, y el
        # estado lo cambia sólo la conversión en proyecto (SEC-03).
        read_only_fields = ["folio", "status", "created_at"]

    def get_total(self, obj: Quote) -> Decimal:
        return sum((item.subtotal for item in obj.items.all()), Decimal("0"))
