"""Admin registration for accounts."""

from django.contrib import admin

from apps.accounts.models import Organization, OtpCode, Subscription, User


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("email", "is_email_verified", "is_active", "created_at")
    search_fields = ("email",)


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ("user", "plan", "status", "created_at")


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("user", "name", "email", "phone", "color", "updated_at")
    search_fields = ("name", "email", "user__email")


@admin.register(OtpCode)
class OtpCodeAdmin(admin.ModelAdmin):
    list_display = ("user", "purpose", "expires_at", "used_at", "created_at")
    list_filter = ("purpose",)
