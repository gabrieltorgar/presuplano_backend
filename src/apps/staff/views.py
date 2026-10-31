"""Staff views: the register, the hand-outs and the payments."""

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.request import Request
from rest_framework.response import Response

from apps.staff.filters import AssignmentFilter, WorkerFilter, WorkerPaymentFilter
from apps.staff.selectors import (
    get_owned_worker,
    list_assignments_for_owner,
    list_worker_payments_for_owner,
    staff_totals,
    worker_rows_for_owner,
    worker_totals,
)
from apps.staff.serializers import (
    AssignmentInputSerializer,
    AssignmentSerializer,
    WorkerPaymentInputSerializer,
    WorkerPaymentSerializer,
    WorkerSerializer,
)
from apps.staff.services import (
    ensure_single_self,
    hand_out,
    pay_worker,
    set_worker_services,
)
from apps.team.tenancy import account_of
from common.permissions import IsVerifiedUser


class WorkerViewSet(viewsets.ModelViewSet):
    """CRUD del personal de la cuenta, con lo que hace y lo que se le debe.

    La lista (US-96 · US-97, iteracion-17): ``?has_balance=true``, ``?kind=``,
    ``?service=<id>`` (quienes hacen ese servicio) e ``?id=a,b``; busca por
    nombre, teléfono, correo y los servicios que cobra; ordena por saldo o por
    nombre, primero a quienes más se les debe.
    """

    serializer_class = WorkerSerializer
    permission_classes = [IsVerifiedUser]
    filterset_class = WorkerFilter
    search_fields = ("name", "phone", "email", "services__tariff__name")
    ordering_fields = ("balance", "name")
    ordering_text_fields = ("name",)
    ordering = ("-balance", "name", "id")

    def get_queryset(self):
        return worker_rows_for_owner(owner=account_of(self.request))

    @action(detail=False, methods=["get"])
    def totals(self, request: Request) -> Response:
        """GET /workers/totals/ — lo que se les debe y lo repartido, de todos."""
        return Response(staff_totals(owner=account_of(request)))

    def perform_create(self, serializer) -> None:
        services = serializer.validated_data.pop("services", [])
        if serializer.validated_data.get("is_self", False):
            ensure_single_self(owner=account_of(self.request))
        worker = serializer.save(owner=account_of(self.request))
        set_worker_services(worker=worker, services=services)

    def perform_update(self, serializer) -> None:
        services = serializer.validated_data.pop("services", None)
        if serializer.validated_data.get("is_self", False):
            ensure_single_self(
                owner=account_of(self.request), exclude=serializer.instance.pk
            )
        worker = serializer.save()
        if services is not None:
            set_worker_services(worker=worker, services=services)


class AssignmentViewSet(viewsets.ModelViewSet):
    """El reparto de las partidas de un proyecto entre el personal."""

    serializer_class = AssignmentSerializer
    permission_classes = [IsVerifiedUser]
    # La lista (iteracion-17): por páginas, ``?project=`` y ``?worker=``.
    filterset_class = AssignmentFilter
    search_fields = ("worker__name", "quote_item__name")
    ordering_fields = ("created_at", "quantity")
    ordering = ("created_at", "id")

    def get_queryset(self):
        return list_assignments_for_owner(owner=account_of(self.request))

    def _hand_out(self, request: Request, payload: dict):
        serializer = AssignmentInputSerializer(
            data=payload, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        return hand_out(owner=account_of(request), **serializer.validated_data)

    def create(self, request: Request, *args, **kwargs) -> Response:
        assignment = self._hand_out(request, request.data)
        return Response(
            AssignmentSerializer(assignment).data, status=status.HTTP_201_CREATED
        )

    def update(self, request: Request, *args, **kwargs) -> Response:
        # Repartir de nuevo lo mismo es corregirlo: una sola puerta de entrada.
        instance = self.get_object()
        assignment = self._hand_out(
            request,
            {
                "project": str(instance.project_id),
                "quote_item": str(instance.quote_item_id),
                "worker": str(instance.worker_id),
                **request.data,
            },
        )
        return Response(AssignmentSerializer(assignment).data)


class WorkerPaymentViewSet(viewsets.ReadOnlyModelViewSet):
    """Pagos al personal, y lo que queda debiéndose."""

    serializer_class = WorkerPaymentSerializer
    permission_classes = [IsVerifiedUser]
    # La lista (iteracion-17): por páginas, ``?worker=`` y ``?project=``, en
    # orden de fecha.
    filterset_class = WorkerPaymentFilter
    search_fields = ("worker__name", "note")
    ordering_fields = ("date", "amount", "created_at")
    ordering = ("date", "created_at", "id")

    def get_queryset(self):
        return list_worker_payments_for_owner(owner=account_of(self.request))

    def create(self, request: Request, *args, **kwargs) -> Response:
        serializer = WorkerPaymentInputSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        payment = pay_worker(owner=account_of(request), **serializer.validated_data)
        return Response(
            WorkerPaymentSerializer(payment).data, status=status.HTTP_201_CREATED
        )

    @action(detail=False, methods=["get"])
    def summary(self, request: Request) -> Response:
        """Las cuatro cifras de una persona, con sus pagos."""
        worker_id = request.query_params.get("worker")
        worker = get_owned_worker(owner=account_of(request), worker_id=worker_id)
        if worker is None:
            raise NotFound("Personal no encontrado.")

        project_id = request.query_params.get("project")
        payments = list_worker_payments_for_owner(
            owner=account_of(request), worker_id=worker_id, project_id=project_id
        )
        return Response(
            {
                "worker_name": worker.name,
                **worker_totals(worker, project_id=project_id),
                "payments": WorkerPaymentSerializer(payments, many=True).data,
            }
        )
