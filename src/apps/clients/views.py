"""Clients views: account-scoped client CRUD."""

from rest_framework import viewsets
from rest_framework.decorators import action

from apps.clients.filters import ClientFilter
from apps.clients.selectors import list_clients_for_owner
from apps.clients.serializers import ClientSerializer
from apps.clients.services import delete_client, delete_clients
from apps.team.tenancy import account_of
from common.bulk import BulkActionMixin
from common.permissions import IsVerifiedUser


class ClientViewSet(BulkActionMixin, viewsets.ModelViewSet):
    """CRUD for the authenticated account's clients (isolated per account).

    GET /api/clients/?page=1&search=reyes&has_contact=true&ordering=-created_at
    """

    serializer_class = ClientSerializer
    permission_classes = [IsVerifiedUser]
    filterset_class = ClientFilter
    search_fields = ("name", "phone", "email")
    ordering_fields = ("name", "created_at")
    ordering_text_fields = ("name",)
    ordering = ("name", "id")

    def get_queryset(self):
        return list_clients_for_owner(owner=account_of(self.request))

    def perform_create(self, serializer) -> None:
        serializer.save(owner=account_of(self.request))

    def perform_destroy(self, instance) -> None:
        delete_client(client=instance)

    @action(
        detail=False, methods=["post"], url_path="bulk/delete", throttle_scope="bulk"
    )
    def bulk_delete(self, request):
        """POST /api/clients/bulk/delete/[?<query string de la lista>] → BulkResult."""
        clients = self.get_bulk_queryset(request)
        return self.bulk_response(delete_clients(clients=clients))
