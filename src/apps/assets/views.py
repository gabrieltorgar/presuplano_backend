"""Assets views: los binarios del editor y el catálogo de mobiliario."""

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response

from apps.assets.filters import PlanAssetFilter
from apps.assets.selectors import (
    list_assets_for_owner,
    list_models_for_owner,
    missing_paths,
)
from apps.assets.serializers import (
    CatalogModelsInputSerializer,
    MissingPathsSerializer,
    ModelIdsSerializer,
    PlanAssetInputSerializer,
    PlanAssetSerializer,
)
from apps.assets.services import remove_models, store_asset, store_models
from apps.team.tenancy import account_of
from common.pagination import DefaultPagination
from common.permissions import IsVerifiedUser


class PlanAssetViewSet(viewsets.ReadOnlyModelViewSet):
    """Los binarios del editor de la cuenta: listarlos, subirlos y cotejarlos."""

    serializer_class = PlanAssetSerializer
    permission_classes = [IsVerifiedUser]
    # La lista (iteracion-17): por páginas —el dispositivo las recorre—, por
    # clase y por ruta.
    filterset_class = PlanAssetFilter
    search_fields = ("path",)
    ordering_fields = ("path", "created_at")
    ordering = ("path", "id")
    # El binario llega como formulario; el cotejo de rutas, como JSON.
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_queryset(self):
        return list_assets_for_owner(owner=account_of(self.request))

    def create(self, request: Request, *args, **kwargs) -> Response:
        serializer = PlanAssetInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        asset, created = store_asset(
            owner=account_of(request), **serializer.validated_data
        )
        return Response(
            PlanAssetSerializer(asset).data,
            # Ya estaba: el resultado es el que se pedía, pero no se creó nada.
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    @action(detail=False, methods=["post"])
    def missing(self, request: Request) -> Response:
        """De estas rutas, las que la cuenta todavía no tiene."""
        serializer = MissingPathsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(
            {
                "missing": missing_paths(
                    owner=account_of(request), paths=serializer.validated_data["paths"]
                )
            }
        )


class CatalogModelViewSet(viewsets.ViewSet):
    """El catálogo de mobiliario de la cuenta: leerlo, guardarlo y quitar fichas.

    Las fichas van y vienen tal como las escribe el editor, en lote: una
    biblioteca trae decenas de piezas y se importa de una sola vez.
    """

    permission_classes = [IsVerifiedUser]

    def list(self, request: Request) -> Response:
        """Las fichas que tiene la cuenta, por páginas (iteracion-17).

        Una cuenta junta varias bibliotecas: el dispositivo recorre las páginas
        en vez de recibir cientos de fichas en una sola respuesta.
        """
        paginator = DefaultPagination()
        rows = list_models_for_owner(owner=account_of(request))
        page = paginator.paginate_queryset(rows, request, view=self)
        return paginator.get_paginated_response([row.fiche for row in page])

    def create(self, request: Request) -> Response:
        """Guarda un lote de fichas; las que ya estaban se reemplazan."""
        serializer = CatalogModelsInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        stored = store_models(
            owner=account_of(request), fiches=serializer.validated_data["models"]
        )
        return Response({"stored": stored}, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"])
    def remove(self, request: Request) -> Response:
        """Quita del catálogo las fichas con esos ids.

        Van por POST y no por DELETE de cada una porque el id lo pone el
        catálogo de origen y trae almohadillas (`eTeks#chair`), que en una URL
        no son parte de la ruta.
        """
        serializer = ModelIdsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        removed = remove_models(
            owner=account_of(request), ids=serializer.validated_data["ids"]
        )
        return Response({"removed": removed})
