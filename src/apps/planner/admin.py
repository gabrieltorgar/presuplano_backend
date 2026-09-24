"""Planner admin: plans are read here, never edited by hand."""

from django.contrib import admin

from apps.planner.models import Plan


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ["name", "owner", "updated_at"]
    search_fields = ["name", "owner__phone"]
    list_filter = ["updated_at"]
    readonly_fields = ["document"]
