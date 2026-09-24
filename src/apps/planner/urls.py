"""Planner URLs (router)."""

from rest_framework.routers import DefaultRouter

from apps.planner.views import PlanViewSet

router = DefaultRouter()
router.register("plans", PlanViewSet, basename="plan")

urlpatterns = router.urls
