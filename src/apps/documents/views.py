"""Documents views: entregar un documento por correo."""

from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.documents.serializers import SendDocumentSerializer
from apps.documents.services import send_document


class SendDocumentView(APIView):
    """POST /api/documents/send/ — manda el PDF al correo de quien lo recibe."""

    permission_classes = [IsAuthenticated]
    # El PDF viaja como formulario: es un archivo, no un texto.
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request: Request) -> Response:
        serializer = SendDocumentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        sent = send_document(user=request.user, **serializer.validated_data)
        return Response(
            {
                "sent": sent,
                "detail": (
                    "Documento enviado."
                    if sent
                    else "No se pudo entregar el correo. Inténtalo de nuevo."
                ),
            }
        )
