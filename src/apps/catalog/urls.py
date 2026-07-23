"""Catalog URLs (router)."""

from rest_framework.routers import DefaultRouter

from apps.catalog.views import TariffViewSet

router = DefaultRouter()
router.register("tariffs", TariffViewSet, basename="tariff")

urlpatterns = router.urls
