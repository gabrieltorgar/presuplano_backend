"""Dashboard view: the account's summary, in one request."""

from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.dashboard.selectors import build_dashboard
from apps.team.tenancy import account_of
from common.permissions import IsVerifiedUser


class DashboardView(APIView):
    """GET /dashboard/ — lo que se ve al abrir la aplicación."""

    permission_classes = [IsVerifiedUser]

    def get(self, request: Request) -> Response:
        return Response(build_dashboard(owner=account_of(request)))
