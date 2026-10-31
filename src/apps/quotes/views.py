"""Quotes views: account-scoped quote CRUD.

There is no «generate document» operation: the document is built from the
quote whenever it is asked for, so it is always the current one.
"""

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from apps.quotes.filters import QuoteFilter
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
from apps.team.tenancy import account_of
from common.permissions import IsVerifiedUser


class QuoteViewSet(viewsets.ModelViewSet):
    """CRUD for the account's quotes; totals are computed from line items.

    The list (US-13, iteracion-17): ``?status=a,b``, ``?plan=a,b`` (the quotes
    of those plans, US-133) and ``?id=a,b``; searches by client; orders by
    date, amount or client, newest first by default. Each quote is also asked
    for on its own (``GET /quotes/{id}/``), so no screen needs the whole list.
    """

    serializer_class = QuoteSerializer
    permission_classes = [IsVerifiedUser]
    filterset_class = QuoteFilter
    search_fields = ("client__name", "folio")
    ordering_fields = ("created_at", "total", "client_name")
    ordering_text_fields = ("client_name",)
    ordering = ("-created_at", "-id")

    def get_queryset(self):
        return list_quotes_for_owner(owner=account_of(self.request))

    def _write(self, request: Request):
        serializer = QuoteWriteSerializer(
            data=request.data,
            context={"owner": account_of(request), "request": request},
        )
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data

    def create(self, request: Request, *args, **kwargs) -> Response:
        data = self._write(request)
        quote = create_quote(
            owner=account_of(request),
            client=data["client"],
            items_data=data["items"],
            notes=data.get("notes"),
            validity_days=data.get("validity_days"),
            plan=data.get("plan"),
        )
        return Response(self._read(quote), status=status.HTTP_201_CREATED)

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
        return Response(self._read(quote))

    def partial_update(self, request: Request, *args, **kwargs) -> Response:
        return self.update(request, *args, **kwargs)

    @action(detail=True, methods=["post"], url_path="plan-sync")
    def plan_sync(self, request: Request, pk=None) -> Response:
        """POST /quotes/{id}/plan-sync/ — la cotización al día con su plano."""
        quote = self.get_object()
        serializer = PlanSyncSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        quote = sync_quote_with_plan(
            quote=quote,
            plan=serializer.validated_data["plan"],
            items_data=serializer.validated_data["items"],
        )
        return Response(self._read(quote))

    def _read(self, quote) -> dict:
        """The quote as it is now, its lines and rooms in one read (no N+1).

        Read again: the one fetched to change it holds its lines from before.
        """
        return QuoteSerializer(self.get_queryset().get(pk=quote.pk)).data

    def perform_destroy(self, instance) -> None:
        delete_quote(quote=instance)
