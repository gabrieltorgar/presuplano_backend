"""Leads serializers (input validation only)."""

from rest_framework import serializers

from apps.leads.models import MESSAGE_MAX_LENGTH, Lead


class LeadSerializer(serializers.ModelSerializer):
    """Un mensaje de contacto: nombre y alguna forma de responderle."""

    message = serializers.CharField(
        max_length=MESSAGE_MAX_LENGTH, required=False, allow_blank=True
    )

    class Meta:
        model = Lead
        fields = ["name", "phone", "email", "message"]

    def validate(self, attrs: dict) -> dict:
        """Un mensaje al que no se puede responder no sirve de nada."""
        if not attrs.get("phone") and not attrs.get("email"):
            raise serializers.ValidationError(
                "Déjanos un teléfono o un correo para poder responderte."
            )
        return attrs
