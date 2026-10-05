"""Documents serializers: qué se manda y a quién."""

from rest_framework import serializers

from apps.documents.services import Kind


class SendDocumentSerializer(serializers.Serializer):
    """Valida el envío de un documento: a quién, cuál, y el PDF."""

    kind = serializers.ChoiceField(choices=Kind.CHOICES)
    to = serializers.EmailField()
    file = serializers.FileField()
    # Lo que se lee en el cuerpo del correo sin abrir el adjunto.
    reference = serializers.CharField(max_length=60, required=False, allow_blank=True)
    party = serializers.CharField(max_length=150, required=False, allow_blank=True)
    amount = serializers.CharField(max_length=30, required=False, allow_blank=True)
    message = serializers.CharField(max_length=600, required=False, allow_blank=True)
