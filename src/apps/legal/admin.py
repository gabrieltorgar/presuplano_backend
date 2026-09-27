"""Admin registration for legal: las constancias se consultan, no se editan."""

from django.contrib import admin

from apps.legal.models import LegalAcceptance


@admin.register(LegalAcceptance)
class LegalAcceptanceAdmin(admin.ModelAdmin):
    list_display = ("user", "document", "version", "accepted_at", "ip_address")
    list_filter = ("document", "version")
    search_fields = ("user__email",)
    readonly_fields = (
        "user",
        "document",
        "version",
        "accepted_at",
        "ip_address",
        "user_agent",
    )

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False
