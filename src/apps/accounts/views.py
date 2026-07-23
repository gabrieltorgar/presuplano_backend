"""Accounts views (orchestration only; logic lives in services)."""

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.serializers import (
    LoginSerializer,
    RegisterSerializer,
    UserAccountSerializer,
    VerifyOtpSerializer,
)
from apps.accounts.services import login_user, register_user, verify_phone


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


class VerifyOtpView(APIView):
    """POST /api/auth/verify-otp/ — verify the phone with the universal OTP."""

    permission_classes = [AllowAny]

    def post(self, request: Request) -> Response:
        serializer = VerifyOtpSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = verify_phone(**serializer.validated_data)
        return Response(UserAccountSerializer(user).data, status=status.HTTP_200_OK)


class LoginView(APIView):
    """POST /api/auth/login/ — authenticate and return JWT tokens."""

    permission_classes = [AllowAny]

    def post(self, request: Request) -> Response:
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user, tokens = login_user(**serializer.validated_data)
        return Response(
            {**tokens, "user": UserAccountSerializer(user).data},
            status=status.HTTP_200_OK,
        )
