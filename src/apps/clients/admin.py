"""Admin registration for clients."""

from django.contrib import admin
from unfold.admin import ModelAdmin

from apps.clients.models import Client
from common.admin import ProtectedFieldsAdminMixin


@admin.register(Client)
class ClientAdmin(ProtectedFieldsAdminMixin, ModelAdmin):
    set_on_create_fields = ("owner",)
    list_display = ("name", "phone", "email", "owner", "created_at")
    search_fields = ("name", "phone", "email")
