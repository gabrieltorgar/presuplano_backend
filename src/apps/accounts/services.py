"""Accounts business logic (all domain operations live here)."""

import base64
import logging
import mimetypes
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.management import call_command
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac
from rest_framework.exceptions import (
    AuthenticationFailed,
    PermissionDenied,
    ValidationError,
)
from rest_framework_simplejwt.token_blacklist.models import (
    BlacklistedToken,
    OutstandingToken,
)
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.deletion import purge_account
from apps.accounts.emails import send_email_changed_notice, send_otp_email
from apps.accounts.models import Organization, OtpCode, Subscription, User
from apps.accounts.otp_quota import OTPCooldown, check_request_quota
from apps.legal.services import record_acceptance

logger = logging.getLogger("apps")

#: Cuántas cifras tiene el código que se manda por correo.
OTP_LENGTH = 6


class AccountNotVerified(PermissionDenied):
    """403 con un código propio para una cuenta sin verificar.

    The screen has to tell this apart from a wrong password to walk the person
    to the code instead of leaving a red box, and matching on the message text
    would break the day the wording changes.

    Lleva además a dónde salió el código —el correo de la cuenta—, para que la
    pantalla siguiente lo diga sin volver a preguntarlo. El acceso lo responde,
    no lo lanza (iteracion-26 #13): el código que acaba de salir tiene que
    quedar en la base también con ``ATOMIC_REQUESTS``.
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
    """Un correo sin espacios y en minúsculas; lo que no es texto, vacío.

    Llega también de un cuerpo que nadie validó (el señuelo del registro):
    un número o una lista no es un correo (MAN-04, iteracion-26 #17).
    """
    if not isinstance(value, str):
        return ""
    return value.strip().lower()


def find_user(*, email: str) -> User | None:
    """La cuenta de ese correo, sin importar cómo se escribieron las mayúsculas."""
    email = normalize_email(email)
    if not email:
        return None
    return User.objects.filter(email__iexact=email).first()


#: Para qué sirve el código universal de la suite E2E: verificar la cuenta.
#: Nunca para recuperar la contraseña ni para cambiar el correo (iteracion-26 #15).
UNIVERSAL_PURPOSES = frozenset({OtpCode.Purpose.SIGNUP})

#: Los entornos donde puede existir (los settings no cargan con él en otro).
UNIVERSAL_ENVIRONMENTS = frozenset({"local", "develop"})


def universal_code_accepted(*, user: User, purpose: str, code: str) -> bool:
    """Si el código universal de la suite E2E abre esa puerta.

    Sólo con ``APP_ENV`` local o develop, para las cuentas de
    ``OTP_UNIVERSAL_EMAILS`` y para verificar la cuenta; cada uso queda anotado
    (sin el código). Con o sin correo configurado: develop sí manda correos.
    """
    if (
        settings.APP_ENV not in UNIVERSAL_ENVIRONMENTS
        or not settings.OTP_UNIVERSAL_CODE
    ):
        return False
    if purpose not in UNIVERSAL_PURPOSES:
        return False
    if user.email.lower() not in settings.OTP_UNIVERSAL_EMAILS:
        return False
    if not constant_time_compare(str(code), settings.OTP_UNIVERSAL_CODE):
        return False
    logger.warning(
        "Universal OTP used", extra={"user_id": str(user.pk), "purpose": purpose}
    )
    return True


def otp_digest(*, user_pk, purpose: str, raw: str) -> str:
    """La huella del código: HMAC-SHA256 con la ``SECRET_KEY`` (iteracion-26 #13).

    Una copia de la base sola (un respaldo, una rama de Neon) no revela ningún
    código vivo, y no cuesta lo que un hash de contraseña en cada intento.
    """
    return salted_hmac(
        "apps.accounts.otp", f"{user_pk}:{purpose}:{raw}", algorithm="sha256"
    ).hexdigest()


def issue_otp(*, user: User, purpose: str) -> str:
    """Un código nuevo para esa cuenta y ese motivo; el anterior deja de valer.

    Los anteriores se anulan con ``update`` (nunca se borran: sus intentos
    quedan para el admin). El código sólo sale hacia el correo: aquí se guarda
    su huella.
    """
    OtpCode.objects.filter(user=user, purpose=purpose, used_at__isnull=True).update(
        used_at=timezone.now()
    )
    code = f"{secrets.randbelow(10**OTP_LENGTH):0{OTP_LENGTH}d}"
    OtpCode.objects.create(
        user=user,
        purpose=purpose,
        code_hash=otp_digest(user_pk=user.pk, purpose=purpose, raw=code),
        expires_at=timezone.now() + timedelta(minutes=settings.OTP_TTL_MINUTES),
    )
    return code


def _live_code(*, user: User, purpose: str) -> OtpCode | None:
    """El último código vigente, bloqueado hasta que termine la transacción.

    Dos verificaciones a la vez se forman en la fila: la segunda lee lo que
    dejó la primera (usado, o con un intento más).
    """
    return (
        OtpCode.objects.select_for_update()
        .filter(
            user=user,
            purpose=purpose,
            used_at__isnull=True,
            expires_at__gt=timezone.now(),
        )
        .order_by("-created_at")
        .first()
    )


@transaction.atomic
def check_otp(*, user: User, purpose: str, code: str) -> bool:
    """Si ese código abre esa puerta. Al usarse, se gasta.

    Cada intento fallido cuenta en la fila (``F``, bajo el bloqueo); al llegar a
    ``OTP_MAX_ATTEMPTS`` el código muere aunque después llegue el correcto: seis
    dígitos no se adivinan en cinco intentos, sí en un millón. Nunca lanza: quien
    llama responde el 400, y el intento sobrevive a ``ATOMIC_REQUESTS``.
    """
    if universal_code_accepted(user=user, purpose=purpose, code=code):
        return True

    live = _live_code(user=user, purpose=purpose)
    if live is None or live.attempts >= settings.OTP_MAX_ATTEMPTS:
        return False
    expected = otp_digest(user_pk=user.pk, purpose=purpose, raw=str(code))
    if constant_time_compare(live.code_hash, expected):
        live.used_at = timezone.now()
        live.save(update_fields=["used_at"])
        return True

    OtpCode.objects.filter(pk=live.pk).update(attempts=F("attempts") + 1)
    spent = OtpCode.objects.filter(
        pk=live.pk, attempts__gte=settings.OTP_MAX_ATTEMPTS
    ).update(used_at=timezone.now())
    if spent:
        logger.warning(
            "Verification code voided after repeated failures",
            extra={"user_id": str(user.pk), "purpose": purpose},
        )
    return False


def send_verification_code(
    *, user: User, purpose: str = OtpCode.Purpose.SIGNUP, to: str | None = None
) -> None:
    """Hacer llegar a su dueño, por correo, el código que abre su cuenta.

    ``to`` manda el código a otra dirección: la del correo nuevo que se quiere
    confirmar. Sin correo configurado el código igual se emite y el envío anota
    que no salió: ya no hay un código universal que lo reemplace (#15).
    """
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
def check_password_strength(
    *, password: str, user: User, field: str = "password"
) -> None:
    """Los validadores de Django (AUTH_PASSWORD_VALIDATORS), en la API.

    Antes sólo se pedía el largo: «password123» o una derivada del propio correo
    pasaban. Se aplican al registrarse, al recuperar y al cambiar la contraseña.

    Raises:
        ValidationError: ``{field: [motivos]}``.
    """
    try:
        password_validation.validate_password(password, user=user)
    except DjangoValidationError as exc:
        raise ValidationError({field: list(exc.messages)}) from None


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
    check_password_strength(password=password, user=User(email=email))

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


def verify_account(*, email: str, code: str) -> User | None:
    """Dar por bueno el correo de quien demuestra tener el código.

    Devuelve ``None`` si el código no sirve: la vista responde el 400 y el
    intento queda contado (iteracion-26 #13). Un correo sin cuenta, o de una ya
    verificada, devuelve lo mismo (iteracion-26 #14): responder distinto
    convertiría el endpoint en un detector de clientes.
    """
    user = find_user(email=email)
    if user is None or user.is_email_verified:
        return None

    if not check_otp(user=user, purpose=OtpCode.Purpose.SIGNUP, code=code):
        return None

    user.is_email_verified = True
    user.save(update_fields=["is_email_verified", "updated_at"])
    logger.info("Account verified", extra={"user_id": str(user.pk)})
    return user


def resend_otp(*, email: str) -> None:
    """Volver a mandar el código de una cuenta pendiente de verificar.

    Ni un correo desconocido ni uno ya verificado se distinguen en la
    respuesta —eso convertiría el endpoint en un detector de clientes—, así
    que sólo se anota y, cuando toca, se envía. La cuota va antes de buscar la
    cuenta (iteracion-26 #14): la espera es la misma exista o no.

    Raises:
        OTPCooldown: dentro de la espera o pasado el tope por hora (429).
    """
    check_request_quota(email=normalize_email(email), purpose=OtpCode.Purpose.SIGNUP)
    user = find_user(email=email)
    pending = user is not None and not user.is_verified
    logger.info(
        "OTP resend requested",
        extra={"account_known": user is not None, "pending": pending},
    )
    if user is not None and pending:
        send_verification_code(user=user)


def start_session(*, user: User) -> RefreshToken:
    """Una sesión nueva para esa cuenta: el refresh del que sale su access.

    La vista la pone en cookies HttpOnly (common/auth_cookies.py); los tokens
    nunca viajan en el cuerpo de una respuesta.
    """
    return RefreshToken.for_user(user)


def end_all_sessions(*, user: User) -> None:
    """Anula todas las sesiones abiertas de la cuenta.

    Cada refresh emitido queda registrado (token_blacklist); ponerlos en la
    lista negra deja fuera a cualquier dispositivo —o copia— que los tenga.
    """
    pendientes = OutstandingToken.objects.filter(
        user=user, blacklistedtoken__isnull=True
    )
    BlacklistedToken.objects.bulk_create(
        [BlacklistedToken(token=token) for token in pendientes], ignore_conflicts=True
    )


def flush_expired_sessions() -> None:
    """Borra de la lista de sesiones las que ya vencieron (``flushexpiredtokens``).

    Cada refresh emitido queda registrado y nada más lo borraba: la tabla
    crecía sin límite. Lo corre el cron diario de Vercel (iteracion-26 #11).
    """
    call_command("flushexpiredtokens")
    logger.info("Expired sessions flushed")


def login_user(*, email: str, password: str) -> tuple[User, RefreshToken | None]:
    """Authenticate by email + password and open a session.

    Credentials are checked before verification status so that a correct
    password on an unverified account yields 403 (not 401). An unverified
    account gets its code again and no session (``None``): the view answers the
    403 (``AccountNotVerified``) instead of raising it, so the code just sent
    stays in the database under ``ATOMIC_REQUESTS`` (iteracion-26 #13).

    Raises:
        AuthenticationFailed: unknown account or wrong password (401).
    """
    user = find_user(email=email)
    if user is None or not user.check_password(password):
        raise AuthenticationFailed("Credenciales inválidas")
    if not user.is_verified:
        # Quien entra sin verificar no se quedó fuera: recibe el código otra vez
        # y la pantalla lo lleva a escribirlo, como al registrarse. Dentro de la
        # espera no sale otro: el de hace un momento sigue sirviendo, y el 403
        # no se vuelve 429.
        try:
            check_request_quota(email=user.email, purpose=OtpCode.Purpose.SIGNUP)
        except OTPCooldown:
            pass
        else:
            send_verification_code(user=user)
        return user, None

    session = start_session(user=user)
    logger.info("Login succeeded", extra={"user_id": str(user.pk)})
    return user, session


def start_password_reset(*, email: str) -> None:
    """Arrancar la recuperación de una contraseña olvidada.

    Un correo desconocido no dice nada —responder distinto convertiría el
    endpoint en un detector de clientes—, así que sólo se anota. La cuota va
    antes de buscar la cuenta (iteracion-26 #14).

    Raises:
        OTPCooldown: dentro de la espera o pasado el tope por hora (429).
    """
    check_request_quota(
        email=normalize_email(email), purpose=OtpCode.Purpose.PASSWORD_RESET
    )
    user = find_user(email=email)
    logger.info("Account recovery requested", extra={"account_known": user is not None})
    if user is not None:
        send_verification_code(user=user, purpose=OtpCode.Purpose.PASSWORD_RESET)


def reset_password(*, email: str, code: str, password: str) -> User | None:
    """Cambiar la contraseña de quien demuestra tener el correo.

    Devuelve ``None`` si el código no sirve: la vista responde el 400 y el
    intento queda contado (iteracion-26 #13). Un correo sin cuenta devuelve lo
    mismo (iteracion-26 #14).

    Raises:
        ValidationError: la contraseña es débil (con o sin cuenta: la misma
            regla, para que ese 400 tampoco diga si el correo existe).
    """
    user = find_user(email=email)

    # Antes de gastar el código: una contraseña débil no obliga a pedir otro.
    check_password_strength(
        password=password, user=user or User(email=normalize_email(email))
    )
    if user is None:
        return None
    if not check_otp(user=user, purpose=OtpCode.Purpose.PASSWORD_RESET, code=code):
        return None

    user.set_password(password)
    # Quien recupera demuestra lo mismo que quien verifica: que el correo es
    # suyo. Una cuenta que se quedó a medias entra de una vez.
    user.is_email_verified = True
    user.save(update_fields=["password", "is_email_verified", "updated_at"])
    # Quien no sabía su contraseña no debe dejar abierta la sesión de nadie más.
    end_all_sessions(user=user)
    logger.info("Account recovered", extra={"user_id": str(user.pk)})
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
        OTPCooldown: el correo nuevo recibió un código hace poco, o ya
            demasiados en la hora (iteracion-26 #14).
    """
    nuevo = normalize_email(email)
    if not nuevo:
        raise ValidationError({"email": "Escribe el correo nuevo"})
    if nuevo == normalize_email(user.email):
        raise ValidationError({"email": "Ese ya es el correo de tu cuenta"})
    if _email_taken(nuevo, by_other_than=user):
        raise ValidationError({"email": "Ese correo ya está registrado"})
    check_request_quota(email=nuevo, purpose=OtpCode.Purpose.EMAIL_CHANGE)

    user.pending_email = nuevo
    user.save(update_fields=["pending_email", "updated_at"])
    send_verification_code(user=user, purpose=OtpCode.Purpose.EMAIL_CHANGE, to=nuevo)
    logger.info("Email change requested", extra={"user_id": str(user.pk)})
    return user


def resend_email_change(*, user: User) -> User:
    """Volver a mandar el código al correo nuevo que está por confirmar.

    Raises:
        ValidationError: no hay un cambio de correo pendiente.
        OTPCooldown: dentro de la espera o pasado el tope por hora (429).
    """
    if not user.pending_email:
        raise ValidationError("No tienes un cambio de correo pendiente")
    check_request_quota(email=user.pending_email, purpose=OtpCode.Purpose.EMAIL_CHANGE)
    send_verification_code(
        user=user, purpose=OtpCode.Purpose.EMAIL_CHANGE, to=user.pending_email
    )
    return user


@transaction.atomic
def confirm_email_change(*, user: User, code: str) -> User | None:
    """Con el código del correo nuevo, la cuenta pasa a usarlo.

    El correo nuevo queda verificado —el código lo prueba— y al de antes le
    llega un aviso: si el cambio no lo hizo su dueño, así se entera. Devuelve
    ``None`` si el código no sirve: la vista responde el 400 y el intento queda
    contado (iteracion-26 #13).

    Raises:
        ValidationError: no hay cambio pendiente, o el correo lo tomó otra
            cuenta mientras tanto (el código ya coincidió: revertirlo no borra
            ningún intento fallido).
    """
    if not user.pending_email:
        raise ValidationError("No tienes un cambio de correo pendiente")
    if not check_otp(user=user, purpose=OtpCode.Purpose.EMAIL_CHANGE, code=code):
        return None
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
    check_password_strength(password=new_password, user=user, field="new_password")
    user.set_password(new_password)
    user.save(update_fields=["password", "updated_at"])
    # Las otras sesiones se cierran; la vista abre una nueva para quien la cambió.
    end_all_sessions(user=user)
    logger.info("Sign-in credentials changed", extra={"user_id": str(user.pk)})
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
