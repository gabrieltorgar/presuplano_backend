"""Admin registration for quotes."""

from django.contrib import admin

from apps.quotes.models import Quote, QuoteItem


class QuoteItemInline(admin.TabularInline):
    model = QuoteItem
    extra = 0


@admin.register(Quote)
class QuoteAdmin(admin.ModelAdmin):
    list_display = ("id", "client", "status", "owner", "created_at")
    list_filter = ("status",)
    inlines = [QuoteItemInline]
