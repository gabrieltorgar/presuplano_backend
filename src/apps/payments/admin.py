"""Admin registration for payments."""

from django.contrib import admin
from unfold.admin import ModelAdmin

from apps.folios.admin import FolioAssignedAdminMixin
from apps.folios.codes import DocumentType
from apps.payments.models import Payment
from common.admin import ProtectedFieldsAdminMixin


@admin.register(Payment)
class PaymentAdmin(FolioAssignedAdminMixin, ProtectedFieldsAdminMixin, ModelAdmin):
    folio_document_type = DocumentType.PAYMENT
    set_on_create_fields = ("owner", "project")
    list_display = ("folio", "project", "amount", "date", "owner", "created_at")
    search_fields = ("folio",)
    readonly_fields = ("folio",)
