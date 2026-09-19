"""Accounts views (orchestration only; logic lives in services)."""

from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.serializers import (
    LoginSerializer,
    MyAccountSerializer,
    OrganizationSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    RegisterSerializer,
    UserAccountSerializer,
    VerifyOtpSerializer,
)
from apps.accounts.services import (
    get_my_organization,
    login_user,
    register_user,
    reset_password,
    start_password_reset,
    verify_phone,
)


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


class PasswordResetRequestView(APIView):
    """POST /api/auth/password-reset/ — pedir recuperar la contraseña."""

    permission_classes = [AllowAny]

    def post(self, request: Request) -> Response:
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        start_password_reset(**serializer.validated_data)
        # La misma respuesta exista o no la cuenta: no se revela quién es cliente.
        return Response(
            {
                "detail": (
                    "Si ese teléfono tiene una cuenta, puedes continuar con el "
                    "código de verificación."
                )
            },
            status=status.HTTP_200_OK,
        )


class PasswordResetConfirmView(APIView):
    """POST /api/auth/password-reset/confirm/ — fijar la contraseña nueva."""

    permission_classes = [AllowAny]

    def post(self, request: Request) -> Response:
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = reset_password(**serializer.validated_data)
        return Response(UserAccountSerializer(user).data, status=status.HTTP_200_OK)


class MyAccountView(APIView):
    """GET /api/auth/me/ — the account of whoever is asking."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        return Response(MyAccountSerializer(request.user).data)


class MyOrganizationView(APIView):
    """GET/PATCH /api/auth/organization/ — the letterhead of the documents."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        organization = get_my_organization(user=request.user)
        return Response(OrganizationSerializer(organization).data)

    def patch(self, request: Request) -> Response:
        organization = get_my_organization(user=request.user)
        serializer = OrganizationSerializer(
            organization, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)
