"""Top-level API views (health check)."""

from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthView(APIView):
    """Liveness probe — returns 200 with a status payload."""

    permission_classes = [AllowAny]

    def get(self, request: Request) -> Response:
        """Return service health."""
        return Response({"status": "ok", "service": "presuplano-backend"})
