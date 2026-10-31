"""Los errores de la API, en palabras de la aplicación."""

import datetime
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.db.models import ProtectedError, RestrictedError
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.test import APIClient, APIRequestFactory
from rest_framework.views import APIView

from apps.accounts.otp_quota import OTPCooldown
from apps.staff.models import Worker, WorkerPayment
from apps.staff.tests.factories import WorkerFactory
from common.exceptions import CONFLICT_MESSAGE, api_exception_handler


class TestConflicto:
    """Bug iteracion-16 - Dos peticiones simultáneas no terminan en un 500.

    Cuando dos peticiones chocan con una restricción única de la base, la
    segunda pierde: se le dice qué pasó y que lo intente de nuevo.
    """

    def test_a_unique_conflict_is_a_409(self) -> None:
        response = api_exception_handler(IntegrityError("duplicate key"), {})

        assert response is not None
        assert response.status_code == status.HTTP_409_CONFLICT
        assert response.data == {"detail": CONFLICT_MESSAGE, "code": "conflict"}

    def test_the_database_message_never_reaches_the_client(self) -> None:
        response = api_exception_handler(
            IntegrityError(
                'duplicate key value violates "team_invitation_one_pending"'
            ),
            {},
        )

        assert "team_invitation" not in str(response.data)


def test_exception_handler_is_registered(settings) -> None:
    """ERR-B01 · iteracion-25 #3: el manejador del contrato es el de la API."""
    assert (
        settings.REST_FRAMEWORK["EXCEPTION_HANDLER"]
        == "common.exceptions.api_exception_handler"
    )


class _ServiceErrorView(APIView):
    """Una vista cuyo servicio rechaza la operación por una regla de negocio."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = []
    error: DjangoValidationError | None = None

    def post(self, request):
        raise self.error


@pytest.mark.parametrize(
    ("error", "body"),
    [
        (
            DjangoValidationError({"status": "Transición no permitida."}),
            {"status": ["Transición no permitida."]},
        ),
        (
            DjangoValidationError("El pedido ya fue facturado."),
            {"non_field_errors": ["El pedido ya fue facturado."]},
        ),
    ],
)
def test_service_validation_error_returns_400_with_field_dict(error, body) -> None:
    """ERR-B01 · iteracion-25 #3: sin el manejador, DRF responde 500."""
    request = APIRequestFactory().post("/fake/", {}, format="json")

    response = _ServiceErrorView.as_view(error=error)(request)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data == body


class TestBorrarAlgoEnUso:
    """Bug iteracion-25 #3 - Borrar algo en uso dice por qué no se puede.

    ``ProtectedError`` y ``RestrictedError`` heredan de ``IntegrityError``: sin
    un caso propio, el 409 pedía reintentar algo que nunca va a pasar.
    """

    def test_protected_rows_are_a_409_that_names_what_uses_them(self) -> None:
        worker = Worker(name="Juan")
        payment = WorkerPayment(worker=worker, amount=Decimal("1"))

        response = api_exception_handler(ProtectedError("protected", {payment}), {})

        assert response.status_code == status.HTTP_409_CONFLICT
        assert response.data["detail"] != CONFLICT_MESSAGE
        assert "No se puede eliminar" in response.data["detail"]
        assert "pagos a personal" in response.data["detail"]

    def test_restricted_rows_are_a_409_that_names_what_uses_them(self) -> None:
        worker = Worker(name="Juan")
        payment = WorkerPayment(worker=worker, amount=Decimal("1"))

        response = api_exception_handler(RestrictedError("restricted", {payment}), {})

        assert response.status_code == status.HTTP_409_CONFLICT
        assert response.data["detail"] != CONFLICT_MESSAGE
        assert "pagos a personal" in response.data["detail"]

    @pytest.mark.django_db
    def test_deleting_a_worker_with_payments_is_a_409_that_says_why(self, user) -> None:
        """DELETE /api/workers/{id}/ de alguien a quien ya se le pagó."""
        worker = WorkerFactory(owner=user)
        WorkerPayment.objects.create(
            owner=user,
            worker=worker,
            amount=Decimal("500"),
            date=datetime.date(2026, 10, 30),
        )
        client = APIClient()
        client.force_authenticate(user=user)
        client.raise_request_exception = False

        response = client.delete(f"/api/workers/{worker.id}/")

        assert response.status_code == status.HTTP_409_CONFLICT
        assert response.data["detail"] != CONFLICT_MESSAGE
        assert "No se puede eliminar" in response.data["detail"]
        assert "pagos a personal" in response.data["detail"]
        assert Worker.objects.filter(id=worker.id).exists()


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("url", "params"),
    [
        ("/api/payments/summary/", {"project": "x"}),
        ("/api/payments/voucher/", {"project": "x"}),
        ("/api/worker-payments/summary/", {"worker": "x"}),
    ],
)
def test_an_id_that_is_not_a_uuid_is_a_400_with_its_reason(user, url, params) -> None:
    """Bug iteracion-25 #3: el ValidationError de Django al filtrar era un 500."""
    client = APIClient()
    client.force_authenticate(user=user)
    client.raise_request_exception = False

    response = client.get(url, params)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "UUID" in str(response.data["non_field_errors"])


@pytest.mark.parametrize(
    ("wait", "text"),
    [
        (42, "Intenta de nuevo en 42 segundos."),
        (3600, "Intenta de nuevo en 60 minutos."),
    ],
)
def test_the_otp_cooldown_is_a_429_with_retry_after(wait, text) -> None:
    """CRD-04.2 · iteracion-26 #14 — La espera del código de un solo uso se dice
    como la aplicación, con cuánto falta en ``Retry-After``."""
    response = api_exception_handler(OTPCooldown(wait=wait), {})

    assert response is not None
    assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert response["Retry-After"] == str(wait)
    assert response.data == {"detail": f"Ya te enviamos un código. {text}"}


@pytest.mark.django_db
class TestCuerpoDemasiadoGrande:
    """API-02 · iteracion-27 #7 — Un cuerpo de más de DATA_UPLOAD_MAX_MEMORY_SIZE
    es un 400 que dice por qué, con la forma de la API: nunca la página «Bad
    Request» de Django sin motivo (la SPA solo podía decir «400»)."""

    def test_a_body_over_the_cap_is_a_400_with_its_reason(self, settings, user) -> None:
        settings.DATA_UPLOAD_MAX_MEMORY_SIZE = 1024
        client = APIClient()
        client.force_authenticate(user=user)

        response = client.post(
            "/api/plans/",
            {"name": "Casa Reyes", "document": {"walls": [], "notes": "x" * 4096}},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["code"] == "request_too_big"
        assert "pesa más de" in response.data["detail"]

    def test_the_handler_names_the_cap(self, settings) -> None:
        from django.core.exceptions import RequestDataTooBig

        settings.DATA_UPLOAD_MAX_MEMORY_SIZE = 4 * 1024 * 1024

        response = api_exception_handler(RequestDataTooBig("too big"), {})

        assert response is not None
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data == {
            "detail": (
                "Lo que enviaste pesa más de 4 MB, lo más que recibe el servidor. "
                "Si es un plano, lo que más pesa suele ser el plano de fondo "
                "escaneado o una textura suelta."
            ),
            "code": "request_too_big",
        }
