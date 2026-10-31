"""Lecturas de colaboradores e invitaciones."""

from django.db.models import QuerySet

from apps.accounts.models import Organization, User
from apps.team.models import Invitation, Membership


def company_name(*, account: User) -> str:
    """Cómo se llama la empresa: el nombre de su organización, o su correo."""
    name = (
        Organization.objects.filter(user=account).values_list("name", flat=True).first()
    )
    return name or account.email


def is_member(*, account: User, email: str) -> bool:
    """Si ``email`` ya colabora (activo o no) en la empresa de ``account``."""
    return Membership.objects.filter(account=account, user__email=email).exists()


def pending_invitation(*, account: User, email: str) -> Invitation | None:
    """La invitación pendiente de ``email`` en esa empresa, vencida o no."""
    return Invitation.objects.filter(
        account=account, email=email, status=Invitation.Status.PENDING
    ).first()


def member_row(membership: Membership) -> dict:
    """Un colaborador como fila de la tabla del administrador."""
    return {
        "id": membership.id,
        "kind": "member",
        "email": membership.user.email,
        "status": "active" if membership.is_active else "inactive",
        "since": membership.created_at,
        "expires_at": None,
    }


def invitation_row(invitation: Invitation) -> dict:
    """Una invitación que espera respuesta, como fila de la misma tabla."""
    return {
        "id": invitation.id,
        "kind": "invitation",
        "email": invitation.email,
        "status": "expired" if invitation.is_expired else "pending",
        "since": invitation.sent_at,
        "expires_at": invitation.expires_at,
    }


#: Cómo se ordena la tabla: por correo (de la A a la Z, por omisión) o desde
#: cuándo. Lo que no está aquí no se ordena (iteracion-17).
TEAM_ORDERINGS = {
    "email": (lambda row: row["email"].lower(), False),
    "-email": (lambda row: row["email"].lower(), True),
    "since": (lambda row: row["since"], False),
    "-since": (lambda row: row["since"], True),
}
DEFAULT_TEAM_ORDERING = "email"


def team_of(
    *,
    account: User,
    search: str = "",
    statuses: frozenset[str] = frozenset(),
    ordering: str = DEFAULT_TEAM_ORDERING,
) -> list[dict]:
    """Quién colabora en la empresa y a quién se espera (US-138).

    Los colaboradores y las invitaciones pendientes o vencidas en una sola
    tabla: las aceptadas ya son colaboradores y las canceladas no esperan a
    nadie. ``statuses`` filtra por varios estados a la vez y ``ordering`` es uno
    de ``TEAM_ORDERINGS``, con el id como desempate para que ninguna fila se
    repita ni se pierda entre páginas (iteracion-17). Son dos tablas que no se
    juntan en la base, y una empresa tiene decenas de colaboradores, no miles:
    se juntan aquí y la vista las corta en páginas.
    """
    members = Membership.objects.filter(account=account).select_related("user")
    invitations = Invitation.objects.filter(
        account=account, status=Invitation.Status.PENDING
    )
    if search:
        members = members.filter(user__email__icontains=search)
        invitations = invitations.filter(email__icontains=search)
    rows = [member_row(m) for m in members] + [invitation_row(i) for i in invitations]
    if statuses:
        rows = [row for row in rows if row["status"] in statuses]
    key, descending = TEAM_ORDERINGS.get(
        ordering, TEAM_ORDERINGS[DEFAULT_TEAM_ORDERING]
    )
    rows.sort(key=lambda row: str(row["id"]))
    rows.sort(key=key, reverse=descending)
    return rows


def get_member(*, account: User, member_id) -> Membership | None:
    """El colaborador de esa empresa con ese id, o nada si es de otra."""
    return (
        Membership.objects.select_related("user")
        .filter(account=account, pk=member_id)
        .first()
    )


def invitations_of(*, account: User) -> QuerySet[Invitation]:
    """Las invitaciones de esa empresa.

    De aquí relee, con su fila bloqueada, el servicio que va a cambiar una
    (SEC-03, iteracion-26 #20).
    """
    return Invitation.objects.filter(account=account)


def get_invitation(*, account: User, invitation_id) -> Invitation | None:
    """La invitación de esa empresa con ese id, o nada si es de otra."""
    return invitations_of(account=account).filter(pk=invitation_id).first()
