"""Quotes views: account-scoped quote CRUD + document generation."""

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from apps.quotes.selectors import list_quotes_for_owner
from apps.quotes.serializers import QuoteSerializer, QuoteWriteSerializer
from apps.quotes.services import create_quote, generate_quote_document, update_quote


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
            owner=request.user, client=data["client"], items_data=data["items"]
        )
        return Response(QuoteSerializer(quote).data, status=status.HTTP_201_CREATED)

    def update(self, request: Request, *args, **kwargs) -> Response:
        quote = self.get_object()
        data = self._write(request)
        quote = update_quote(
            quote=quote, client=data["client"], items_data=data["items"]
        )
        return Response(QuoteSerializer(quote).data)

    def partial_update(self, request: Request, *args, **kwargs) -> Response:
        return self.update(request, *args, **kwargs)

    @action(detail=True, methods=["post"], url_path="generate-document")
    def generate_document(self, request: Request, pk: str | None = None) -> Response:
        quote = self.get_object()
        quote = generate_quote_document(quote=quote)
        return Response(QuoteSerializer(quote).data)
