"""Planner serializers."""

import json

from django.conf import settings
from rest_framework import serializers

from apps.planner.models import Plan


class PlanSummarySerializer(serializers.ModelSerializer):
    """What the plan list needs: no document.

    Painting five rows cannot cost five whole plans over a phone connection.
    """

    document_updated_at = serializers.SerializerMethodField()

    class Meta:
        model = Plan
        fields = ["id", "name", "created_at", "updated_at", "document_updated_at"]
        read_only_fields = fields

    def get_document_updated_at(self, plan: Plan) -> str | None:
        """When the editor stamped this plan, by the clock that drew it.

        The device decides which copy is newer, and comparing its own stamp
        against the server's clock would make that decision depend on how well
        the two agree.
        """
        document = plan.document if isinstance(plan.document, dict) else {}
        stamp = document.get("updatedAt")
        return stamp if isinstance(stamp, str) else None


class PlanSerializer(serializers.ModelSerializer):
    """A whole plan, document included."""

    name = serializers.CharField(
        max_length=150,
        error_messages={
            "blank": "El plano necesita un nombre",
            "required": "El plano necesita un nombre",
        },
    )

    # El editor ya le puso un id al plano —es el de su dirección— y el mismo
    # plano tiene que llamarse igual en el servidor y en cada dispositivo.
    id = serializers.UUIDField(required=False)

    class Meta:
        model = Plan
        fields = ["id", "name", "document", "created_at", "updated_at"]
        read_only_fields = ["created_at", "updated_at"]

    def validate_document(self, value):
        """Keep one scanned plan from taking the database down with it.

        A loose texture and the background scan travel inside the document as
        data URLs, which is what makes a plan heavy; the message says so,
        because «demasiado grande» leaves the architect with nothing to do.
        """
        if not isinstance(value, dict):
            raise serializers.ValidationError("El documento del plano no es válido")

        size = len(json.dumps(value).encode("utf-8"))
        if size > settings.PLAN_MAX_BYTES:
            limit = settings.PLAN_MAX_BYTES // (1024 * 1024)
            raise serializers.ValidationError(
                f"El plano pesa más de {limit} MB. Lo que más pesa suele ser el "
                "plano de fondo escaneado o una textura suelta."
            )
        return value
