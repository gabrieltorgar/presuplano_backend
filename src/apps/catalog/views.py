"""Catalog views: account-scoped tariff CRUD."""

from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from apps.catalog.selectors import list_tariffs_for_owner
from apps.catalog.serializers import TariffSerializer


class TariffViewSet(viewsets.ModelViewSet):
    """CRUD for the authenticated account's tariffs (isolated per account)."""

    serializer_class = TariffSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return list_tariffs_for_owner(owner=self.request.user)

    def perform_create(self, serializer) -> None:
        serializer.save(owner=self.request.user)
