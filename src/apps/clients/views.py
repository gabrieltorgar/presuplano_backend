"""Clients views: account-scoped client CRUD."""

from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from apps.clients.selectors import list_clients_for_owner
from apps.clients.serializers import ClientSerializer


class ClientViewSet(viewsets.ModelViewSet):
    """CRUD for the authenticated account's clients (isolated per account)."""

    serializer_class = ClientSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return list_clients_for_owner(owner=self.request.user)

    def perform_create(self, serializer) -> None:
        serializer.save(owner=self.request.user)
