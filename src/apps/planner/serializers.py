"""Planner serializers."""

import json

from django.conf import settings
from rest_framework import serializers

from apps.planner.models import Plan
from common.validators import IMAGES, validate_upload


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
        the two agree. The plan travels inside the editor's own envelope
        (``{format, version, plan}``), so the date is looked for there first.
        """
        document = plan.document if isinstance(plan.document, dict) else {}
        inner = document.get("plan")
        source = inner if isinstance(inner, dict) else document
        stamp = source.get("updatedAt")
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

    def validate_id(self, value):
        """El id se pone al crear el plano y no cambia después."""
        if self.instance is not None and value != self.instance.pk:
            raise serializers.ValidationError("El id de un plano no cambia.")
        return value

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


MEASURE_MUST_BE_POSITIVE = "La medida debe ser mayor que 0"


#: Lo que se convierte: PNG, JPG y WEBP (photo_conversion.SUPPORTED_FORMATS).
PHOTO_TYPES = {k: v for k, v in IMAGES.items() if v != "image/gif"}
#: Una foto de teléfono de 48 megapíxeles cabe; una bomba de descompresión, no.
PHOTO_MAX_PIXELS = 50_000_000
UNSUPPORTED_PHOTO = "Formato de imagen no admitido"


class PhotoInputSerializer(serializers.Serializer):
    """The photo of a paper plan, already shrunk by the browser (US-129)."""

    photo = serializers.FileField(
        error_messages={
            "required": "Sube la foto del plano",
            "empty": "Sube la foto del plano",
            "invalid": "Sube la foto del plano",
        }
    )

    # Las medidas totales que da el arquitecto cuando el plano no las trae
    # escritas (iteracion-7), y la decisión de seguir sin ellas.
    width_m = serializers.FloatField(
        required=False, error_messages={"invalid": MEASURE_MUST_BE_POSITIVE}
    )
    height_m = serializers.FloatField(
        required=False, error_messages={"invalid": MEASURE_MUST_BE_POSITIVE}
    )
    skip_measures = serializers.BooleanField(required=False, default=False)

    def validate_width_m(self, value: float) -> float:
        return self._positive(value)

    def validate_height_m(self, value: float) -> float:
        return self._positive(value)

    @staticmethod
    def _positive(value: float) -> float:
        if not value > 0:
            raise serializers.ValidationError(MEASURE_MUST_BE_POSITIVE)
        return value

    def measures(self) -> dict | None:
        """The sides the architect gave, in metres; None when none."""
        given = {
            side: self.validated_data[side]
            for side in ("width_m", "height_m")
            if side in self.validated_data
        }
        return given or None

    def validate_photo(self, value):
        """Una imagen de verdad, entera y que cabe (API-02, iteracion-26 #19).

        Antes sólo se medía: una foto con la firma bien y los datos rotos llegaba
        a Claude, o a un 500 al prepararla.
        """
        limit = settings.PHOTO_PLAN_MAX_BYTES
        validate_upload(
            value,
            allowed=PHOTO_TYPES,
            max_bytes=limit,
            max_pixels=PHOTO_MAX_PIXELS,
            too_big=f"La foto pesa más de {limit // (1024 * 1024)} MB",
            not_allowed=UNSUPPORTED_PHOTO,
        )
        return value
