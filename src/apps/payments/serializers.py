"""Payments serializers (input validation + read shapes)."""

from rest_framework import serializers

from apps.payments.models import Payment
from apps.projects.models import Project
from apps.quotes.models import QuoteItem


class PaymentInputSerializer(serializers.Serializer):
    """Validates a payment payload."""

    project = serializers.PrimaryKeyRelatedField(queryset=Project.objects.all())
    quote_item = serializers.PrimaryKeyRelatedField(
        queryset=QuoteItem.objects.all(), required=False, allow_null=True
    )
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    date = serializers.DateField()


class PaymentSerializer(serializers.ModelSerializer):
    """Read shape of a payment."""

    class Meta:
        model = Payment
        fields = ["id", "project", "quote_item", "amount", "date", "created_at"]
