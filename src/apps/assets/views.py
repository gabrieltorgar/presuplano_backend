"""Assets views: subir un binario del editor y saber cuáles faltan."""

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from apps.assets.selectors import list_assets_for_owner, missing_paths
from apps.assets.serializers import (
    MissingPathsSerializer,
    PlanAssetInputSerializer,
    PlanAssetSerializer,
)
from apps.assets.services import store_asset


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
