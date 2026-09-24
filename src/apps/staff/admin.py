"""Admin registration for staff."""

from django.contrib import admin

from apps.staff.models import Assignment, Worker, WorkerPayment, WorkerService


class WorkerServiceInline(admin.TabularInline):
    model = WorkerService
    extra = 0


@admin.register(Worker)
class WorkerAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "is_self", "phone", "owner", "created_at")
    list_filter = ("kind", "is_self", "is_active")
    search_fields = ("name", "phone", "email")
    inlines = [WorkerServiceInline]


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = ("worker", "quote_item", "quantity", "unit_price", "created_at")
    search_fields = ("worker__name", "quote_item__name")


@admin.register(WorkerPayment)
class WorkerPaymentAdmin(admin.ModelAdmin):
    list_display = ("worker", "amount", "method", "date", "project", "owner")
    list_filter = ("method",)
    search_fields = ("worker__name",)
