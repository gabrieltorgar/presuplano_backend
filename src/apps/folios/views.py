"""Folios views: la configuración de folios de la empresa en la que se trabaja."""

from django.http import Http404
from rest_framework.request import Request
from rest_framework.response import Response

from apps.folios.codes import DocumentType
from apps.folios.selectors import folio_setting_row, folio_settings_for
from apps.folios.serializers import (
    FolioPreviewSerializer,
    FolioSettingInputSerializer,
    FolioSettingSerializer,
)
from apps.folios.services import configure_folios, preview_folio
from apps.team.permissions import IsCompanyAdmin
from apps.team.tenancy import account_of
from common.permissions import IsVerifiedUser
from common.views import TenantAPIView


def _document_type(value: str) -> str:
    """El tipo pedido en la ruta; uno que no existe es 404."""
    if value not in DocumentType.values:
        raise Http404
    return value


class FolioSettingsView(TenantAPIView):
    """GET /api/folio-settings/ — la configuración de cada tipo de documento.

    Es un recurso, no una lista: un objeto con una llave por tipo
    (``{"quote": {...}, "project": {...}}``), en el orden de ``DocumentType``.
    """

    permission_classes = [IsVerifiedUser]

    def get(self, request: Request) -> Response:
        rows = folio_settings_for(owner=account_of(request))
        return Response(
            {row["document_type"]: FolioSettingSerializer(row).data for row in rows}
        )


class FolioSettingDetailView(TenantAPIView):
    """GET/PUT /api/folio-settings/<tipo>/ — la modalidad y la clave de un tipo.

    Cambiarla es de quien administra la empresa (US-140); verla, de todos.
    """

    def get_permissions(self):
        if self.request.method == "GET":
            return [IsVerifiedUser()]
        return [IsVerifiedUser(), IsCompanyAdmin()]

    def get(self, request: Request, document_type: str) -> Response:
        row = folio_setting_row(
            owner=account_of(request), document_type=_document_type(document_type)
        )
        return Response(FolioSettingSerializer(row).data)

    def put(self, request: Request, document_type: str) -> Response:
        kind = _document_type(document_type)
        serializer = FolioSettingInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        owner = account_of(request)
        setting = configure_folios(
            owner=owner, document_type=kind, **serializer.validated_data
        )
        row = folio_setting_row(owner=owner, document_type=kind, setting=setting)
        return Response(FolioSettingSerializer(row).data)


class FolioPreviewView(TenantAPIView):
    """GET /api/folio-settings/<tipo>/preview/?mode=sequential&prefix=VEN.

    El folio que saldría con esa clave, sin guardarla ni apartarlo: si VEN
    llegó a 100, la vista previa dice VEN-101.
    """

    permission_classes = [IsVerifiedUser]

    def get(self, request: Request, document_type: str) -> Response:
        kind = _document_type(document_type)
        serializer = FolioPreviewSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        folio = preview_folio(
            owner=account_of(request), document_type=kind, **serializer.validated_data
        )
        return Response({"next_folio": folio})
