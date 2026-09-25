"""Assets views: los binarios del editor y el catálogo de mobiliario."""

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

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


class PlanAssetViewSet(viewsets.ReadOnlyModelViewSet):
    """Los binarios del editor de la cuenta: listarlos, subirlos y cotejarlos."""

    serializer_class = PlanAssetSerializer
    permission_classes = [IsAuthenticated]
    # El binario llega como formulario; el cotejo de rutas, como JSON.
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_queryset(self):
        return list_assets_for_owner(owner=self.request.user)

    def create(self, request: Request, *args, **kwargs) -> Response:
        serializer = PlanAssetInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        asset, created = store_asset(owner=request.user, **serializer.validated_data)
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
                    owner=request.user, paths=serializer.validated_data["paths"]
                )
            }
        )


class CatalogModelViewSet(viewsets.ViewSet):
    """El catálogo de mobiliario de la cuenta: leerlo, guardarlo y quitar fichas.

    Las fichas van y vienen tal como las escribe el editor, en lote: una
    biblioteca trae decenas de piezas y se importa de una sola vez.
    """

    permission_classes = [IsAuthenticated]

    def list(self, request: Request) -> Response:
        """Las fichas que tiene la cuenta."""
        return Response(
            [row.fiche for row in list_models_for_owner(owner=request.user)]
        )

    def create(self, request: Request) -> Response:
        """Guarda un lote de fichas; las que ya estaban se reemplazan."""
        serializer = CatalogModelsInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        stored = store_models(
            owner=request.user, fiches=serializer.validated_data["models"]
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
            owner=request.user, ids=serializer.validated_data["ids"]
        )
        return Response({"removed": removed})
