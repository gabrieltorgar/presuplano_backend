"""Accounts business logic (all domain operations live here)."""

import logging
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

from apps.accounts.emails import send_otp_email
from apps.accounts.models import Organization, OtpCode, Subscription, User
from common import mail

logger = logging.getLogger("apps")

#: Cuántas cifras tiene el código que se manda por correo.
OTP_LENGTH = 6


class AccountNotVerified(PermissionDenied):
    """403 con un código propio para una cuenta sin verificar.

    The screen has to tell this apart from a wrong password to walk the person
    to the code instead of leaving a red box, and matching on the message text
    would break the day the wording changes.
    """

    def __init__(self) -> None:
        super().__init__(
            {
                "detail": "Debes verificar tu cuenta antes de iniciar sesión",
                # El código no cambia aunque ahora la identidad pueda ser un
                # correo: la pantalla que lo entiende lleva meses publicada.
                "code": "phone_not_verified",
            }
        )


#: El nombre con el que nació, para quien lo importe desde fuera.
PhoneNotVerified = AccountNotVerified


def normalize_email(value: str | None) -> str | None:
    """Un correo en minúsculas, o nada. Vacío es nada, no cadena vacía."""
    cleaned = (value or "").strip().lower()
    return cleaned or None


def normalize_phone(value: str | None) -> str | None:
    """Un teléfono sin espacios, o nada."""
    cleaned = (value or "").strip()
    return cleaned or None


def find_user(*, identifier: str) -> User | None:
    """La cuenta que responde a ese teléfono o a ese correo.

    Es lo que permite escribir en un solo campo lo que cada quien recuerda: el
    número de la obra o el correo del estudio.
    """
    identifier = (identifier or "").strip()
    if not identifier:
        return None
    if "@" in identifier:
        return User.objects.filter(email__iexact=identifier).first()
    return User.objects.filter(phone=identifier).first()


def uses_universal_code(user: User) -> bool:
    """Si a esa cuenta le sirve el código universal del MVP.

    Le sirve a quien no tiene por dónde recibir el suyo: sin correo —no hay
    SMS todavía— o con el correo apagado por falta de configuración. Quien sí
    puede recibirlo necesita el suyo, y el universal deja de abrirle la puerta.
    """
    return not (user.email and mail.is_configured())


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
    *, user: User, purpose: str = OtpCode.Purpose.SIGNUP
) -> None:
    """Hacer llegar a su dueño el código que abre su cuenta.

    Por correo cuando lo hay, que es el canal que existe hoy. A una cuenta que
    sólo tiene teléfono no hay nada que mandarle todavía —no hay SMS— y le
    sigue sirviendo el código universal; esto deja constancia del intento.
    """
    if uses_universal_code(user):
        # Sin canal propio sigue valiendo el código universal; queda anotado
        # que tocaba enviarlo, que es lo único que se puede hacer hoy por una
        # cuenta que sólo tiene teléfono.
        logger.info(
            "Verification code requested",
            extra={"user_id": str(user.pk), "channel": "pending"},
        )
        return

    code = issue_otp(user=user, purpose=purpose)
    send_otp_email(
        user=user, code=code, purpose=purpose, minutes=settings.OTP_TTL_MINUTES
    )
    logger.info(
        "Verification code requested",
        extra={"user_id": str(user.pk), "channel": "email"},
    )
    logger.info("Verification code sent", extra={"user_id": str(user.pk)})


@transaction.atomic
def register_user(
    *, password: str, phone: str | None = None, email: str | None = None
) -> User:
    """Create a pending (unverified) account, its subscription and letterhead.

    La cuenta nace sin verificar, con su suscripción del plan inicial y un
    membrete vacío en la misma transacción. Basta con una de las dos
    identidades: el teléfono de siempre, el correo, o los dos.
    """
    phone = normalize_phone(phone)
    email = normalize_email(email)
    if not phone and not email:
        raise ValidationError("Necesitas un teléfono o un correo para registrarte")

    user = User.objects.create_user(
        phone=phone,
        email=email,
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
    # Y el código sale de inmediato: la pantalla siguiente ya lo está pidiendo.
    send_verification_code(user=user)
    return user


def verify_account(*, identifier: str, code: str) -> User:
    """Dar por buena la identidad de quien demuestra tener el código.

    Se verifica el canal por el que se pidió: quien escribe su correo verifica
    su correo, quien escribe su teléfono, su teléfono.

    Raises:
        NotFound: no hay cuenta con ese teléfono ni con ese correo.
        ValidationError: ya estaba verificada por ahí, o el código no es válido.
    """
    user = find_user(identifier=identifier)
    if user is None:
        raise NotFound("No existe una cuenta con esos datos.")

    por_correo = "@" in identifier
    if por_correo and user.is_email_verified:
        raise ValidationError("El correo ya está verificado")
    if not por_correo and user.is_phone_verified:
        raise ValidationError("El teléfono ya está verificado")

    if not check_otp(user=user, purpose=OtpCode.Purpose.SIGNUP, code=code):
        raise ValidationError("Código de verificación inválido")

    if por_correo:
        user.is_email_verified = True
        user.save(update_fields=["is_email_verified", "updated_at"])
    else:
        user.is_phone_verified = True
        user.save(update_fields=["is_phone_verified", "updated_at"])
    logger.info("Account verified", extra={"user_id": str(user.pk)})
    return user


def resend_otp(*, identifier: str) -> None:
    """Volver a mandar el código de una cuenta pendiente de verificar.

    Ni una identidad desconocida ni una ya verificada se distinguen en la
    respuesta —eso convertiría el endpoint en un detector de clientes—, así
    que sólo se anota y, cuando toca, se envía.
    """
    user = find_user(identifier=identifier)
    pending = user is not None and not user.is_verified
    logger.info(
        "OTP resend requested",
        extra={"account_known": user is not None, "pending": pending},
    )
    if user is not None and pending:
        send_verification_code(user=user)


def login_user(*, identifier: str, password: str) -> tuple[User, dict[str, str]]:
    """Authenticate by phone-or-email + password and issue JWT tokens.

    Credentials are checked before verification status so that a correct
    password on an unverified account yields 403 (not 401).

    Raises:
        AuthenticationFailed: unknown account or wrong password (401).
        AccountNotVerified: correct credentials but unverified (403); the
            verification code is sent again on the way out.
    """
    user = find_user(identifier=identifier)
    if user is None or not user.check_password(password):
        raise AuthenticationFailed("Credenciales inválidas")
    if not user.is_verified:
        # Quien entra sin verificar no se quedó fuera: recibe el código otra vez
        # y la pantalla lo lleva a escribirlo, como al registrarse.
        send_verification_code(user=user)
        raise AccountNotVerified

    refresh = RefreshToken.for_user(user)
    tokens = {"access": str(refresh.access_token), "refresh": str(refresh)}
    logger.info("Login succeeded", extra={"user_id": str(user.pk)})
    return user, tokens


def start_password_reset(*, identifier: str) -> None:
    """Arrancar la recuperación de una contraseña olvidada.

    A quien tiene correo le llega su código; a quien sólo tiene teléfono le
    sirve el universal mientras no haya SMS. Una identidad desconocida no dice
    nada —responder distinto convertiría el endpoint en un detector de
    clientes—, así que sólo se anota.
    """
    user = find_user(identifier=identifier)
    logger.info("Password reset requested", extra={"account_known": user is not None})
    if user is not None:
        send_verification_code(user=user, purpose=OtpCode.Purpose.PASSWORD_RESET)


def reset_password(*, identifier: str, code: str, password: str) -> User:
    """Cambiar la contraseña de quien demuestra tener el teléfono o el correo.

    Raises:
        NotFound: no existe una cuenta con esos datos.
        ValidationError: el código no es el correcto.
    """
    user = find_user(identifier=identifier)
    if user is None:
        raise NotFound("No existe una cuenta con esos datos.")

    if not check_otp(user=user, purpose=OtpCode.Purpose.PASSWORD_RESET, code=code):
        raise ValidationError("Código de verificación inválido")

    user.set_password(password)
    # Quien recupera demuestra lo mismo que quien verifica: que tiene el canal.
    # Una cuenta que se quedó a medias entra de una vez.
    campos = ["password", "updated_at"]
    if "@" in identifier:
        user.is_email_verified = True
        campos.append("is_email_verified")
    else:
        user.is_phone_verified = True
        campos.append("is_phone_verified")
    user.save(update_fields=campos)
    logger.info("Password reset", extra={"user_id": str(user.pk)})
    return user


@transaction.atomic
def update_my_account(
    *, user: User, phone: str | None = None, email: str | None = None
) -> User:
    """Cambiar el teléfono o el correo desde el perfil.

    Un dato nuevo entra sin verificar y con su código en camino: la cuenta no
    puede quedarse sin ninguna identidad verificada por un cambio, así que el
    otro canal es el que la sostiene mientras tanto.

    Raises:
        ValidationError: el dato ya es de otra cuenta, o se queda sin ninguno.
    """
    cambios: list[str] = []

    if phone is not None:
        nuevo = normalize_phone(phone)
        if nuevo != user.phone:
            if nuevo and User.objects.filter(phone=nuevo).exclude(pk=user.pk).exists():
                raise ValidationError({"phone": "Ese teléfono ya está registrado"})
            user.phone = nuevo
            user.is_phone_verified = False
            cambios += ["phone", "is_phone_verified"]

    if email is not None:
        nuevo = normalize_email(email)
        if nuevo != user.email:
            if (
                nuevo
                and User.objects.filter(email__iexact=nuevo)
                .exclude(pk=user.pk)
                .exists()
            ):
                raise ValidationError({"email": "Ese correo ya está registrado"})
            user.email = nuevo
            user.is_email_verified = False
            cambios += ["email", "is_email_verified"]

    if not user.phone and not user.email:
        raise ValidationError("Tu cuenta necesita un teléfono o un correo")

    if cambios:
        user.save(update_fields=[*cambios, "updated_at"])
        logger.info(
            "Account identity updated",
            extra={"user_id": str(user.pk), "fields": ",".join(cambios)},
        )
        # El dato nuevo hay que demostrarlo: el código sale hacia él.
        if not user.is_verified or (email is not None and user.email):
            send_verification_code(user=user)

    return user


def get_my_organization(*, user: User) -> Organization:
    """Return the account's letterhead, creating an empty one if it has none.

    Accounts registered before organizations existed have no row; asking for it
    is what creates it, so the screen never sees a 404 it cannot act on.
    """
    organization, _created = Organization.objects.get_or_create(user=user)
    return organization
