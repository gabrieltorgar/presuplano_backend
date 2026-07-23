"""Accounts business logic (all domain operations live here)."""

import logging

from django.db import transaction

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
