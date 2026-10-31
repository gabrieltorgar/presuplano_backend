"""Accounts views (orchestration only; logic lives in services)."""

import uuid

from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import status
from rest_framework.exceptions import (
    AuthenticationFailed,
    PermissionDenied,
    ValidationError,
)
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

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
    SessionRefreshSerializer,
    UserAccountSerializer,
    VerifyOtpSerializer,
)
from apps.accounts.services import (
    cancel_email_change,
    change_password,
    confirm_email_change,
    delete_account,
    flush_expired_sessions,
    get_my_organization,
    login_user,
    normalize_email,
    organization_logo_data_url,
    register_user,
    request_email_change,
    resend_email_change,
    resend_otp,
    reset_password,
    start_password_reset,
    start_session,
    verify_account,
)
from apps.legal.services import client_ip
from apps.team.permissions import IsCompanyAdmin
from apps.team.tenancy import account_of, is_company_admin
from common.auth_cookies import (
    clear_session_cookies,
    refresh_from,
    set_session_cookies,
    set_token_cookies,
)
from common.authentication import CredentialExchangeMixin
from common.cron import CronSecretAuthentication, IsCronJob
from common.permissions import IsVerifiedUser
from common.recaptcha import Verdict, guard_public_form


@method_decorator(ensure_csrf_cookie, name="get")
class CsrfCookieView(APIView):
    """GET /api/auth/csrf/ — deja la cookie CSRF que la SPA repite en X-CSRFToken.

    Pública a propósito: no devuelve datos ni cambia nada, y la SPA la llama al
    arrancar y antes de entrar, cuando todavía no hay sesión. Sin autenticación,
    una cookie de acceso vencida no la convierte en 401.
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request: Request) -> Response:
        return Response(status=status.HTTP_204_NO_CONTENT)


class RegisterView(CredentialExchangeMixin, APIView):
    """POST /api/auth/register/ — crear una cuenta con correo y contraseña.

    Abre la sesión de la cuenta sin verificar en las cookies HttpOnly (el
    cuerpo es sólo la cuenta): con ella la SPA pide ``me/`` y lleva a la
    pantalla del código; ninguna ruta de datos la acepta hasta verificar
    (IsVerifiedUser, iteracion-26 #12).
    """

    permission_classes = [AllowAny]
    # Intercambio de credenciales: una cookie de acceso vieja no lo vuelve 401.
    authentication_classes: list = []
    throttle_scope = "register"

    def post(self, request: Request) -> Response:
        verdict = guard_public_form(
            request,
            action="signup_submit",
            when_unavailable="reject",
            remote_ip=client_ip(request),
        )
        if verdict is Verdict.DROP:
            # La respuesta de un registro, sin cuenta detrás.
            return Response(
                {
                    "id": str(uuid.uuid4()),
                    "email": normalize_email(request.data.get("email")),
                    "is_email_verified": False,
                },
                status=status.HTTP_201_CREATED,
            )

        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = register_user(
            ip_address=client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
            **serializer.validated_data,
        )
        response = Response(
            UserAccountSerializer(user).data, status=status.HTTP_201_CREATED
        )
        set_session_cookies(response, start_session(user=user))
        get_token(request)
        return response


class VerifyOtpView(CredentialExchangeMixin, APIView):
    """POST /api/auth/verify-otp/ — dar por bueno el correo con el código.

    Verificar es entrar (iteracion-26 #12): deja una sesión nueva de esa
    cuenta en las cookies, también en un navegador que llegó por el acceso
    de una cuenta sin verificar, sin volver a pedir la contraseña.
    """

    permission_classes = [AllowAny]
    authentication_classes: list = []  # el código es la credencial
    throttle_scope = "otp"

    def post(self, request: Request) -> Response:
        serializer = VerifyOtpSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = verify_account(**serializer.validated_data)
        response = Response(UserAccountSerializer(user).data, status=status.HTTP_200_OK)
        set_session_cookies(response, start_session(user=user))
        get_token(request)
        return response


class ResendOtpView(CredentialExchangeMixin, APIView):
    """POST /api/auth/resend-otp/ — volver a pedir el código de verificación."""

    permission_classes = [AllowAny]
    authentication_classes: list = []  # basta el correo; no lee la sesión
    throttle_scope = "otp"

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


class LoginView(CredentialExchangeMixin, APIView):
    """POST /api/auth/login/ — abrir la sesión en cookies HttpOnly.

    El cuerpo sólo trae la cuenta: los tokens van en cookies que JavaScript no
    puede leer, y el token CSRF en la suya, que la SPA sí lee para escribir.
    """

    permission_classes = [AllowAny]
    # Intercambio de credenciales: no lee la sesión, así que ni una cookie de
    # acceso muerta (401) ni una viva sin X-CSRFToken (403) impiden entrar. El
    # CSRF de login lo cierran los parsers de solo JSON.
    authentication_classes: list = []
    throttle_scope = "login"

    def post(self, request: Request) -> Response:
        verdict = guard_public_form(
            request,
            action="login_submit",
            when_unavailable="reject",
            remote_ip=client_ip(request),
        )
        if verdict is Verdict.DROP:
            raise AuthenticationFailed("Credenciales inválidas")

        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user, session = login_user(**serializer.validated_data)
        response = Response(
            {"user": UserAccountSerializer(user).data}, status=status.HTTP_200_OK
        )
        set_session_cookies(response, session)
        get_token(request)
        return response


class SessionRefreshView(APIView):
    """POST /api/auth/refresh/ — renovar la sesión con el refresh de la cookie.

    El refresh rota y el usado queda en la lista negra. Sin sesión o con una
    anulada responde 401 y borra las cookies. Público a propósito: lo que
    autoriza es la cookie de refresh, no el access vencido. Sólo la cookie:
    un refresh en el cuerpo no se lee (iteracion-26 #10), y el cuerpo de la
    respuesta nunca trae tokens.
    """

    permission_classes = [AllowAny]
    authentication_classes: list = []

    def post(self, request: Request) -> Response:
        raw = refresh_from(request)
        serializer = SessionRefreshSerializer(data={"refresh": raw or ""})
        try:
            serializer.is_valid(raise_exception=True)
        except (AuthenticationFailed, TokenError, ValidationError):
            response = Response(
                {"detail": "La sesión terminó. Vuelve a iniciar sesión."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
            clear_session_cookies(response)
            return response
        response = Response({"detail": "Sesión renovada."}, status=status.HTTP_200_OK)
        set_token_cookies(
            response,
            access=serializer.validated_data["access"],
            refresh=serializer.validated_data.get("refresh", raw),
        )
        get_token(request)
        return response


class LogoutView(APIView):
    """POST /api/auth/logout/ — cerrar la sesión: anula el refresh y borra las cookies.

    Público a propósito: salir sin sesión no falla, y una sesión vencida
    también tiene que poder cerrarse.
    """

    permission_classes = [AllowAny]
    authentication_classes: list = []

    def post(self, request: Request) -> Response:
        raw = refresh_from(request)
        if raw:
            try:
                RefreshToken(raw).blacklist()
            except TokenError:
                pass  # ya vencida o anulada: no queda nada que cerrar
        response = Response(status=status.HTTP_204_NO_CONTENT)
        clear_session_cookies(response)
        return response


class FlushExpiredTokensView(APIView):
    """GET /api/cron/flush-expired-tokens/ — borrar las sesiones vencidas.

    La llama el cron diario de Vercel (vercel.json → crons) con
    ``Authorization: Bearer <CRON_SECRET>``. Ninguna sesión la abre: sin el
    secreto configurado, sin la cabecera o con otro secreto responde 401 y
    no corre (common/cron.py).
    """

    authentication_classes = [CronSecretAuthentication]
    permission_classes = [IsCronJob]

    def get(self, request: Request) -> Response:
        flush_expired_sessions()
        return Response(status=status.HTTP_204_NO_CONTENT)


class PasswordResetRequestView(CredentialExchangeMixin, APIView):
    """POST /api/auth/password-reset/ — pedir recuperar la contraseña."""

    permission_classes = [AllowAny]
    authentication_classes: list = []  # quien la olvidó no tiene sesión
    throttle_scope = "password_reset"

    def post(self, request: Request) -> Response:
        verdict = guard_public_form(
            request,
            action="password_reset_request",
            when_unavailable="reject",
            remote_ip=client_ip(request),
        )
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if verdict is not Verdict.DROP:
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


class PasswordResetConfirmView(CredentialExchangeMixin, APIView):
    """POST /api/auth/password-reset/confirm/ — fijar la contraseña nueva."""

    permission_classes = [AllowAny]
    authentication_classes: list = []  # el código es la credencial
    throttle_scope = "otp"

    def post(self, request: Request) -> Response:
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = reset_password(**serializer.validated_data)
        return Response(UserAccountSerializer(user).data, status=status.HTTP_200_OK)


class MyAccountView(APIView):
    """GET/PATCH /api/auth/me/ — la cuenta de quien pregunta y su correo."""

    # GET sin verificar (VERIFICATION_EXEMPT): con ``is_email_verified`` en
    # falso, la SPA lleva a la pantalla del código. Lo demás pide verificar.
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.request.method == "GET":
            return super().get_permissions()
        return [IsVerifiedUser()]

    def get(self, request: Request) -> Response:
        # La SPA lo pide al arrancar: asegura la cookie CSRF aunque haya vencido.
        get_token(request)
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

    permission_classes = [IsVerifiedUser]

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

    permission_classes = [IsVerifiedUser]
    throttle_scope = "otp"

    def post(self, request: Request) -> Response:
        serializer = EmailChangeConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = confirm_email_change(user=request.user, **serializer.validated_data)
        return Response(MyAccountSerializer(user).data, status=status.HTTP_200_OK)


class MyEmailResendView(APIView):
    """POST /api/auth/me/email/resend/ — volver a mandar el código al correo nuevo."""

    permission_classes = [IsVerifiedUser]
    throttle_scope = "otp"

    def post(self, request: Request) -> Response:
        user = resend_email_change(user=request.user)
        return Response(MyAccountSerializer(user).data, status=status.HTTP_200_OK)


class MyPasswordView(APIView):
    """POST /api/auth/me/password/ — cambiar la contraseña sabiendo la actual."""

    permission_classes = [IsVerifiedUser]

    def post(self, request: Request) -> Response:
        serializer = PasswordChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = change_password(user=request.user, **serializer.validated_data)
        response = Response(
            {"detail": "Tu contraseña quedó cambiada."}, status=status.HTTP_200_OK
        )
        # Las demás sesiones quedaron anuladas; ésta sigue con una nueva.
        set_session_cookies(response, start_session(user=user))
        return response


class MyAccountDeleteView(APIView):
    """POST /api/auth/me/delete/ — eliminar la cuenta con todo lo suyo.

    Es un POST y no un DELETE porque lleva cuerpo —la contraseña que lo
    confirma— y no todos los intermediarios respetan el cuerpo de un DELETE.
    """

    permission_classes = [IsVerifiedUser]

    def post(self, request: Request) -> Response:
        serializer = DeleteAccountSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        delete_account(user=request.user, **serializer.validated_data)
        response = Response(status=status.HTTP_204_NO_CONTENT)
        clear_session_cookies(response)
        return response


class MyOrganizationView(APIView):
    """GET/PATCH /api/auth/organization/ — the letterhead of the documents."""

    permission_classes = [IsVerifiedUser]
    # El logotipo llega como multipart; el nombre y el color, como JSON.
    parser_classes = [MultiPartParser, JSONParser]

    def get(self, request: Request) -> Response:
        # La de la empresa en la que se trabaja (iteracion-14).
        organization = get_my_organization(user=account_of(request))
        return Response(OrganizationSerializer(organization).data)

    def patch(self, request: Request) -> Response:
        # La identidad de la empresa la cambia sólo su administrador (US-140).
        if not is_company_admin(request):
            raise PermissionDenied(IsCompanyAdmin.message)
        organization = get_my_organization(user=account_of(request))
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

    permission_classes = [IsVerifiedUser]

    def get(self, request: Request) -> Response:
        return Response(
            {"data_url": organization_logo_data_url(user=account_of(request))}
        )
