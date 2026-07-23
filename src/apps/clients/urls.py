"""Clients URLs (router)."""

from rest_framework.routers import DefaultRouter

from apps.clients.views import ClientViewSet

router = DefaultRouter()
router.register("clients", ClientViewSet, basename="client")

urlpatterns = router.urls
