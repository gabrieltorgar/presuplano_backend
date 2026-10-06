"""Planner views: account-scoped plan CRUD and photo conversion."""

from django.conf import settings
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import APIException
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from apps.planner import photo_conversion
from apps.planner.selectors import list_plans_for_owner
from apps.planner.serializers import (
    PhotoInputSerializer,
    PlanSerializer,
    PlanSummarySerializer,
)


class DailyPhotoLimitReached(APIException):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    default_code = "photo_limit"


class PhotoServiceUnavailable(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = (
        "No pudimos convertir la foto ahora. Inténtalo de nuevo en unos minutos."
    )
    default_code = "photo_unavailable"


class PlanViewSet(viewsets.ModelViewSet):
    """CRUD for the authenticated account's plans (isolated per account)."""

    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return list_plans_for_owner(owner=self.request.user)

    def get_serializer_class(self):
        return PlanSummarySerializer if self.action == "list" else PlanSerializer

    def perform_create(self, serializer) -> None:
        serializer.save(owner=self.request.user)

    @action(
        detail=False,
        methods=["post"],
        url_path="photo-conversions",
        parser_classes=[MultiPartParser, FormParser],
    )
    def photo_conversions(self, request: Request) -> Response:
        """US-129: the walls and rooms of a photo of a paper plan.

        They come back relative to the photo (0 to 1), to be laid over it.
        """
        serializer = PhotoInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        limit = settings.PHOTO_PLAN_DAILY_LIMIT
        if photo_conversion.conversions_today(request.user) >= limit:
            raise DailyPhotoLimitReached(
                f"Llegaste al límite de {limit} fotos por día. "
                "Vuelve a intentarlo mañana."
            )

        try:
            result = photo_conversion.convert_photo(
                owner=request.user, data=serializer.validated_data["photo"].read()
            )
        except photo_conversion.UnsupportedPhoto as error:
            raise serializers.ValidationError(
                {"photo": ["Formato de imagen no admitido"]}
            ) from error
        except photo_conversion.ConversionUnavailable as error:
            raise PhotoServiceUnavailable() from error
        return Response(result)
