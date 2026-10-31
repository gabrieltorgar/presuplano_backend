"""Admin registration for the editor's files and catalogue."""

from django.contrib import admin
from unfold.admin import ModelAdmin

from apps.assets.models import CatalogModel, PlanAsset
from common.admin import ProtectedFieldsAdminMixin


@admin.register(PlanAsset)
class PlanAssetAdmin(ProtectedFieldsAdminMixin, ModelAdmin):
    set_on_create_fields = ("owner",)
    list_display = ("path", "kind", "size", "owner", "created_at")
    list_filter = ("kind",)
    search_fields = ("path",)


@admin.register(CatalogModel)
class CatalogModelAdmin(ProtectedFieldsAdminMixin, ModelAdmin):
    set_on_create_fields = ("owner",)
    list_display = ("model_id", "owner", "created_at")
    search_fields = ("model_id",)
