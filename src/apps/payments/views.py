"""Payments views: register payment, list, summary and voucher."""

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from apps.payments.selectors import list_payments_for_owner
from apps.payments.serializers import PaymentInputSerializer, PaymentSerializer
from apps.payments.services import (
    build_voucher,
    pending_balance,
    register_payment,
    total_paid,
)
from apps.projects.models import Project
from apps.projects.selectors import advanced_value


class PaymentViewSet(viewsets.ReadOnlyModelViewSet):
    """List/register payments; project payment summary; payment voucher."""

    serializer_class = PaymentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        project_id = self.request.query_params.get("project")
        return list_payments_for_owner(owner=self.request.user, project_id=project_id)

    def _get_project(self) -> Project:
        project_id = self.request.query_params.get("project")
        project = Project.objects.filter(id=project_id, owner=self.request.user).first()
        if project is None:
            raise NotFound("Proyecto no encontrado.")
        return project

    def create(self, request: Request, *args, **kwargs) -> Response:
        serializer = PaymentInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payment = register_payment(owner=request.user, **serializer.validated_data)
        return Response(PaymentSerializer(payment).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["get"])
    def summary(self, request: Request) -> Response:
        project = self._get_project()
        payments = list_payments_for_owner(owner=request.user, project_id=project.id)
        return Response(
            {
                "advanced_value": advanced_value(project),
                "total_paid": total_paid(project),
                "pending_balance": pending_balance(project),
                "payments": PaymentSerializer(payments, many=True).data,
            }
        )

    @action(detail=False, methods=["get"])
    def voucher(self, request: Request) -> Response:
        project = self._get_project()
        return Response(build_voucher(project=project))
