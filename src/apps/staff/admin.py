"""Admin registration for staff."""

from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline

from apps.folios.admin import FolioAssignedAdminMixin
from apps.folios.codes import DocumentType
from apps.staff.models import Assignment, Worker, WorkerPayment, WorkerService
from common.admin import ProtectedFieldsAdminMixin


class WorkerServiceInline(TabularInline):
    model = WorkerService
    extra = 0


@admin.register(Worker)
class WorkerAdmin(ProtectedFieldsAdminMixin, ModelAdmin):
    set_on_create_fields = ("owner",)
    list_display = ("name", "kind", "is_self", "phone", "owner", "created_at")
    list_filter = ("kind", "is_self", "is_active")
    search_fields = ("name", "phone", "email")
    inlines = [WorkerServiceInline]


@admin.register(Assignment)
class AssignmentAdmin(ProtectedFieldsAdminMixin, ModelAdmin):
    # Corregir un reparto no lo cambia de proyecto, partida ni persona.
    set_on_create_fields = ("project", "quote_item", "worker")
    list_display = ("worker", "quote_item", "quantity", "unit_price", "created_at")
    search_fields = ("worker__name", "quote_item__name")


@admin.register(WorkerPayment)
class WorkerPaymentAdmin(
    FolioAssignedAdminMixin, ProtectedFieldsAdminMixin, ModelAdmin
):
    folio_document_type = DocumentType.WORKER_PAYMENT
    set_on_create_fields = ("owner", "worker")
    list_display = ("folio", "worker", "amount", "method", "date", "project", "owner")
    list_filter = ("method",)
    search_fields = ("folio", "worker__name")
    readonly_fields = ("folio",)


@admin.register(WorkerService)
class WorkerServiceAdmin(ModelAdmin):
    """Lo que cobra cada quien por servicio; se edita dentro de su persona."""

    list_display = ("worker", "tariff", "unit_price")
    search_fields = ("worker__name", "tariff__name")
    list_select_related = ("worker", "tariff")
