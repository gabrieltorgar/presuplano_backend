"""Assets URLs (router)."""

from rest_framework.routers import DefaultRouter

from apps.assets.views import PlanAssetViewSet

router = DefaultRouter()
router.register("plan-assets", PlanAssetViewSet, basename="plan-asset")

urlpatterns = router.urls
