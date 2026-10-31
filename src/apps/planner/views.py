"""Planner views: account-scoped plan CRUD and photo conversion."""

from django.conf import settings
from rest_framework import serializers, status
from rest_framework.decorators import action
from rest_framework.exceptions import APIException
from rest_framework.parsers import MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response

from apps.planner import photo_conversion
from apps.planner.filters import PlanFilter
from apps.planner.selectors import list_plans_for_owner
from apps.planner.serializers import (
    PhotoInputSerializer,
    PlanSerializer,
    PlanSummarySerializer,
)
from apps.planner.services import delete_plans
from apps.team.tenancy import account_of
from common.bulk import BulkActionMixin
from common.permissions import IsVerifiedUser
from common.views import TenantModelViewSet


class DailyPhotoLimitReached(APIException):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    default_code = "photo_limit"


class PhotoServiceUnavailable(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = (
        "No pudimos convertir la foto ahora. Inténtalo de nuevo en unos minutos."
    )
    default_code = "photo_unavailable"


class PlanViewSet(BulkActionMixin, TenantModelViewSet):
    """CRUD for the authenticated account's plans (isolated per account).

    The list (US-78, iteracion-17) is summaries without the document, by pages:
    the device walks them a hundred at a time to catch up, and only downloads
    the document of the plans it opens or that changed. It searches by name
    and orders by last change or name, the one touched last first by default.
    """

    permission_classes = [IsVerifiedUser]
    filterset_class = PlanFilter
    search_fields = ("name",)
    ordering_fields = ("updated_at", "name")
    ordering_text_fields = ("name",)
    ordering = ("-updated_at", "-id")

    def get_queryset(self):
        return list_plans_for_owner(owner=account_of(self.request))

    def get_serializer_class(self):
        return PlanSummarySerializer if self.action == "list" else PlanSerializer

    def perform_create(self, serializer) -> None:
        serializer.save(owner=account_of(self.request))

    @action(
        detail=False, methods=["post"], url_path="bulk/delete", throttle_scope="bulk"
    )
    def bulk_delete(self, request):
        """POST /api/plans/bulk/delete/[?<query string de la lista>] → BulkResult."""
        plans = self.get_bulk_queryset(request)
        return self.bulk_response(delete_plans(plans=plans))

    @action(
        detail=False,
        methods=["post"],
        url_path="photo-conversions",
        parser_classes=[MultiPartParser],
        # Cada foto la lee un servicio de pago (iteracion-26 #16).
        throttle_scope="costly",
    )
    def photo_conversions(self, request: Request) -> Response:
        """US-129: the walls and rooms of a photo of a paper plan.

        They come back relative to the photo (0 to 1), to be laid over it, with
        the scale when it is known. When the plan has not its width or its
        height written, the answer asks for them instead (``needs_measures``).
        """
        serializer = PhotoInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        limit = settings.PHOTO_PLAN_DAILY_LIMIT
        if photo_conversion.conversions_today(account_of(request)) >= limit:
            raise DailyPhotoLimitReached(
                f"Llegaste al límite de {limit} fotos por día. "
                "Vuelve a intentarlo mañana."
            )

        try:
            result = photo_conversion.convert_photo(
                owner=account_of(request),
                data=serializer.validated_data["photo"].read(),
                measures=serializer.measures(),
                skip_measures=serializer.validated_data["skip_measures"],
            )
        except photo_conversion.UnsupportedPhoto as error:
            raise serializers.ValidationError(
                {"photo": ["Formato de imagen no admitido"]}
            ) from error
        except photo_conversion.ConversionUnavailable as error:
            raise PhotoServiceUnavailable() from error
        return Response(result)
