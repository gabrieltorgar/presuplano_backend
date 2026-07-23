"""Admin registration for projects."""

from django.contrib import admin

from apps.projects.models import Evidence, Progress, Project


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("id", "quote", "status", "owner", "created_at")
    list_filter = ("status",)


@admin.register(Progress)
class ProgressAdmin(admin.ModelAdmin):
    list_display = ("id", "project", "quote_item", "quantity", "date")


@admin.register(Evidence)
class EvidenceAdmin(admin.ModelAdmin):
    list_display = ("id", "progress", "image", "created_at")
