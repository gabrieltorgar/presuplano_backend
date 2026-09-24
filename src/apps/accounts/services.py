"""Accounts business logic (all domain operations live here)."""

import logging
import secrets

from django.conf import settings
from django.db import transaction
from rest_framework.exceptions import (
    AuthenticationFailed,
    NotFound,
    PermissionDenied,
    ValidationError,
)
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import Organization, Subscription, User

logger = logging.getLogger("apps")


@transaction.atomic
def register_user(*, phone: str, password: str) -> User:
    """Create a pending (unverified) account, its subscription and letterhead.

    The account starts with ``is_phone_verified=False``; a subscription with the
    initial plan and an empty organization are created in the same transaction
    (multi-tenant workspace).
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
    # Empty letterhead, but already there: the documents screen never has to
    # deal with an account that has no organization row at all.
    Organization.objects.create(user=user)
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


def resend_otp(*, phone: str) -> None:
    """Volver a mandar el código de verificación de una cuenta pendiente.

    En el MVP el código es el OTP universal, así que no hay nada que enviar:
    esto existe para dejar registro del intento y para que la pantalla tenga a
    quién pedírselo. Ni un teléfono desconocido ni uno ya verificado se
    distinguen en la respuesta —eso convertiría el endpoint en un detector de
    clientes—, así que solo se anota.
    """
    user = User.objects.filter(phone=phone).first()
    logger.info(
        "OTP resent",
        extra={
            "phone_known": user is not None,
            "pending": user is not None and not user.is_phone_verified,
        },
    )


def login_user(*, phone: str, password: str) -> tuple[User, dict[str, str]]:
    """Authenticate by phone + password and issue JWT tokens.

    Credentials are checked before verification status so that a correct
    password on an unverified account yields 403 (not 401).

    Raises:
        AuthenticationFailed: unknown phone or wrong password (401).
        PermissionDenied: correct credentials but phone not verified (403).
    """
    user = User.objects.filter(phone=phone).first()
    if user is None or not user.check_password(password):
        raise AuthenticationFailed("Credenciales inválidas")
    if not user.is_phone_verified:
        raise PermissionDenied("Debes verificar tu teléfono antes de iniciar sesión")

    refresh = RefreshToken.for_user(user)
    tokens = {"access": str(refresh.access_token), "refresh": str(refresh)}
    logger.info("Login succeeded", extra={"user_id": str(user.pk)})
    return user, tokens


def start_password_reset(*, phone: str) -> None:
    """Arrancar la recuperación de una contraseña olvidada.

    En el MVP el código es el OTP universal, así que no hay nada que enviar:
    esto existe para dejar registro del intento y para que la pantalla tenga a
    quién preguntarle. Un teléfono desconocido no dice nada —responder distinto
    convertiría el endpoint en un detector de clientes—, así que solo se anota.
    """
    exists = User.objects.filter(phone=phone).exists()
    logger.info(
        "Password reset requested",
        extra={"phone_known": exists},
    )


def reset_password(*, phone: str, code: str, password: str) -> User:
    """Cambiar la contraseña de quien demuestra tener el teléfono.

    Raises:
        NotFound: no existe una cuenta con ese teléfono.
        ValidationError: el código no es el correcto.
    """
    try:
        user = User.objects.get(phone=phone)
    except User.DoesNotExist as exc:
        raise NotFound("No existe una cuenta con ese teléfono.") from exc

    if not secrets.compare_digest(str(code), str(settings.OTP_UNIVERSAL_CODE)):
        raise ValidationError("Código de verificación inválido")

    user.set_password(password)
    # Quien recupera demuestra lo mismo que quien verifica: que tiene el
    # teléfono. Una cuenta que se quedó a medias entra de una vez.
    user.is_phone_verified = True
    user.save(update_fields=["password", "is_phone_verified", "updated_at"])
    logger.info("Password reset", extra={"user_id": str(user.pk)})
    return user


def get_my_organization(*, user: User) -> Organization:
    """Return the account's letterhead, creating an empty one if it has none.

    Accounts registered before organizations existed have no row; asking for it
    is what creates it, so the screen never sees a 404 it cannot act on.
    """
    organization, _created = Organization.objects.get_or_create(user=user)
    return organization
