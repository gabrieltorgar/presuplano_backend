"""Admin registration for plan assets."""

from django.contrib import admin

from apps.assets.models import PlanAsset


@admin.register(PlanAsset)
class PlanAssetAdmin(admin.ModelAdmin):
    list_display = ("path", "kind", "size", "owner", "created_at")
    list_filter = ("kind",)
    search_fields = ("path",)
