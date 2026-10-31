"""Accounts app config."""

from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"
    label = "accounts"
    verbose_name = "Cuentas"

    def ready(self) -> None:
        # Los chequeos de arranque viven en common y en core; se registran al
        # importarse.
        from common import checks  # noqa: F401
        from core import checks as core_checks  # noqa: F401
