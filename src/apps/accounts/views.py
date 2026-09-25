"""Accounts views (orchestration only; logic lives in services)."""

from rest_framework import status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
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
    ResendOtpSerializer,
    UpdateMyAccountSerializer,
    UserAccountSerializer,
    VerifyOtpSerializer,
)
from apps.accounts.services import (
    get_my_organization,
    login_user,
    organization_logo_data_url,
    register_user,
    resend_otp,
    reset_password,
    start_password_reset,
    update_my_account,
    verify_account,
)


class RegisterView(APIView):
    """POST /api/auth/register/ — crear una cuenta (teléfono o correo)."""

    permission_classes = [AllowAny]

    def post(self, request: Request) -> Response:
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = register_user(**serializer.validated_data)
        return Response(
            UserAccountSerializer(user).data, status=status.HTTP_201_CREATED
        )


class VerifyOtpView(APIView):
    """POST /api/auth/verify-otp/ — dar por buena la identidad con el código."""

    permission_classes = [AllowAny]

    def post(self, request: Request) -> Response:
        serializer = VerifyOtpSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = verify_account(**serializer.validated_data)
        return Response(UserAccountSerializer(user).data, status=status.HTTP_200_OK)


class ResendOtpView(APIView):
    """POST /api/auth/resend-otp/ — volver a pedir el código de verificación."""

    permission_classes = [AllowAny]

    def post(self, request: Request) -> Response:
        serializer = ResendOtpSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        resend_otp(**serializer.validated_data)
        # La misma respuesta exista o no la cuenta: no se revela quién es cliente.
        return Response(
            {
                "detail": (
                    "Si esa cuenta está pendiente de verificar, te enviamos el "
                    "código otra vez."
                )
            },
            status=status.HTTP_200_OK,
        )


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
                    "Si esos datos tienen una cuenta, te enviamos el código "
                    "para continuar."
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
    """GET/PATCH /api/auth/me/ — la cuenta de quien pregunta, y cómo se entra."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        return Response(MyAccountSerializer(request.user).data)

    def patch(self, request: Request) -> Response:
        """Cambiar el teléfono o el correo con los que se entra."""
        serializer = UpdateMyAccountSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = update_my_account(user=request.user, **serializer.validated_data)
        return Response(MyAccountSerializer(user).data, status=status.HTTP_200_OK)


class MyOrganizationView(APIView):
    """GET/PATCH /api/auth/organization/ — the letterhead of the documents."""

    permission_classes = [IsAuthenticated]
    # El logotipo llega como formulario; el nombre y el color, como JSON.
    parser_classes = [MultiPartParser, FormParser, JSONParser]

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


class MyOrganizationLogoView(APIView):
    """GET /api/auth/organization/logo/ — el logotipo listo para imprimirse.

    Devuelve la imagen incrustada en la respuesta y no su dirección: el PDF se
    dibuja en el navegador, y el navegador no puede bajar del bucket un archivo
    de otro dominio que no lo autoriza. Sin esto, el documento salía sin marca.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        return Response({"data_url": organization_logo_data_url(user=request.user)})
