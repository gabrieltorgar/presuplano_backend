"""Serializers de colaboradores e invitaciones."""

from rest_framework import serializers

from apps.accounts.serializers import PASSWORD_MAX_LENGTH

#: Cuántos correos caben en una sola tanda.
MAX_EMAILS = 20


class InviteSerializer(serializers.Serializer):
    """Los correos a invitar: de uno a veinte."""

    emails = serializers.ListField(
        child=serializers.EmailField(
            error_messages={"invalid": "Revisa este correo: no parece válido."}
        ),
        min_length=1,
        max_length=MAX_EMAILS,
        error_messages={
            "min_length": "Escribe al menos un correo.",
            "max_length": f"Invita hasta {MAX_EMAILS} correos a la vez.",
        },
    )


class SentInvitationSerializer(serializers.Serializer):
    """Una invitación que acaba de salir, y si su correo llegó a enviarse."""

    id = serializers.UUIDField(source="invitation.id")
    email = serializers.EmailField(source="invitation.email")
    expires_at = serializers.DateTimeField(source="invitation.expires_at")
    email_sent = serializers.BooleanField()


class SkippedSerializer(serializers.Serializer):
    email = serializers.EmailField()
    reason = serializers.CharField()


class InviteResultSerializer(serializers.Serializer):
    invited = SentInvitationSerializer(many=True)
    skipped = SkippedSerializer(many=True)


class InvitationPreviewSerializer(serializers.Serializer):
    """Lo que la pantalla de la invitación muestra antes de aceptarla."""

    email = serializers.EmailField()
    company = serializers.CharField()
    status = serializers.CharField()
    account_exists = serializers.BooleanField()
    expires_at = serializers.DateTimeField()


class AcceptInvitationSerializer(serializers.Serializer):
    """La contraseña —nueva o la de siempre— y, para una cuenta nueva, los
    documentos que acepta."""

    password = serializers.CharField(
        write_only=True,
        max_length=PASSWORD_MAX_LENGTH,
        error_messages={
            "required": "Escribe tu contraseña.",
            "blank": "Escribe tu contraseña.",
            "max_length": (
                f"La contraseña puede tener hasta {PASSWORD_MAX_LENGTH} caracteres."
            ),
        },
    )
    terms_version = serializers.CharField(
        max_length=40, required=False, allow_blank=True, default=""
    )
    privacy_version = serializers.CharField(
        max_length=40, required=False, allow_blank=True, default=""
    )


class TeamRowSerializer(serializers.Serializer):
    """Una fila de la tabla de colaboradores: un colaborador o una invitación."""

    id = serializers.UUIDField()
    kind = serializers.ChoiceField(choices=["member", "invitation"])
    email = serializers.EmailField()
    status = serializers.ChoiceField(
        choices=["active", "inactive", "pending", "expired"]
    )
    since = serializers.DateTimeField()
    expires_at = serializers.DateTimeField(allow_null=True)


class MemberUpdateSerializer(serializers.Serializer):
    """Activar o desactivar a un colaborador."""

    is_active = serializers.BooleanField()
