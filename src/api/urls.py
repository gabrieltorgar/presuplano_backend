"""Root API URLs including each app."""

from django.urls import include, path

from api.views import HealthView

urlpatterns = [
    path("health/", HealthView.as_view(), name="health"),
    path("auth/", include("apps.accounts.urls")),
]
