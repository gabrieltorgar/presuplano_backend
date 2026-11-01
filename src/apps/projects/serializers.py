"""Projects serializers (input validation + read shapes)."""

from decimal import Decimal

from rest_framework import serializers

from apps.projects.models import Evidence, Progress, Project
from apps.projects.selectors import advanced_value, quoted_value
from apps.quotes.models import Quote, QuoteItem
from apps.staff.models import Worker
from common.fields import OwnedPrimaryKeyRelatedField


class StartProjectSerializer(serializers.Serializer):
    """Validates the payload to start a project (a quote id)."""

    quote = OwnedPrimaryKeyRelatedField(
        queryset=Quote.objects.all(), not_found="Cotización no encontrada."
    )


class ProgressInputSerializer(serializers.Serializer):
    """Validates a progress entry (quantity + date + who did it)."""

    quote_item = OwnedPrimaryKeyRelatedField(
        queryset=QuoteItem.objects.all(),
        owner_field="quote__owner",
        not_found="Partida no encontrada.",
    )
    quantity = serializers.DecimalField(max_digits=12, decimal_places=2)
    date = serializers.DateField()
    worker = OwnedPrimaryKeyRelatedField(
        queryset=Worker.objects.all(),
        not_found="Personal no encontrado.",
        required=False,
        allow_null=True,
    )


class ProgressSerializer(serializers.ModelSerializer):
    """Read shape of a progress entry with its earned value."""

    earned_value = serializers.DecimalField(
        max_digits=14, decimal_places=2, read_only=True
    )

    class Meta:
        model = Progress
        fields = [
            "id",
            "quote_item",
            "quantity",
            "date",
            "earned_value",
            "worker",
            "labor_unit_price",
        ]
        # Lo copia el servicio del reparto de quien lo hizo (VAL-05).
        read_only_fields = ["labor_unit_price"]


class ProgressUpdateSerializer(serializers.Serializer):
    """Una corrección de avance: cualquiera de los tres, ninguno obligatorio."""

    quantity = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)
    date = serializers.DateField(required=False)
    worker = OwnedPrimaryKeyRelatedField(
        queryset=Worker.objects.all(),
        not_found="Personal no encontrado.",
        required=False,
        allow_null=True,
    )


def absolute_media_url(file, request) -> str:
    """La dirección de un archivo, completa aunque el almacenamiento sea local.

    En producción el almacenamiento ya da una dirección pública completa; en
    local da una ruta, que sin el host no se puede abrir desde la aplicación.
    """
    url = file.url
    if request is not None and url.startswith("/"):
        return request.build_absolute_uri(url)
    return url


class EvidenceSerializer(serializers.ModelSerializer):
    """Una foto de un avance, con la dirección desde la que se ve."""

    image = serializers.SerializerMethodField()

    class Meta:
        model = Evidence
        fields = ["id", "progress", "image", "created_at"]

    def get_image(self, obj: Evidence) -> str:
        return absolute_media_url(obj.image, self.context.get("request"))


class ProjectListSerializer(serializers.ModelSerializer):
    """A row of the projects list: its values, no lines, progress or photos.

    US-67 (iteracion-17): the list brings what the table shows; the progress
    entries and their photos come with each project, on its own screen.
    """

    client_name = serializers.CharField(source="quote.client.name", read_only=True)
    quoted_value = serializers.SerializerMethodField()
    advanced_value = serializers.SerializerMethodField()
    progress_percentage = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = [
            "id",
            "folio",
            "quote",
            "client_name",
            "status",
            "quoted_value",
            "advanced_value",
            "progress_percentage",
            "created_at",
        ]
        # El estado lo cambia sólo finalizar, y la cotización de origen no
        # cambia nunca: un proyecto nace de una sola (SEC-03).
        read_only_fields = ["folio", "quote", "status", "created_at"]

    def get_quoted_value(self, obj: Project) -> Decimal:
        return quoted_value(obj)

    def get_advanced_value(self, obj: Project) -> Decimal:
        return advanced_value(obj)

    def get_progress_percentage(self, obj: Project) -> float:
        quoted = quoted_value(obj)
        if quoted == 0:
            return 0.0
        return round(float(advanced_value(obj) / quoted * 100), 2)


class ProjectSerializer(ProjectListSerializer):
    """Read shape of a project with quoted/advanced/percentage values."""

    items = serializers.SerializerMethodField()
    progresses = serializers.SerializerMethodField()

    class Meta(ProjectListSerializer.Meta):
        fields = [
            "id",
            "folio",
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
        read_only_fields = ["folio", "quote", "status", "created_at"]

    def get_progresses(self, obj: Project) -> list[dict]:
        """Lo registrado en obra, avance por avance, con sus fotos.

        Es lo que muestra la pantalla del proyecto para revisar y corregir, y lo
        que lee el documento de estado.
        """
        request = self.context.get("request")
        return [
            {
                "id": str(progress.id),
                "quote_item": str(progress.quote_item_id),
                "date": str(progress.date),
                "item": progress.quote_item.name,
                "unit_type": progress.quote_item.unit_type,
                "quantity": str(progress.quantity),
                "earned_value": str(progress.earned_value.quantize(Decimal("0.01"))),
                "worker": str(progress.worker_id) if progress.worker_id else None,
                "worker_name": progress.worker.name if progress.worker_id else "",
                "evidence": [
                    {
                        "id": str(evidence.id),
                        "image": absolute_media_url(evidence.image, request),
                        "created_at": evidence.created_at.isoformat(),
                    }
                    for evidence in progress.evidences.all()
                ],
            }
            for progress in obj.progresses.all()
        ]

    def get_items(self, obj: Project) -> list[dict]:
        """Line items with their pending (still-registerable) quantity."""
        items = []
        for item in obj.quote.items.all():
            advanced = sum((p.quantity for p in item.progresses.all()), Decimal("0"))
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
