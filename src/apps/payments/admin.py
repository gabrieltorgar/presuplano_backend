"""Admin registration for payments."""

from django.contrib import admin

from apps.payments.models import Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("id", "project", "amount", "date", "owner", "created_at")
