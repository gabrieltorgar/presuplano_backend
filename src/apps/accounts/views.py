"""Accounts views (orchestration only; logic lives in services)."""

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.serializers import RegisterSerializer, UserAccountSerializer
from apps.accounts.services import register_user


class RegisterView(APIView):
    """POST /api/auth/register/ — create an account (phone + password)."""

    permission_classes = [AllowAny]

    def post(self, request: Request) -> Response:
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = register_user(**serializer.validated_data)
        return Response(
            UserAccountSerializer(user).data, status=status.HTTP_201_CREATED
        )
