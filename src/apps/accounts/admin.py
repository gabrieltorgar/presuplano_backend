"""Admin registration for accounts."""

from django.contrib import admin

from apps.accounts.models import Subscription, User


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("phone", "is_phone_verified", "is_active", "created_at")
    search_fields = ("phone",)


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ("user", "plan", "status", "created_at")
