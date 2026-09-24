"""Planner views: account-scoped plan CRUD."""

from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from apps.planner.selectors import list_plans_for_owner
from apps.planner.serializers import PlanSerializer, PlanSummarySerializer


class PlanViewSet(viewsets.ModelViewSet):
    """CRUD for the authenticated account's plans (isolated per account)."""

    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return list_plans_for_owner(owner=self.request.user)

    def get_serializer_class(self):
        return PlanSummarySerializer if self.action == "list" else PlanSerializer

    def perform_create(self, serializer) -> None:
        serializer.save(owner=self.request.user)
