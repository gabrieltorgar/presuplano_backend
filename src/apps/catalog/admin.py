"""Admin registration for catalog."""

from django.contrib import admin
from unfold.admin import ModelAdmin

from apps.catalog.models import Tariff
from common.admin import ProtectedFieldsAdminMixin


@admin.register(Tariff)
class TariffAdmin(ProtectedFieldsAdminMixin, ModelAdmin):
    set_on_create_fields = ("owner",)
    list_display = ("name", "unit_type", "unit_price", "owner", "created_at")
    list_filter = ("unit_type",)
    search_fields = ("name",)
