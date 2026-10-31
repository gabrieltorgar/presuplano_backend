"""Admin registration for accounts (Unfold)."""

from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin as BaseGroupAdmin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group
from django.utils.translation import gettext_lazy as _
from rest_framework_simplejwt.token_blacklist import admin as blacklist_admin
from rest_framework_simplejwt.token_blacklist.models import (
    BlacklistedToken,
    OutstandingToken,
)
from unfold.admin import ModelAdmin
from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm

from apps.accounts.deletion import purge_account
from apps.accounts.models import Organization, OtpCode, Subscription, User
from common.admin import ProtectedFieldsAdminMixin

# Llegan con el ModelAdmin de Django: se vuelven a registrar con Unfold.
for _model in (Group, OutstandingToken, BlacklistedToken):
    admin.site.unregister(_model)


@admin.register(Group)
class GroupAdmin(BaseGroupAdmin, ModelAdmin):
    """Los grupos de Django con la apariencia del admin."""


@admin.register(User)
class UserAdmin(BaseUserAdmin, ModelAdmin):
    """Cuentas por correo: sin nombre de usuario, con su verificación."""

    form = UserChangeForm
    add_form = UserCreationForm
    change_password_form = AdminPasswordChangeForm
    ordering = ("email",)
    list_display = ("email", "is_email_verified", "is_active", "is_staff", "created_at")
    list_filter = ("is_email_verified", "is_active", "is_staff")
    search_fields = ("email",)
    readonly_fields = ("created_at", "updated_at", "last_login")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (_("Verificación"), {"fields": ("is_email_verified", "pending_email")}),
        (
            _("Permisos"),
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        (_("Fechas"), {"fields": ("last_login", "created_at", "updated_at")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "password1", "password2"),
            },
        ),
    )

    # Borrar una cuenta es purgarla con todo lo suyo, archivos incluidos, y con
    # el contexto de la RLS de esa cuenta: con el del admin no vería sus filas
    # y el borrado chocaría con ellas (iteracion-26 #22).
    def delete_model(self, request, obj) -> None:
        purge_account(user=obj)

    def delete_queryset(self, request, queryset) -> None:
        for user in queryset:
            purge_account(user=user)


@admin.register(Subscription)
class SubscriptionAdmin(ProtectedFieldsAdminMixin, ModelAdmin):
    list_display = ("user", "plan", "status", "created_at")
    # Nace activa al registrarse y ningún flujo la cambia todavía (iteracion-26 #20).
    protected_fields = ("status",)
    set_on_create_fields = ("user",)
    list_select_related = ("user",)


@admin.register(Organization)
class OrganizationAdmin(ProtectedFieldsAdminMixin, ModelAdmin):
    set_on_create_fields = ("user",)
    list_display = ("user", "name", "email", "phone", "color", "updated_at")
    search_fields = ("name", "email", "user__email")
    list_select_related = ("user",)


@admin.register(OtpCode)
class OtpCodeAdmin(ModelAdmin):
    """Auditoría de los códigos: para qué, intentos y vigencia (iteracion-26 #13).

    Nunca muestra su huella (``code_hash``), y los códigos sólo los crea el
    servicio: aquí no se agregan ni se editan.
    """

    list_display = (
        "user",
        "purpose",
        "expires_at",
        "used_at",
        "attempts",
        "created_at",
    )
    list_filter = ("purpose",)
    search_fields = ("user__email",)
    list_select_related = ("user",)
    # Explícitos (nunca exclude): un campo nuevo no aparece solo.
    fields = ("user", "purpose", "expires_at", "used_at", "attempts", "created_at")
    readonly_fields = fields

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False


@admin.register(OutstandingToken)
class OutstandingTokenAdmin(blacklist_admin.OutstandingTokenAdmin, ModelAdmin):
    """Las sesiones emitidas (refresh), de solo lectura como en simplejwt."""


@admin.register(BlacklistedToken)
class BlacklistedTokenAdmin(blacklist_admin.BlacklistedTokenAdmin, ModelAdmin):
    """Las sesiones anuladas: al renovar, al salir o al cambiar la contraseña."""
