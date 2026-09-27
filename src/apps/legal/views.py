"""Legal views: los documentos se leen sin cuenta; aceptarlos, con ella."""

from django.http import Http404
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.legal import documents
from apps.legal.serializers import AcceptanceSerializer
from apps.legal.services import client_ip, record_acceptance, status_for


class LegalDocumentsView(APIView):
    """GET /api/legal/ — qué documentos hay y su versión vigente."""

    permission_classes = [AllowAny]
    authentication_classes: list = []

    def get(self, request: Request) -> Response:
        return Response(
            {
                kind: {"title": doc.title, "version": doc.version}
                for kind in documents.FILES
                for doc in [documents.load(kind)]
            }
        )


class LegalDocumentView(APIView):
    """GET /api/legal/<kind>/ — el texto vigente de un documento."""

    permission_classes = [AllowAny]
    authentication_classes: list = []

    def get(self, request: Request, kind: str) -> Response:
        if kind not in documents.FILES:
            raise Http404
        doc = documents.load(kind)
        return Response(
            {
                "kind": doc.kind,
                "title": doc.title,
                "version": doc.version,
                "body": doc.body,
            }
        )


class LegalAcceptView(APIView):
    """POST /api/legal/accept/ — aceptar las versiones vigentes."""

    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        serializer = AcceptanceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        record_acceptance(
            user=request.user,
            ip_address=client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
            **serializer.validated_data,
        )
        return Response(status_for(request.user), status=status.HTTP_200_OK)
