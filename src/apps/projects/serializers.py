"""Projects serializers (input validation + read shapes)."""

from decimal import Decimal

from rest_framework import serializers

from apps.projects.models import Evidence, Progress, Project
from apps.projects.selectors import advanced_value, quoted_value
from apps.quotes.models import Quote, QuoteItem


class StartProjectSerializer(serializers.Serializer):
    """Validates the payload to start a project (a quote id)."""

    quote = serializers.PrimaryKeyRelatedField(queryset=Quote.objects.all())


class ProgressInputSerializer(serializers.Serializer):
    """Validates a progress entry (quantity + date). Percentage removed in v1.1."""

    quote_item = serializers.PrimaryKeyRelatedField(queryset=QuoteItem.objects.all())
    quantity = serializers.DecimalField(max_digits=12, decimal_places=2)
    date = serializers.DateField()


class ProgressSerializer(serializers.ModelSerializer):
    """Read shape of a progress entry with its earned value."""

    earned_value = serializers.DecimalField(
        max_digits=14, decimal_places=2, read_only=True
    )

    class Meta:
        model = Progress
        fields = ["id", "quote_item", "quantity", "date", "earned_value"]


class EvidenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Evidence
        fields = ["id", "progress", "image"]


class ProjectSerializer(serializers.ModelSerializer):
    """Read shape of a project with quoted/advanced/percentage values."""

    client_name = serializers.CharField(source="quote.client.name", read_only=True)
    quoted_value = serializers.SerializerMethodField()
    advanced_value = serializers.SerializerMethodField()
    progress_percentage = serializers.SerializerMethodField()
    items = serializers.SerializerMethodField()
    progresses = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = [
            "id",
            "quote",
            "client_name",
            "status",
            "quoted_value",
            "advanced_value",
            "progress_percentage",
            "items",
            "progresses",
            "created_at",
        ]

    def get_progresses(self, obj: Project) -> list[dict]:
        """Recorded advances (for the project status document)."""
        return [
            {
                "date": str(progress.date),
                "item": progress.quote_item.name,
                "quantity": str(progress.quantity),
            }
            for progress in obj.progresses.all()
        ]

    def get_items(self, obj: Project) -> list[dict]:
        """Line items with their pending (still-registerable) quantity."""
        items = []
        for item in obj.quote.items.all():
            advanced = sum(
                (p.quantity for p in item.progresses.all()), Decimal("0")
            )
            items.append(
                {
                    "id": str(item.id),
                    "name": item.name,
                    "unit_type": item.unit_type,
                    "quantity": str(item.quantity),
                    "pending_quantity": str(item.quantity - advanced),
                }
            )
        return items

    def get_quoted_value(self, obj: Project) -> Decimal:
        return quoted_value(obj)

    def get_advanced_value(self, obj: Project) -> Decimal:
        return advanced_value(obj)

    def get_progress_percentage(self, obj: Project) -> float:
        quoted = quoted_value(obj)
        if quoted == 0:
            return 0.0
        return round(float(advanced_value(obj) / quoted * 100), 2)
