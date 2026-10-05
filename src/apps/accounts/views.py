"""Accounts views (orchestration only; logic lives in services)."""

from rest_framework import status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.serializers import (
    DeleteAccountSerializer,
    EmailChangeConfirmSerializer,
    EmailChangeSerializer,
    LoginSerializer,
    MyAccountSerializer,
    OrganizationSerializer,
    PasswordChangeSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    RegisterSerializer,
    ResendOtpSerializer,
    UserAccountSerializer,
    VerifyOtpSerializer,
)
from apps.accounts.services import (
    cancel_email_change,
    change_password,
    confirm_email_change,
    delete_account,
    get_my_organization,
    login_user,
    organization_logo_data_url,
    register_user,
    request_email_change,
    resend_email_change,
    resend_otp,
    reset_password,
    start_password_reset,
    verify_account,
)
from apps.legal.services import client_ip


class RegisterView(APIView):
    """POST /api/auth/register/ — crear una cuenta con correo y contraseña."""

    permission_classes = [AllowAny]

    def post(self, request: Request) -> Response:
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = register_user(
            ip_address=client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
            **serializer.validated_data,
        )
        return Response(
            UserAccountSerializer(user).data, status=status.HTTP_201_CREATED
        )


class VerifyOtpView(APIView):
    """POST /api/auth/verify-otp/ — dar por bueno el correo con el código."""

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
    """GET/PATCH /api/auth/me/ — la cuenta de quien pregunta y su correo."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        return Response(MyAccountSerializer(request.user).data)

    def patch(self, request: Request) -> Response:
        """Empezar a cambiar el correo; es lo mismo que ``POST me/email/``."""
        serializer = EmailChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request_email_change(user=request.user, **serializer.validated_data)
        return Response(MyAccountSerializer(user).data, status=status.HTTP_200_OK)


class MyEmailView(APIView):
    """POST/DELETE /api/auth/me/email/ — pedir un correo nuevo, o desistir.

    El correo nuevo queda pendiente y recibe su código; la cuenta sigue
    entrando con el de siempre hasta que se confirma.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        serializer = EmailChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request_email_change(user=request.user, **serializer.validated_data)
        return Response(MyAccountSerializer(user).data, status=status.HTTP_200_OK)

    def delete(self, request: Request) -> Response:
        user = cancel_email_change(user=request.user)
        return Response(MyAccountSerializer(user).data, status=status.HTTP_200_OK)


class MyEmailVerifyView(APIView):
    """POST /api/auth/me/email/verify/ — confirmar el correo nuevo con su código."""

    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        serializer = EmailChangeConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = confirm_email_change(user=request.user, **serializer.validated_data)
        return Response(MyAccountSerializer(user).data, status=status.HTTP_200_OK)


class MyEmailResendView(APIView):
    """POST /api/auth/me/email/resend/ — volver a mandar el código al correo nuevo."""

    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        user = resend_email_change(user=request.user)
        return Response(MyAccountSerializer(user).data, status=status.HTTP_200_OK)


class MyPasswordView(APIView):
    """POST /api/auth/me/password/ — cambiar la contraseña sabiendo la actual."""

    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        serializer = PasswordChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        change_password(user=request.user, **serializer.validated_data)
        return Response(
            {"detail": "Tu contraseña quedó cambiada."}, status=status.HTTP_200_OK
        )


class MyAccountDeleteView(APIView):
    """POST /api/auth/me/delete/ — eliminar la cuenta con todo lo suyo.

    Es un POST y no un DELETE porque lleva cuerpo —la contraseña que lo
    confirma— y no todos los intermediarios respetan el cuerpo de un DELETE.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        serializer = DeleteAccountSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        delete_account(user=request.user, **serializer.validated_data)
        return Response(status=status.HTTP_204_NO_CONTENT)


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
