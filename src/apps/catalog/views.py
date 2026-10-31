"""Catalog views: account-scoped tariff CRUD."""

from rest_framework import viewsets
from rest_framework.decorators import action

from apps.catalog.filters import TariffFilter
from apps.catalog.selectors import list_tariffs_for_owner
from apps.catalog.serializers import TariffSerializer
from apps.catalog.services import delete_tariff, delete_tariffs
from apps.team.tenancy import account_of
from common.bulk import BulkActionMixin
from common.permissions import IsVerifiedUser


class TariffViewSet(BulkActionMixin, viewsets.ModelViewSet):
    """CRUD for the authenticated account's tariffs (isolated per account).

    GET /api/tariffs/?search=piso&unit_type=square_meter,unit&ordering=-unit_price
    """

    serializer_class = TariffSerializer
    permission_classes = [IsVerifiedUser]
    filterset_class = TariffFilter
    search_fields = ("name", "description")
    ordering_fields = ("name", "unit_price", "created_at")
    ordering_text_fields = ("name",)
    ordering = ("name", "id")

    def get_queryset(self):
        return list_tariffs_for_owner(owner=account_of(self.request))

    def perform_create(self, serializer) -> None:
        serializer.save(owner=account_of(self.request))

    def perform_destroy(self, instance) -> None:
        delete_tariff(tariff=instance)

    @action(
        detail=False, methods=["post"], url_path="bulk/delete", throttle_scope="bulk"
    )
    def bulk_delete(self, request):
        """POST /api/tariffs/bulk/delete/[?<query string de la lista>] → BulkResult."""
        tariffs = self.get_bulk_queryset(request)
        return self.bulk_response(delete_tariffs(tariffs=tariffs))
