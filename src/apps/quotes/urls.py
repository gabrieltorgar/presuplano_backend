"""Quotes URLs (router)."""

from rest_framework.routers import DefaultRouter

from apps.quotes.views import QuoteViewSet

router = DefaultRouter()
router.register("quotes", QuoteViewSet, basename="quote")

urlpatterns = router.urls
