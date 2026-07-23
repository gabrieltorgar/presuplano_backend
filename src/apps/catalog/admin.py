"""Admin registration for catalog."""

from django.contrib import admin

from apps.catalog.models import Tariff


@admin.register(Tariff)
class TariffAdmin(admin.ModelAdmin):
    list_display = ("name", "unit_type", "unit_price", "owner", "created_at")
    list_filter = ("unit_type",)
    search_fields = ("name",)
