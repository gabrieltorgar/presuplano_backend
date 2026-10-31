"""Reglas de colaboradores: invitar, aceptar, activar y quitar."""

import hashlib
import logging
import secrets
import uuid
from dataclasses import dataclass, field
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import APIException, NotFound, ValidationError

from apps.accounts.models import User
from apps.accounts.services import check_password_strength, find_user, normalize_email
from apps.legal.services import record_acceptance
from apps.team.emails import send_invitation_email, send_invitation_emails
from apps.team.models import Invitation, Membership
from apps.team.selectors import (
    company_name,
    get_invitation,
    get_member,
    is_member,
    pending_invitation,
)
from common.bulk import NOT_FOUND, BulkResult, error_text
from common.mail import mask_email

logger = logging.getLogger("apps")

#: Cuánto vale un enlace de invitación.
INVITATION_DAYS = 7

#: Por qué no sale una segunda invitación al mismo correo.
ALREADY_PENDING = "Ya tiene una invitación pendiente; puedes reenviarla."


def hash_token(token: str) -> str:
    """La huella del enlace: lo que se guarda y con lo que se busca."""
    return hashlib.sha256(token.encode()).hexdigest()


def _new_link() -> tuple[str, str]:
    """Un enlace nuevo: el secreto que viaja y la huella que se queda."""
    token = secrets.token_urlsafe(32)
    return token, hash_token(token)


@dataclass
class Sent:
    invitation: Invitation
    email_sent: bool


@dataclass
class InviteResult:
    invited: list[Sent] = field(default_factory=list)
    skipped: list[dict[str, str]] = field(default_factory=list)


def _send(invitation: Invitation, token: str) -> Sent:
    sent = send_invitation_email(
        account=invitation.account,
        email=invitation.email,
        token=token,
        days=INVITATION_DAYS,
    )
    logger.info(
        "Invitation sent",
        extra={"to": mask_email(invitation.email), "delivered": sent},
    )
    return Sent(invitation=invitation, email_sent=sent)


def _refresh_link(invitation: Invitation) -> str:
    """Enlace y vigencia nuevos; el anterior deja de servir."""
    token, invitation.token_hash = _new_link()
    invitation.sent_at = timezone.now()
    invitation.expires_at = invitation.sent_at + timedelta(days=INVITATION_DAYS)
    invitation.save(update_fields=["token_hash", "sent_at", "expires_at"])
    return token


@transaction.atomic
def invite_collaborators(*, account: User, emails: list[str]) -> InviteResult:
    """Invita a cada correo a la empresa de ``account``.

    No se manda una segunda invitación a quien ya colabora o ya tiene una
    vigente; una vencida se renueva. Los correos salen en una sola tanda y en
    la misma transacción que las invitaciones: si algo corta el envío a la
    mitad, no queda ninguna pendiente sin su correo (iteracion-16). Si el
    correo no sale, las invitaciones quedan y se pueden reenviar.
    """
    result = InviteResult()
    links: list[tuple[Invitation, str]] = []
    seen: set[str] = set()
    for raw in emails:
        email = normalize_email(raw)
        if email in seen:
            continue
        seen.add(email)

        if email == normalize_email(account.email):
            result.skipped.append(
                {
                    "email": email,
                    "reason": "Es tu propio correo: ya eres el administrador.",
                }
            )
            continue
        if is_member(account=account, email=email):
            result.skipped.append({"email": email, "reason": "Ya es colaborador."})
            continue

        invitation = pending_invitation(account=account, email=email)
        if invitation is not None and not invitation.is_expired:
            result.skipped.append({"email": email, "reason": ALREADY_PENDING})
            continue

        if invitation is None:
            token, token_hash = _new_link()
            now = timezone.now()
            try:
                with transaction.atomic():
                    invitation = Invitation.objects.create(
                        account=account,
                        email=email,
                        token_hash=token_hash,
                        sent_at=now,
                        expires_at=now + timedelta(days=INVITATION_DAYS),
                    )
            except IntegrityError:
                # Otra petición la acaba de guardar: es la misma invitación, no
                # un error del sistema (iteracion-16).
                result.skipped.append({"email": email, "reason": ALREADY_PENDING})
                continue
        else:
            token = _refresh_link(invitation)
        links.append((invitation, token))

    if links:
        sent = send_invitation_emails(
            account=account,
            links=[(invitation.email, token) for invitation, token in links],
            days=INVITATION_DAYS,
        )
        logger.info("Invitations sent", extra={"count": len(links), "delivered": sent})
        result.invited = [
            Sent(invitation=invitation, email_sent=sent) for invitation, _ in links
        ]
    return result


class InvitationGone(APIException):
    """La invitación existió pero ya no sirve: venció o se canceló."""

    status_code = status.HTTP_410_GONE
    default_code = "invitation_gone"


class InvitationUsed(APIException):
    """La invitación ya se aceptó: el enlace sirve una sola vez."""

    status_code = status.HTTP_409_CONFLICT
    default_code = "invitation_used"
    default_detail = "Ya aceptaste esta invitación: inicia sesión con tu correo."


def find_invitation(*, token: str, lock: bool = False) -> Invitation:
    """La invitación de ese enlace.

    Raises:
        NotFound: ningún enlace emitido tiene esa huella.
    """
    queryset = Invitation.objects.select_related("account")
    if lock:
        queryset = queryset.select_for_update()
    invitation = queryset.filter(token_hash=hash_token(token)).first()
    if invitation is None:
        raise NotFound("Esta invitación no existe. Revisa el enlace o pide otra.")
    return invitation


def invitation_state(invitation: Invitation) -> str:
    """Pendiente, vencida, aceptada o cancelada: lo que la pantalla necesita."""
    return "expired" if invitation.is_expired else invitation.status


def _ensure_usable(invitation: Invitation) -> None:
    if invitation.status == Invitation.Status.ACCEPTED:
        raise InvitationUsed()
    if invitation.status == Invitation.Status.CANCELLED:
        raise InvitationGone("La invitación se canceló. Pide otra al administrador.")
    if invitation.is_expired:
        raise InvitationGone(
            "La invitación venció. Pide al administrador que te la reenvíe."
        )


class AccountJustCreated(APIException):
    """La cuenta de ese correo nació mientras tanto: se entra con su contraseña."""

    status_code = status.HTTP_409_CONFLICT
    default_code = "account_exists"
    default_detail = (
        "Ya existe una cuenta con este correo. Vuelve a abrir la invitación y "
        "entra con la contraseña de esa cuenta."
    )


@dataclass
class Accepted:
    """Quién entró y a qué empresa se sumó."""

    user: User
    account: User


def decoy_acceptance(*, token: str) -> dict:
    """La respuesta a una aceptación descartada por el campo trampa.

    Tiene la forma de una de verdad —la persona y la empresa a la que se
    entra—, para que nadie la distinga ni se rompa quien la lee, pero no hay
    cuenta ni sesión detrás (iteracion-16). Un enlace que no existe o que ya no
    sirve responde lo mismo que en la vía real (MAN-04, iteracion-26 #17).

    Raises:
        NotFound, InvitationGone, InvitationUsed: el enlace no sirve.
    """
    invitation = find_invitation(token=token)
    _ensure_usable(invitation)
    return {
        "user": {
            "id": str(uuid.uuid4()),
            "email": invitation.email,
            "is_email_verified": True,
        },
        "company": {
            "id": str(uuid.uuid4()),
            "name": company_name(account=invitation.account),
        },
    }


@transaction.atomic
def accept_invitation(
    *,
    token: str,
    password: str,
    terms_version: str = "",
    privacy_version: str = "",
    ip_address: str | None = None,
    user_agent: str = "",
) -> Accepted:
    """Sumar a la empresa a quien recibió el enlace.

    Sin cuenta, la crea ya confirmada —el enlace llegó a ese correo— y sin
    empresa propia, con la constancia de los documentos que aceptó. Con cuenta,
    pide su contraseña. El enlace sirve una sola vez.

    Raises:
        NotFound, InvitationGone, InvitationUsed: el enlace no sirve.
        ValidationError: contraseña débil o equivocada, o faltan los documentos.
        AccountJustCreated: la cuenta de ese correo nació mientras tanto.
    """
    invitation = find_invitation(token=token, lock=True)
    _ensure_usable(invitation)

    user = find_user(email=invitation.email)
    if user is None:
        if not terms_version:
            raise ValidationError(
                {"terms_version": ["Acepta los términos y condiciones para continuar."]}
            )
        if not privacy_version:
            raise ValidationError(
                {
                    "privacy_version": [
                        "Acepta la política de privacidad para continuar."
                    ]
                }
            )
        check_password_strength(password=password, user=User(email=invitation.email))
        try:
            with transaction.atomic():
                user = User.objects.create_user(
                    email=invitation.email,
                    password=password,
                    is_email_verified=True,
                    has_own_workspace=False,
                )
        except IntegrityError:
            # La invitación de otra empresa al mismo correo la creó mientras
            # tanto: ahora se entra con su contraseña (iteracion-16).
            raise AccountJustCreated() from None
        record_acceptance(
            user=user,
            terms_version=terms_version,
            privacy_version=privacy_version,
            ip_address=ip_address,
            user_agent=user_agent,
        )
    else:
        if not user.check_password(password):
            raise ValidationError({"password": ["La contraseña no es correcta."]})
        if not user.is_email_verified:
            user.is_email_verified = True
            user.save(update_fields=["is_email_verified", "updated_at"])

    Membership.objects.get_or_create(account=invitation.account, user=user)
    invitation.status = Invitation.Status.ACCEPTED
    invitation.accepted_at = timezone.now()
    invitation.save(update_fields=["status", "accepted_at"])
    logger.info(
        "Invitation accepted",
        extra={"user_id": str(user.pk), "account_id": str(invitation.account_id)},
    )
    return Accepted(user=user, account=invitation.account)


def _owned_member(*, account: User, member_id) -> Membership:
    membership = get_member(account=account, member_id=member_id)
    if membership is None:
        raise NotFound("Ese colaborador no está en tu empresa.")
    return membership


def set_member_active(*, account: User, member_id, is_active: bool) -> Membership:
    """Activar o desactivar a un colaborador (US-138).

    Desactivado no entra a la empresa desde su siguiente petición; lo que
    registró sigue ahí.
    """
    membership = _owned_member(account=account, member_id=member_id)
    membership.is_active = is_active
    membership.save(update_fields=["is_active", "updated_at"])
    logger.info(
        "Collaborator toggled",
        extra={"membership_id": str(membership.pk), "active": is_active},
    )
    return membership


def remove_member(*, account: User, member_id) -> None:
    """Quitar a un colaborador de la empresa (US-138).

    Deja de estar en ella; lo que registró es de la empresa y se queda. Su
    cuenta sigue siendo suya —puede colaborar en otras o volver si lo invitan—:
    borrarla es decisión de esa persona, no del administrador.
    """
    membership = _owned_member(account=account, member_id=member_id)
    membership.delete()
    logger.info("Collaborator removed", extra={"account_id": str(account.pk)})


def _owned_waiting_invitation(*, account: User, invitation_id) -> Invitation:
    """Una invitación de la empresa que todavía espera respuesta.

    Raises:
        NotFound: no es de esta empresa.
        ValidationError: ya se aceptó o ya se canceló.
    """
    invitation = get_invitation(account=account, invitation_id=invitation_id)
    if invitation is None:
        raise NotFound("Esa invitación no es de tu empresa.")
    if invitation.status == Invitation.Status.ACCEPTED:
        raise ValidationError(
            {"detail": "Esta invitación ya se aceptó: ya es colaborador."}
        )
    if invitation.status == Invitation.Status.CANCELLED:
        raise ValidationError({"detail": "Esta invitación ya se canceló."})
    return invitation


class EmailNotSent(APIException):
    """El correo no salió y nada cambió: el enlace anterior sigue sirviendo."""

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_code = "email_not_sent"

    def __init__(self) -> None:
        super().__init__(
            {
                "detail": (
                    "No pudimos enviar el correo. El enlace anterior sigue "
                    "sirviendo; intenta de nuevo en un momento."
                ),
                "code": "email_not_sent",
            }
        )


def resend_invitation(*, account: User, invitation_id) -> Sent:
    """Reenviar una invitación pendiente o vencida (US-139).

    Sale con un enlace nuevo que vale 7 días, y el anterior deja de servir sólo
    cuando el correo salió: si no sale, la persona se queda con el enlace que ya
    tenía en vez de quedarse sin ninguno (iteracion-16).

    Raises:
        EmailNotSent: el correo no salió; la invitación quedó como estaba.
    """
    invitation = _owned_waiting_invitation(account=account, invitation_id=invitation_id)
    token, token_hash = _new_link()
    sent = _send(invitation, token)
    if not sent.email_sent:
        raise EmailNotSent()
    invitation.token_hash = token_hash
    invitation.sent_at = timezone.now()
    invitation.expires_at = invitation.sent_at + timedelta(days=INVITATION_DAYS)
    invitation.save(update_fields=["token_hash", "sent_at", "expires_at"])
    return sent


#: Las acciones en lote de la tabla de colaboradores (iteracion-17). Reenviar
#: invitaciones en lote no está: sale con la iteración de seguridad.
TEAM_BULK_ACTIONS = ("activate", "deactivate", "delete", "cancel")

#: Por qué una acción de colaboradores no aplica a una invitación, y al revés.
NOT_A_MEMBER = "Es una invitación, no un colaborador."
NOT_AN_INVITATION = "Es un colaborador, no una invitación."


def bulk_team_action(*, account: User, action: str, ids: list) -> BulkResult:
    """Activa, desactiva, quita o cancela varios de la tabla a la vez (US-138).

    Cada fila por su cuenta y en su propio bloque atómico: la que no es de esa
    clase —desactivar una invitación, cancelar a un colaborador— o ya no está,
    dice por qué en ``failed`` y las demás siguen.
    """
    result = BulkResult()
    for item_id in ids:
        result.requested += 1
        membership = get_member(account=account, member_id=item_id)
        invitation = (
            None
            if membership is not None
            else get_invitation(account=account, invitation_id=item_id)
        )
        if membership is None and invitation is None:
            result.fail(item_id, NOT_FOUND)
            continue
        try:
            with transaction.atomic():
                if action == "cancel":
                    if invitation is None:
                        raise ValidationError(NOT_AN_INVITATION)
                    cancel_invitation(account=account, invitation_id=item_id)
                elif membership is None:
                    raise ValidationError(NOT_A_MEMBER)
                elif action == "delete":
                    remove_member(account=account, member_id=item_id)
                else:
                    set_member_active(
                        account=account,
                        member_id=item_id,
                        is_active=action == "activate",
                    )
        except (ValidationError, NotFound) as exc:
            result.fail(item_id, error_text(exc))
        else:
            result.processed += 1
    logger.info(
        "Team bulk action",
        extra={
            "action": action,
            "requested": result.requested,
            "processed": result.processed,
        },
    )
    return result


def cancel_invitation(*, account: User, invitation_id) -> None:
    """Cancelar una invitación pendiente (US-139): su enlace deja de servir."""
    invitation = _owned_waiting_invitation(account=account, invitation_id=invitation_id)
    invitation.status = Invitation.Status.CANCELLED
    invitation.save(update_fields=["status"])
    logger.info("Invitation cancelled", extra={"invitation_id": str(invitation.pk)})
