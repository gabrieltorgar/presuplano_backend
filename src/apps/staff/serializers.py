"""Staff serializers (input validation + read shapes)."""

from rest_framework import serializers

from apps.catalog.models import Tariff
from apps.projects.models import Project
from apps.quotes.models import QuoteItem
from apps.staff.models import Assignment, Worker, WorkerPayment
from apps.staff.selectors import worker_totals
from common.money import money


class WorkerServiceInputSerializer(serializers.Serializer):
    """Un servicio que hace esa persona, y a cómo se le paga."""

    tariff = serializers.PrimaryKeyRelatedField(queryset=Tariff.objects.all())
    unit_price = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, allow_null=True
    )


class WorkerSerializer(serializers.ModelSerializer):
    """Read/write shape of a worker, with what it costs and what is owed."""

    name = serializers.CharField(
        max_length=150,
        error_messages={
            "blank": "El nombre es obligatorio",
            "required": "El nombre es obligatorio",
        },
    )
    services = WorkerServiceInputSerializer(many=True, required=False)
    committed_value = serializers.SerializerMethodField()
    accrued_value = serializers.SerializerMethodField()
    total_paid = serializers.SerializerMethodField()
    balance = serializers.SerializerMethodField()
    advance_balance = serializers.SerializerMethodField()

    class Meta:
        model = Worker
        fields = [
            "id",
            "kind",
            "name",
            "phone",
            "email",
            "notes",
            "is_self",
            "is_active",
            "services",
            "committed_value",
            "accrued_value",
            "total_paid",
            "balance",
            "advance_balance",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def _totals(self, obj: Worker) -> dict:
        # Una sola cuenta por objeto, aunque la pidan los cinco campos.
        cache = self.context.setdefault("totals", {})
        if obj.pk not in cache:
            cache[obj.pk] = worker_totals(obj)
        return cache[obj.pk]

    def get_committed_value(self, obj: Worker):
        return self._totals(obj)["committed_value"]

    def get_accrued_value(self, obj: Worker):
        return self._totals(obj)["accrued_value"]

    def get_total_paid(self, obj: Worker):
        return self._totals(obj)["total_paid"]

    def get_balance(self, obj: Worker):
        return self._totals(obj)["balance"]

    def get_advance_balance(self, obj: Worker):
        return self._totals(obj)["advance_balance"]

    def to_representation(self, instance: Worker) -> dict:
        data = super().to_representation(instance)
        data["services"] = [
            {
                "id": str(service.id),
                "tariff": str(service.tariff_id),
                "tariff_name": service.tariff.name,
                "unit_type": service.tariff.unit_type,
                # Como cadena, igual que el resto del dinero de esta API: un
                # decimal renderizado a JSON sale como flotante y el formulario
                # lo recibe con otro tipo del que dice tener.
                "unit_price": (
                    None if service.unit_price is None else money(service.unit_price)
                ),
            }
            for service in instance.services.all()
        ]
        return data


class AssignmentInputSerializer(serializers.Serializer):
    """Validates a hand-out: which item, to whom, how much and at what price."""

    project = serializers.PrimaryKeyRelatedField(queryset=Project.objects.all())
    quote_item = serializers.PrimaryKeyRelatedField(queryset=QuoteItem.objects.all())
    worker = serializers.PrimaryKeyRelatedField(queryset=Worker.objects.all())
    quantity = serializers.DecimalField(max_digits=12, decimal_places=2)
    unit_price = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, allow_null=True
    )
    note = serializers.CharField(max_length=255, required=False, allow_blank=True)


class AssignmentSerializer(serializers.ModelSerializer):
    """Read shape of a hand-out."""

    worker_name = serializers.CharField(source="worker.name", read_only=True)
    item_name = serializers.CharField(source="quote_item.name", read_only=True)
    committed_value = serializers.DecimalField(
        max_digits=14, decimal_places=2, read_only=True
    )

    class Meta:
        model = Assignment
        fields = [
            "id",
            "project",
            "quote_item",
            "item_name",
            "worker",
            "worker_name",
            "quantity",
            "unit_price",
            "committed_value",
            "note",
            "created_at",
        ]


class WorkerPaymentInputSerializer(serializers.Serializer):
    """Validates a payment to a worker."""

    worker = serializers.PrimaryKeyRelatedField(queryset=Worker.objects.all())
    project = serializers.PrimaryKeyRelatedField(
        queryset=Project.objects.all(), required=False, allow_null=True
    )
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    method = serializers.ChoiceField(
        choices=WorkerPayment.Method.choices,
        required=False,
        default=WorkerPayment.Method.CASH,
    )
    date = serializers.DateField()
    note = serializers.CharField(max_length=255, required=False, allow_blank=True)


class WorkerPaymentSerializer(serializers.ModelSerializer):
    """Read shape of a payment to a worker."""

    worker_name = serializers.CharField(source="worker.name", read_only=True)

    class Meta:
        model = WorkerPayment
        fields = [
            "id",
            "worker",
            "worker_name",
            "project",
            "amount",
            "method",
            "date",
            "note",
            "created_at",
        ]
