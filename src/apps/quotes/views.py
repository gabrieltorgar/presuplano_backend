"""Quotes views: account-scoped quote CRUD.

There is no «generate document» operation: the document is built from the
quote whenever it is asked for, so it is always the current one.
"""

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from apps.quotes.selectors import list_quotes_for_owner
from apps.quotes.serializers import (
    PlanSyncSerializer,
    QuoteSerializer,
    QuoteWriteSerializer,
)
from apps.quotes.services import (
    create_quote,
    delete_quote,
    sync_quote_with_plan,
    update_quote,
)


class QuoteViewSet(viewsets.ModelViewSet):
    """CRUD for the account's quotes; totals are computed from line items."""

    serializer_class = QuoteSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return list_quotes_for_owner(owner=self.request.user)

    def _write(self, request: Request):
        serializer = QuoteWriteSerializer(
            data=request.data, context={"owner": request.user, "request": request}
        )
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data

    def create(self, request: Request, *args, **kwargs) -> Response:
        data = self._write(request)
        quote = create_quote(
            owner=request.user,
            client=data["client"],
            items_data=data["items"],
            notes=data.get("notes"),
            validity_days=data.get("validity_days"),
            plan=data.get("plan"),
        )
        return Response(QuoteSerializer(quote).data, status=status.HTTP_201_CREATED)

    def update(self, request: Request, *args, **kwargs) -> Response:
        quote = self.get_object()
        data = self._write(request)
        quote = update_quote(
            quote=quote,
            client=data["client"],
            items_data=data["items"],
            notes=data.get("notes"),
            validity_days=data.get("validity_days"),
        )
        return Response(QuoteSerializer(quote).data)

    def partial_update(self, request: Request, *args, **kwargs) -> Response:
        return self.update(request, *args, **kwargs)

    @action(detail=True, methods=["post"], url_path="plan-sync")
    def plan_sync(self, request: Request, pk=None) -> Response:
        """POST /quotes/{id}/plan-sync/ — la cotización al día con su plano."""
        quote = self.get_object()
        serializer = PlanSyncSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        quote = sync_quote_with_plan(
            quote=quote,
            plan=serializer.validated_data["plan"],
            items_data=serializer.validated_data["items"],
        )
        # Releída: la que se trajo para actualizarla guarda sus partidas de antes.
        return Response(QuoteSerializer(self.get_queryset().get(pk=quote.pk)).data)

    def perform_destroy(self, instance) -> None:
        delete_quote(quote=instance)
