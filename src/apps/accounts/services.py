"""Accounts business logic (all domain operations live here)."""

import logging
import secrets

from django.conf import settings
from django.db import transaction
from rest_framework.exceptions import NotFound, ValidationError

from apps.accounts.models import Subscription, User

logger = logging.getLogger("apps")


@transaction.atomic
def register_user(*, phone: str, password: str) -> User:
    """Create a pending (unverified) account and its active subscription.

    The account starts with ``is_phone_verified=False``; a subscription with the
    initial plan is created in the same transaction (multi-tenant workspace).
    """
    user = User.objects.create_user(
        phone=phone,
        password=password,
        is_phone_verified=False,
    )
    Subscription.objects.create(
        user=user,
        plan=Subscription.Plan.INITIAL,
        status=Subscription.Status.ACTIVE,
    )
    logger.info("Account registered", extra={"user_id": str(user.pk)})
    return user


def verify_phone(*, phone: str, code: str) -> User:
    """Verify a pending account's phone against the universal MVP OTP code.

    In the MVP the OTP is a single universal code (``OTP_UNIVERSAL_CODE``); a real
    per-user code delivered by SMS/WhatsApp replaces it later.

    Raises:
        NotFound: no account exists for the phone.
        ValidationError: phone already verified, or the code is invalid.
    """
    try:
        user = User.objects.get(phone=phone)
    except User.DoesNotExist as exc:
        raise NotFound("No existe una cuenta con ese teléfono.") from exc

    if user.is_phone_verified:
        raise ValidationError("El teléfono ya está verificado")

    if not secrets.compare_digest(str(code), str(settings.OTP_UNIVERSAL_CODE)):
        raise ValidationError("Código de verificación inválido")

    user.is_phone_verified = True
    user.save(update_fields=["is_phone_verified", "updated_at"])
    logger.info("Phone verified", extra={"user_id": str(user.pk)})
    return user
