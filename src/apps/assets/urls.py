"""Assets URLs (router)."""

from rest_framework.routers import DefaultRouter

from apps.assets.views import CatalogModelViewSet, PlanAssetViewSet

router = DefaultRouter()
router.register("plan-assets", PlanAssetViewSet, basename="plan-asset")
router.register("plan-models", CatalogModelViewSet, basename="plan-model")

urlpatterns = router.urls
