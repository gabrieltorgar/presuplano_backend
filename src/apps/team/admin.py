"""Admin de colaboradores e invitaciones (Unfold)."""

from django.contrib import admin
from unfold.admin import ModelAdmin

from apps.team.models import Invitation, Membership
from common.admin import ProtectedFieldsAdminMixin


@admin.register(Membership)
class MembershipAdmin(ProtectedFieldsAdminMixin, ModelAdmin):
    set_on_create_fields = ("account", "user")
    list_display = ("user", "account", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("user__email", "account__email")
    raw_id_fields = ("user", "account")


@admin.register(Invitation)
class InvitationAdmin(ProtectedFieldsAdminMixin, ModelAdmin):
    # Se acepta o se cancela sólo por su servicio; el correo es a quien llegó
    # el enlace (iteracion-26 #20).
    protected_fields = ("status",)
    set_on_create_fields = ("account", "email")
    list_display = ("email", "account", "status", "sent_at", "expires_at")
    list_filter = ("status",)
    search_fields = ("email", "account__email")
    raw_id_fields = ("account",)
    # La huella del enlace no se enseña ni se edita: no sirve sin el enlace.
    exclude = ("token_hash",)
    readonly_fields = ("sent_at", "expires_at", "accepted_at", "created_at")
