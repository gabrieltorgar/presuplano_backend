"""Views de colaboradores: invitar y gestionar a quien trabaja en la empresa."""

from django.middleware.csrf import get_token
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.serializers import UserAccountSerializer
from apps.accounts.services import find_user, start_session
from apps.legal.services import client_ip
from apps.team.permissions import IsCompanyAdmin
from apps.team.selectors import (
    DEFAULT_TEAM_ORDERING,
    company_name,
    invitation_row,
    member_row,
    team_of,
)
from apps.team.serializers import (
    AcceptInvitationSerializer,
    InvitationPreviewSerializer,
    InviteResultSerializer,
    InviteSerializer,
    MemberUpdateSerializer,
    TeamRowSerializer,
)
from apps.team.services import (
    TEAM_BULK_ACTIONS,
    accept_invitation,
    bulk_team_action,
    cancel_invitation,
    decoy_acceptance,
    find_invitation,
    invitation_state,
    invite_collaborators,
    remove_member,
    resend_invitation,
    set_member_active,
)
from apps.team.tenancy import account_of
from common.auth_cookies import set_session_cookies
from common.bulk import BulkSelectionSerializer, bulk_max_items
from common.pagination import DefaultPagination
from common.permissions import IsVerifiedUser
from common.recaptcha import Verdict, guard_public_form


class InvitationsView(APIView):
    """POST /api/collaborators/invitations/ — invitar a uno o varios correos.

    Responde 201 si salió al menos una invitación; si todos los correos ya
    estaban, 200 con el porqué de cada uno.
    """

    permission_classes = [IsVerifiedUser, IsCompanyAdmin]
    throttle_scope = "invitations"

    def post(self, request: Request) -> Response:
        serializer = InviteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = invite_collaborators(
            account=account_of(request), emails=serializer.validated_data["emails"]
        )
        return Response(
            InviteResultSerializer(result).data,
            status=status.HTTP_201_CREATED if result.invited else status.HTTP_200_OK,
        )


class InvitationDetailView(APIView):
    """GET /api/invitations/<token>/ — de quién es la invitación y si sirve.

    Público: lo que autoriza es el enlace, que sólo tiene quien recibió el
    correo. Sin autenticación, para que una sesión vieja no estorbe.
    """

    permission_classes = [AllowAny]
    authentication_classes: list = []
    throttle_scope = "invitation"

    def get(self, request: Request, token: str) -> Response:
        invitation = find_invitation(token=token)
        data = {
            "email": invitation.email,
            "company": company_name(account=invitation.account),
            "status": invitation_state(invitation),
            "account_exists": find_user(email=invitation.email) is not None,
            "expires_at": invitation.expires_at,
        }
        return Response(InvitationPreviewSerializer(data).data)


class InvitationAcceptView(APIView):
    """POST /api/invitations/<token>/accept/ — aceptar y entrar a la empresa.

    Crea la cuenta si hace falta y abre la sesión, como el acceso. Lleva
    reCAPTCHA y campo trampa: es un formulario público que crea cuentas.
    """

    permission_classes = [AllowAny]
    authentication_classes: list = []
    throttle_scope = "login"

    def post(self, request: Request, token: str) -> Response:
        verdict = guard_public_form(
            request,
            action="invitation_accept",
            when_unavailable="reject",
            remote_ip=client_ip(request),
        )
        if verdict is Verdict.DROP:
            # La respuesta de siempre, con la empresa como una de verdad, sin
            # cuenta ni sesión detrás (iteracion-16).
            return Response(
                decoy_acceptance(token=token), status=status.HTTP_201_CREATED
            )

        serializer = AcceptInvitationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        accepted = accept_invitation(
            token=token,
            ip_address=client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
            **serializer.validated_data,
        )
        response = Response(
            {
                "user": UserAccountSerializer(accepted.user).data,
                # A esta empresa entra: la aplicación la deja elegida.
                "company": {
                    "id": str(accepted.account.pk),
                    "name": company_name(account=accepted.account),
                },
            },
            status=status.HTTP_201_CREATED,
        )
        set_session_cookies(response, start_session(user=accepted.user))
        get_token(request)
        return response


def team_rows(request: Request) -> list[dict]:
    """Las filas de la tabla como las pide la query string de la lista.

    ``?search=`` busca en el correo; ``?status=a,b`` filtra por varios estados
    (active, inactive, pending, expired); ``?ordering=`` es email, -email,
    since o -since. La lista y sus acciones en lote leen lo mismo.
    """
    params = request.query_params
    statuses = frozenset(
        part.strip() for part in (params.get("status") or "").split(",") if part.strip()
    )
    return team_of(
        account=account_of(request),
        search=(params.get("search") or "").strip(),
        statuses=statuses,
        ordering=(params.get("ordering") or DEFAULT_TEAM_ORDERING).strip(),
    )


class TeamView(APIView):
    """GET /api/collaborators/ — colaboradores e invitaciones que esperan (US-138).

    Por páginas, como toda lista (iteracion-17): ``{count, next, previous,
    results}`` con ``?page=`` y ``?page_size=`` (20 por omisión, hasta 100).
    """

    permission_classes = [IsVerifiedUser, IsCompanyAdmin]

    def get(self, request: Request) -> Response:
        paginator = DefaultPagination()
        page = paginator.paginate_queryset(team_rows(request), request, view=self)
        return paginator.get_paginated_response(TeamRowSerializer(page, many=True).data)


class TeamBulkView(APIView):
    """POST /api/collaborators/bulk/<acción>/ — activar, desactivar, quitar o
    cancelar varios a la vez (US-138, iteracion-17).

    El cuerpo trae los ids o «todos los resultados» con la query string de la
    lista; la respuesta es ``{requested, processed, failed}``.
    """

    permission_classes = [IsVerifiedUser, IsCompanyAdmin]
    throttle_scope = "bulk"

    def post(self, request: Request, action: str) -> Response:
        if action not in TEAM_BULK_ACTIONS:
            raise NotFound("Esa acción no existe.")
        limit = bulk_max_items()
        selection = BulkSelectionSerializer(
            data=request.data, context={"max_items": limit}
        )
        selection.is_valid(raise_exception=True)
        data = selection.validated_data
        if data["select_all"]:
            excluded = {str(item) for item in data["exclude_ids"]}
            ids = [
                row["id"]
                for row in team_rows(request)
                if str(row["id"]) not in excluded
            ]
            if len(ids) > limit:
                raise serializers.ValidationError(
                    {
                        "select_all": [
                            f"La selección tiene {len(ids)} registros; el máximo por "
                            f"acción es {limit}. Acota los filtros."
                        ]
                    }
                )
        else:
            ids = data["ids"]
        result = bulk_team_action(account=account_of(request), action=action, ids=ids)
        return Response(result.as_dict())


class MemberView(APIView):
    """PATCH/DELETE /api/collaborators/members/<id>/ — activar, desactivar, quitar."""

    permission_classes = [IsVerifiedUser, IsCompanyAdmin]

    def patch(self, request: Request, member_id) -> Response:
        serializer = MemberUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        membership = set_member_active(
            account=account_of(request),
            member_id=member_id,
            is_active=serializer.validated_data["is_active"],
        )
        return Response(TeamRowSerializer(member_row(membership)).data)

    def delete(self, request: Request, member_id) -> Response:
        remove_member(account=account_of(request), member_id=member_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


class InvitationResendView(APIView):
    """POST /api/collaborators/invitations/<id>/resend/ — enlace nuevo (US-139).

    Responde la fila con ``email_sent``; si el correo no sale, 503 con
    ``code: email_not_sent`` y el enlace anterior sigue sirviendo.
    """

    permission_classes = [IsVerifiedUser, IsCompanyAdmin]
    throttle_scope = "invitations"

    def post(self, request: Request, invitation_id) -> Response:
        sent = resend_invitation(
            account=account_of(request), invitation_id=invitation_id
        )
        row = TeamRowSerializer(invitation_row(sent.invitation)).data
        return Response({**row, "email_sent": sent.email_sent})


class InvitationCancelView(APIView):
    """POST /api/collaborators/invitations/<id>/cancel/ — su enlace deja de servir."""

    permission_classes = [IsVerifiedUser, IsCompanyAdmin]

    def post(self, request: Request, invitation_id) -> Response:
        cancel_invitation(account=account_of(request), invitation_id=invitation_id)
        return Response(status=status.HTTP_204_NO_CONTENT)
