"""Staff views: the register, the hand-outs and the payments."""

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from apps.staff.models import Worker
from apps.staff.selectors import (
    list_assignments_for_owner,
    list_worker_payments_for_owner,
    list_workers_for_owner,
    worker_totals,
)
from apps.staff.serializers import (
    AssignmentInputSerializer,
    AssignmentSerializer,
    WorkerPaymentInputSerializer,
    WorkerPaymentSerializer,
    WorkerSerializer,
)
from apps.staff.services import assign_service, pay_worker, set_worker_services


class WorkerViewSet(viewsets.ModelViewSet):
    """CRUD del personal de la cuenta, con lo que hace y lo que se le debe."""

    serializer_class = WorkerSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return list_workers_for_owner(owner=self.request.user)

    def perform_create(self, serializer) -> None:
        services = serializer.validated_data.pop("services", [])
        self._guard_single_self(serializer.validated_data.get("is_self", False))
        worker = serializer.save(owner=self.request.user)
        set_worker_services(worker=worker, services=services)

    def perform_update(self, serializer) -> None:
        services = serializer.validated_data.pop("services", None)
        if serializer.validated_data.get("is_self", False):
            self._guard_single_self(True, exclude=serializer.instance.pk)
        worker = serializer.save()
        if services is not None:
            set_worker_services(worker=worker, services=services)

    def _guard_single_self(self, is_self: bool, exclude=None) -> None:
        """«Yo» es uno solo: dos despachos propios no significan nada."""
        if not is_self:
            return
        others = Worker.objects.filter(owner=self.request.user, is_self=True)
        if exclude is not None:
            others = others.exclude(pk=exclude)
        if others.exists():
            raise ValidationError("Ya tienes un registro tuyo en el personal")


class AssignmentViewSet(viewsets.ModelViewSet):
    """El reparto de las partidas de un proyecto entre el personal."""

    serializer_class = AssignmentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return list_assignments_for_owner(
            owner=self.request.user,
            project_id=self.request.query_params.get("project"),
        )

    def _hand_out(self, request: Request, payload: dict):
        serializer = AssignmentInputSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        if data["project"].owner_id != request.user.id:
            raise NotFound("Proyecto no encontrado.")
        return assign_service(**data)

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
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return list_worker_payments_for_owner(
            owner=self.request.user,
            worker_id=self.request.query_params.get("worker"),
            project_id=self.request.query_params.get("project"),
        )

    def create(self, request: Request, *args, **kwargs) -> Response:
        serializer = WorkerPaymentInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payment = pay_worker(owner=request.user, **serializer.validated_data)
        return Response(
            WorkerPaymentSerializer(payment).data, status=status.HTTP_201_CREATED
        )

    @action(detail=False, methods=["get"])
    def summary(self, request: Request) -> Response:
        """Las cuatro cifras de una persona, con sus pagos."""
        worker_id = request.query_params.get("worker")
        worker = Worker.objects.filter(id=worker_id, owner=request.user).first()
        if worker is None:
            raise NotFound("Personal no encontrado.")

        project_id = request.query_params.get("project")
        payments = list_worker_payments_for_owner(
            owner=request.user, worker_id=worker_id, project_id=project_id
        )
        return Response(
            {
                "worker_name": worker.name,
                **worker_totals(worker, project_id=project_id),
                "payments": WorkerPaymentSerializer(payments, many=True).data,
            }
        )
