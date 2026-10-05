"""Accounts business logic (all domain operations live here)."""

import base64
import logging
import mimetypes
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import (
    AuthenticationFailed,
    NotFound,
    PermissionDenied,
    ValidationError,
)
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.deletion import purge_account
from apps.accounts.emails import send_email_changed_notice, send_otp_email
from apps.accounts.models import Organization, OtpCode, Subscription, User
from apps.legal.services import record_acceptance
from common import mail

logger = logging.getLogger("apps")

#: Cuántas cifras tiene el código que se manda por correo.
OTP_LENGTH = 6


class AccountNotVerified(PermissionDenied):
    """403 con un código propio para una cuenta sin verificar.

    The screen has to tell this apart from a wrong password to walk the person
    to the code instead of leaving a red box, and matching on the message text
    would break the day the wording changes.

    Lleva además a dónde salió el código —el correo de la cuenta—, para que la
    pantalla siguiente lo diga sin volver a preguntarlo.
    """

    def __init__(self, identity: str = "") -> None:
        super().__init__(
            {
                "detail": "Debes verificar tu cuenta antes de iniciar sesión",
                # El código conserva su nombre de cuando se entraba con
                # teléfono: la pantalla que lo entiende ya está publicada.
                "code": "phone_not_verified",
                "identity": identity,
            }
        )


#: El nombre con el que nació, para quien lo importe desde fuera.
PhoneNotVerified = AccountNotVerified


def normalize_email(value: str | None) -> str:
    """Un correo sin espacios y en minúsculas."""
    return (value or "").strip().lower()


def find_user(*, email: str) -> User | None:
    """La cuenta de ese correo, sin importar cómo se escribieron las mayúsculas."""
    email = normalize_email(email)
    if not email:
        return None
    return User.objects.filter(email__iexact=email).first()


def uses_universal_code(user: User) -> bool:
    """Si a esa cuenta le sirve el código universal del MVP.

    Sólo mientras el correo no esté configurado: sin él no hay por dónde
    mandar el código de nadie. En cuanto lo está, cada quien necesita el suyo
    y el universal deja de abrir la puerta.
    """
    return not mail.is_configured()


def issue_otp(*, user: User, purpose: str) -> str:
    """Un código nuevo para esa cuenta y ese motivo; el anterior deja de valer."""
    OtpCode.objects.filter(user=user, purpose=purpose, used_at__isnull=True).update(
        used_at=timezone.now()
    )
    code = f"{secrets.randbelow(10**OTP_LENGTH):0{OTP_LENGTH}d}"
    OtpCode.objects.create(
        user=user,
        purpose=purpose,
        code_hash=make_password(code),
        expires_at=timezone.now() + timedelta(minutes=settings.OTP_TTL_MINUTES),
    )
    return code


def check_otp(*, user: User, purpose: str, code: str) -> bool:
    """Si ese código abre esa puerta. Al usarse, se gasta."""
    if uses_universal_code(user):
        return secrets.compare_digest(str(code), str(settings.OTP_UNIVERSAL_CODE))

    now = timezone.now()
    for issued in OtpCode.objects.filter(
        user=user, purpose=purpose, used_at__isnull=True, expires_at__gt=now
    ):
        if check_password(str(code), issued.code_hash):
            issued.used_at = now
            issued.save(update_fields=["used_at"])
            return True
    return False


def send_verification_code(
    *, user: User, purpose: str = OtpCode.Purpose.SIGNUP, to: str | None = None
) -> None:
    """Hacer llegar a su dueño, por correo, el código que abre su cuenta.

    Con el correo sin configurar no hay nada que mandar —sigue valiendo el
    código universal—; queda anotado que tocaba enviarlo. ``to`` manda el
    código a otra dirección: la del correo nuevo que se quiere confirmar.
    """
    if uses_universal_code(user):
        logger.info(
            "Verification code requested",
            extra={"user_id": str(user.pk), "channel": "pending"},
        )
        return

    code = issue_otp(user=user, purpose=purpose)
    send_otp_email(
        user=user,
        code=code,
        purpose=purpose,
        minutes=settings.OTP_TTL_MINUTES,
        to=to,
    )
    logger.info(
        "Verification code requested",
        extra={"user_id": str(user.pk), "channel": "email"},
    )
    logger.info("Verification code sent", extra={"user_id": str(user.pk)})


@transaction.atomic
def register_user(
    *,
    email: str,
    password: str,
    terms_version: str,
    privacy_version: str,
    ip_address: str | None = None,
    user_agent: str = "",
) -> User:
    """Create a pending (unverified) account, its subscription and letterhead.

    La cuenta nace sin verificar, con su suscripción del plan inicial, un
    membrete vacío y la constancia de que aceptó los términos y la política de
    privacidad vigentes, todo en la misma transacción; el código sale de
    inmediato hacia su correo.
    """
    email = normalize_email(email)
    if not email:
        raise ValidationError({"email": "Necesitas un correo para registrarte"})

    user = User.objects.create_user(email=email, password=password)
    Subscription.objects.create(
        user=user,
        plan=Subscription.Plan.INITIAL,
        status=Subscription.Status.ACTIVE,
    )
    # Empty letterhead, but already there: the documents screen never has to
    # deal with an account that has no organization row at all.
    Organization.objects.create(user=user)
    record_acceptance(
        user=user,
        terms_version=terms_version,
        privacy_version=privacy_version,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    logger.info("Account registered", extra={"user_id": str(user.pk)})
    # Y el código sale de inmediato: la pantalla siguiente ya lo está pidiendo.
    send_verification_code(user=user)
    return user


def verify_account(*, email: str, code: str) -> User:
    """Dar por bueno el correo de quien demuestra tener el código.

    Raises:
        NotFound: no hay cuenta con ese correo.
        ValidationError: ya estaba verificada, o el código no es válido.
    """
    user = find_user(email=email)
    if user is None:
        raise NotFound("No existe una cuenta con ese correo.")
    if user.is_email_verified:
        raise ValidationError("El correo ya está verificado")

    if not check_otp(user=user, purpose=OtpCode.Purpose.SIGNUP, code=code):
        raise ValidationError("Código de verificación inválido")

    user.is_email_verified = True
    user.save(update_fields=["is_email_verified", "updated_at"])
    logger.info("Account verified", extra={"user_id": str(user.pk)})
    return user


def resend_otp(*, email: str) -> None:
    """Volver a mandar el código de una cuenta pendiente de verificar.

    Ni un correo desconocido ni uno ya verificado se distinguen en la
    respuesta —eso convertiría el endpoint en un detector de clientes—, así
    que sólo se anota y, cuando toca, se envía.
    """
    user = find_user(email=email)
    pending = user is not None and not user.is_verified
    logger.info(
        "OTP resend requested",
        extra={"account_known": user is not None, "pending": pending},
    )
    if user is not None and pending:
        send_verification_code(user=user)


def login_user(*, email: str, password: str) -> tuple[User, dict[str, str]]:
    """Authenticate by email + password and issue JWT tokens.

    Credentials are checked before verification status so that a correct
    password on an unverified account yields 403 (not 401).

    Raises:
        AuthenticationFailed: unknown account or wrong password (401).
        AccountNotVerified: correct credentials but unverified (403); the
            verification code is sent again on the way out.
    """
    user = find_user(email=email)
    if user is None or not user.check_password(password):
        raise AuthenticationFailed("Credenciales inválidas")
    if not user.is_verified:
        # Quien entra sin verificar no se quedó fuera: recibe el código otra vez
        # y la pantalla lo lleva a escribirlo, como al registrarse.
        send_verification_code(user=user)
        raise AccountNotVerified(user.verification_identity)

    refresh = RefreshToken.for_user(user)
    tokens = {"access": str(refresh.access_token), "refresh": str(refresh)}
    logger.info("Login succeeded", extra={"user_id": str(user.pk)})
    return user, tokens


def start_password_reset(*, email: str) -> None:
    """Arrancar la recuperación de una contraseña olvidada.

    Un correo desconocido no dice nada —responder distinto convertiría el
    endpoint en un detector de clientes—, así que sólo se anota.
    """
    user = find_user(email=email)
    logger.info("Password reset requested", extra={"account_known": user is not None})
    if user is not None:
        send_verification_code(user=user, purpose=OtpCode.Purpose.PASSWORD_RESET)


def reset_password(*, email: str, code: str, password: str) -> User:
    """Cambiar la contraseña de quien demuestra tener el correo.

    Raises:
        NotFound: no existe una cuenta con ese correo.
        ValidationError: el código no es el correcto.
    """
    user = find_user(email=email)
    if user is None:
        raise NotFound("No existe una cuenta con ese correo.")

    if not check_otp(user=user, purpose=OtpCode.Purpose.PASSWORD_RESET, code=code):
        raise ValidationError("Código de verificación inválido")

    user.set_password(password)
    # Quien recupera demuestra lo mismo que quien verifica: que el correo es
    # suyo. Una cuenta que se quedó a medias entra de una vez.
    user.is_email_verified = True
    user.save(update_fields=["password", "is_email_verified", "updated_at"])
    logger.info("Password reset", extra={"user_id": str(user.pk)})
    return user


def _email_taken(email: str, *, by_other_than: User) -> bool:
    return (
        User.objects.filter(email__iexact=email).exclude(pk=by_other_than.pk).exists()
    )


@transaction.atomic
def request_email_change(*, user: User, email: str) -> User:
    """Empezar a cambiar el correo: el nuevo espera hasta demostrarse.

    La cuenta sigue entrando con su correo de siempre; el nuevo queda por
    confirmar y su código sale hacia él. Pedir otro correo reemplaza al
    anterior pendiente.

    Raises:
        ValidationError: vacío, igual al actual o ya de otra cuenta.
    """
    nuevo = normalize_email(email)
    if not nuevo:
        raise ValidationError({"email": "Escribe el correo nuevo"})
    if nuevo == normalize_email(user.email):
        raise ValidationError({"email": "Ese ya es el correo de tu cuenta"})
    if _email_taken(nuevo, by_other_than=user):
        raise ValidationError({"email": "Ese correo ya está registrado"})

    user.pending_email = nuevo
    user.save(update_fields=["pending_email", "updated_at"])
    send_verification_code(user=user, purpose=OtpCode.Purpose.EMAIL_CHANGE, to=nuevo)
    logger.info("Email change requested", extra={"user_id": str(user.pk)})
    return user


def resend_email_change(*, user: User) -> User:
    """Volver a mandar el código al correo nuevo que está por confirmar.

    Raises:
        ValidationError: no hay un cambio de correo pendiente.
    """
    if not user.pending_email:
        raise ValidationError("No tienes un cambio de correo pendiente")
    send_verification_code(
        user=user, purpose=OtpCode.Purpose.EMAIL_CHANGE, to=user.pending_email
    )
    return user


@transaction.atomic
def confirm_email_change(*, user: User, code: str) -> User:
    """Con el código del correo nuevo, la cuenta pasa a usarlo.

    El correo nuevo queda verificado —el código lo prueba— y al de antes le
    llega un aviso: si el cambio no lo hizo su dueño, así se entera.

    Raises:
        ValidationError: no hay cambio pendiente, el código no es válido o el
            correo lo tomó otra cuenta mientras tanto.
    """
    if not user.pending_email:
        raise ValidationError("No tienes un cambio de correo pendiente")
    if not check_otp(user=user, purpose=OtpCode.Purpose.EMAIL_CHANGE, code=code):
        raise ValidationError({"code": "Código de verificación inválido"})
    if _email_taken(user.pending_email, by_other_than=user):
        raise ValidationError({"email": "Ese correo ya está registrado"})

    anterior = user.email
    user.email = user.pending_email
    user.pending_email = ""
    user.is_email_verified = True
    user.save(
        update_fields=["email", "pending_email", "is_email_verified", "updated_at"]
    )
    logger.info("Email changed", extra={"user_id": str(user.pk)})
    transaction.on_commit(
        lambda: send_email_changed_notice(old_email=anterior, new_email=user.email)
    )
    return user


def cancel_email_change(*, user: User) -> User:
    """Olvidar el correo nuevo pendiente; su código deja de servir."""
    OtpCode.objects.filter(
        user=user, purpose=OtpCode.Purpose.EMAIL_CHANGE, used_at__isnull=True
    ).update(used_at=timezone.now())
    if user.pending_email:
        user.pending_email = ""
        user.save(update_fields=["pending_email", "updated_at"])
    return user


def change_password(*, user: User, current_password: str, new_password: str) -> User:
    """Cambiar la contraseña sabiendo la de ahora.

    Raises:
        ValidationError: la actual no es correcta, o la nueva es la misma.
    """
    if not user.check_password(current_password):
        raise ValidationError(
            {"current_password": "La contraseña actual no es correcta"}
        )
    if current_password == new_password:
        raise ValidationError(
            {"new_password": "La contraseña nueva debe ser distinta de la actual"}
        )
    user.set_password(new_password)
    user.save(update_fields=["password", "updated_at"])
    logger.info("Password changed", extra={"user_id": str(user.pk)})
    return user


def delete_account(*, user: User, password: str) -> dict[str, int]:
    """Eliminar la cuenta y todo lo suyo, confirmándolo con la contraseña.

    Se borra, no se anonimiza: la cuenta, su organización y logotipo, su
    información de trabajo, sus fotografías, planos, texturas y modelos, sus
    códigos y sus constancias de aceptación.

    Raises:
        ValidationError: la contraseña no es correcta.
    """
    if not user.check_password(password):
        raise ValidationError({"password": "La contraseña no es correcta"})
    return purge_account(user=user)


def get_my_organization(*, user: User) -> Organization:
    """Return the account's letterhead, creating an empty one if it has none.

    Accounts registered before organizations existed have no row; asking for it
    is what creates it, so the screen never sees a 404 it cannot act on.
    """
    organization, _created = Organization.objects.get_or_create(user=user)
    return organization


def organization_logo_data_url(*, user: User) -> str | None:
    """El logotipo de la cuenta como imagen incrustable, o nada.

    El PDF lo dibuja el navegador, y el logotipo vive en el bucket: bajarlo
    desde ahí es una petición a otro dominio que el bucket no autoriza, así
    que el documento salía sin marca. Esta API sí puede leerlo —y ya está
    autorizada para hablar con la aplicación—, de modo que lo entrega en el
    mismo cuerpo de la respuesta.
    """
    organization = get_my_organization(user=user)
    if not organization.logo:
        return None

    try:
        with organization.logo.open("rb") as archivo:
            raw = archivo.read()
    except (FileNotFoundError, OSError, ValueError):
        # Un archivo que ya no está no es un error de quien pide el documento.
        logger.warning("Organization logo missing", extra={"user_id": str(user.pk)})
        return None

    mime = mimetypes.guess_type(organization.logo.name)[0] or "image/png"
    return f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"
