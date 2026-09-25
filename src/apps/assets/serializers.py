"""Assets serializers."""

from rest_framework import serializers

from apps.assets.models import PlanAsset


class PlanAssetSerializer(serializers.ModelSerializer):
    """Lo que el editor necesita: con qué nombre lo pide y de dónde lo baja."""

    url = serializers.SerializerMethodField()

    class Meta:
        model = PlanAsset
        fields = ["id", "path", "kind", "url", "size", "created_at"]
        read_only_fields = fields

    def get_url(self, asset: PlanAsset) -> str:
        return asset.file.url if asset.file else ""


class PlanAssetInputSerializer(serializers.Serializer):
    """Validates an upload: the logical path, what it is, and the bytes."""

    path = serializers.CharField(max_length=400)
    kind = serializers.ChoiceField(
        choices=PlanAsset.Kind.choices, required=False, default=PlanAsset.Kind.TEXTURE
    )
    file = serializers.FileField()


class MissingPathsSerializer(serializers.Serializer):
    """Validates the manifest query: a list of paths."""

    paths = serializers.ListField(
        child=serializers.CharField(max_length=400), allow_empty=True, max_length=500
    )


class CatalogModelsInputSerializer(serializers.Serializer):
    """Valida un lote de fichas: objetos, y no más de los que trae una biblioteca."""

    models = serializers.ListField(
        child=serializers.DictField(), allow_empty=True, max_length=500
    )


class ModelIdsSerializer(serializers.Serializer):
    """Valida una lista de ids del catálogo."""

    ids = serializers.ListField(
        child=serializers.CharField(max_length=200), allow_empty=True, max_length=500
    )
