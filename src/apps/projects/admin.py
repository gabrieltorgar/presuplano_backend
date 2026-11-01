"""Admin registration for projects."""

from django.contrib import admin
from unfold.admin import ModelAdmin

from apps.folios.admin import FolioAssignedAdminMixin
from apps.folios.codes import DocumentType
from apps.projects.models import Evidence, Progress, Project
from common.admin import ProtectedFieldsAdminMixin


@admin.register(Project)
class ProjectAdmin(FolioAssignedAdminMixin, ProtectedFieldsAdminMixin, ModelAdmin):
    folio_document_type = DocumentType.PROJECT
    # El estado lo cambia sólo finalizarlo; la cotización de la que nació, nunca
    # (iteracion-26 #20).
    protected_fields = ("status",)
    set_on_create_fields = ("owner", "quote")
    list_display = ("folio", "quote", "status", "owner", "created_at")
    list_filter = ("status",)
    search_fields = ("folio",)
    readonly_fields = ("folio",)


@admin.register(Progress)
class ProgressAdmin(ProtectedFieldsAdminMixin, ModelAdmin):
    list_display = ("id", "project", "quote_item", "quantity", "date")
    # El precio de mano de obra lo copia el servicio del reparto (VAL-05).
    protected_fields = ("labor_unit_price",)
    set_on_create_fields = ("project", "quote_item")


@admin.register(Evidence)
class EvidenceAdmin(ModelAdmin):
    list_display = ("id", "progress", "image", "created_at")
