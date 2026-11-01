"""Admin registration for quotes."""

from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline

from apps.folios.admin import FolioAssignedAdminMixin
from apps.folios.codes import DocumentType
from apps.quotes.models import Quote, QuoteItem, QuoteItemRoom
from common.admin import ProtectedFieldsAdminMixin


class QuoteItemInline(TabularInline):
    model = QuoteItem
    extra = 0


@admin.register(Quote)
class QuoteAdmin(FolioAssignedAdminMixin, ProtectedFieldsAdminMixin, ModelAdmin):
    folio_document_type = DocumentType.QUOTE
    # El estado lo cambia sólo volverla proyecto (iteracion-26 #20).
    protected_fields = ("status",)
    set_on_create_fields = ("owner",)
    list_display = ("folio", "client", "status", "plan", "owner", "created_at")
    list_filter = ("status",)
    search_fields = ("folio", "client__name")
    readonly_fields = ("folio",)
    inlines = [QuoteItemInline]


class QuoteItemRoomInline(TabularInline):
    model = QuoteItemRoom
    extra = 0


@admin.register(QuoteItem)
class QuoteItemAdmin(ModelAdmin):
    """Las partidas se editan dentro de su cotización; aquí se buscan."""

    list_display = ("name", "quote", "quantity", "unit_price", "from_plan")
    search_fields = ("name", "quote__client__name")
    list_select_related = ("quote",)
    inlines = [QuoteItemRoomInline]


@admin.register(QuoteItemRoom)
class QuoteItemRoomAdmin(ModelAdmin):
    """Lo que cae en cada habitación (iteracion-25); se edita en su partida."""

    list_display = ("name", "quote_item", "quantity")
    search_fields = ("name", "quote_item__name")
    list_select_related = ("quote_item",)
