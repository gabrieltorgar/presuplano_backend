"""Planner admin: plans are read here, never edited by hand."""

from django.contrib import admin
from unfold.admin import ModelAdmin

from apps.planner.models import PhotoConversion, Plan
from common.admin import ProtectedFieldsAdminMixin


@admin.register(Plan)
class PlanAdmin(ProtectedFieldsAdminMixin, ModelAdmin):
    set_on_create_fields = ("owner",)
    list_display = ["name", "owner", "updated_at"]
    search_fields = ["name", "owner__email"]
    list_filter = ["updated_at"]
    readonly_fields = ["document"]


@admin.register(PhotoConversion)
class PhotoConversionAdmin(ModelAdmin):
    """Who converted photos and when: the daily cap, seen from here."""

    list_display = ["owner", "walls", "rooms", "created_at"]
    search_fields = ["owner__email"]
    list_filter = ["created_at"]
    readonly_fields = ["owner", "walls", "rooms", "created_at", "updated_at"]
