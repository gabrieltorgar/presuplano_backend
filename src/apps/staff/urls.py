"""Staff URLs (router)."""

from rest_framework.routers import DefaultRouter

from apps.staff.views import AssignmentViewSet, WorkerPaymentViewSet, WorkerViewSet

router = DefaultRouter()
router.register("workers", WorkerViewSet, basename="worker")
router.register("assignments", AssignmentViewSet, basename="assignment")
router.register("worker-payments", WorkerPaymentViewSet, basename="worker-payment")

urlpatterns = router.urls
