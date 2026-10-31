"""Payments views: register payment, list, summary and voucher."""

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.request import Request
from rest_framework.response import Response

from apps.payments.filters import PaymentFilter
from apps.payments.selectors import get_owned_project, list_payments_for_owner
from apps.payments.serializers import PaymentInputSerializer, PaymentSerializer
from apps.payments.services import (
    build_voucher,
    credit_balance,
    receivable_balance,
    register_payment,
    total_paid,
)
from apps.projects.models import Project
from apps.projects.selectors import advanced_value, quoted_value
from apps.team.tenancy import account_of
from common.permissions import IsVerifiedUser


class PaymentViewSet(viewsets.ReadOnlyModelViewSet):
    """List/register payments; project payment summary; payment voucher."""

    serializer_class = PaymentSerializer
    permission_classes = [IsVerifiedUser]
    # La lista (iteracion-17): por páginas, ``?project=`` y en orden de fecha.
    # Sin búsqueda: se piden los de un proyecto, no se buscan.
    filterset_class = PaymentFilter
    search_fields = ()
    ordering_fields = ("date", "amount", "created_at")
    ordering = ("date", "created_at", "id")

    def get_queryset(self):
        return list_payments_for_owner(owner=account_of(self.request))

    def _get_project(self) -> Project:
        project_id = self.request.query_params.get("project")
        project = get_owned_project(
            owner=account_of(self.request), project_id=project_id
        )
        if project is None:
            raise NotFound("Proyecto no encontrado.")
        return project

    def create(self, request: Request, *args, **kwargs) -> Response:
        serializer = PaymentInputSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        payment = register_payment(
            owner=account_of(request), **serializer.validated_data
        )
        return Response(PaymentSerializer(payment).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["get"])
    def summary(self, request: Request) -> Response:
        project = self._get_project()
        payments = list_payments_for_owner(
            owner=account_of(request), project_id=project.id
        )
        return Response(
            {
                "advanced_value": advanced_value(project),
                "quoted_value": quoted_value(project),
                "total_paid": total_paid(project),
                "pending_balance": receivable_balance(project),
                "credit_balance": credit_balance(project),
                "client_name": project.quote.client.name,
                "payments": PaymentSerializer(payments, many=True).data,
            }
        )

    @action(detail=False, methods=["get"])
    def voucher(self, request: Request) -> Response:
        project = self._get_project()
        return Response(build_voucher(project=project))
