"""Root API URLs including each app."""

from django.urls import include, path

from api.views import HealthView

urlpatterns = [
    path("health/", HealthView.as_view(), name="health"),
    path("auth/", include("apps.accounts.urls")),
    path("", include("apps.catalog.urls")),
    path("", include("apps.clients.urls")),
    path("", include("apps.quotes.urls")),
    path("", include("apps.projects.urls")),
    path("", include("apps.payments.urls")),
    path("", include("apps.leads.urls")),
    path("", include("apps.planner.urls")),
    path("", include("apps.staff.urls")),
    path("", include("apps.dashboard.urls")),
    path("", include("apps.assets.urls")),
    path("", include("apps.documents.urls")),
]
