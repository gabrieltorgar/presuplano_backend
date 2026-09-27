"""Legal URLs."""

from django.urls import path

from apps.legal.views import LegalAcceptView, LegalDocumentsView, LegalDocumentView

app_name = "legal"

urlpatterns = [
    path("legal/", LegalDocumentsView.as_view(), name="documents"),
    path("legal/accept/", LegalAcceptView.as_view(), name="accept"),
    path("legal/<str:kind>/", LegalDocumentView.as_view(), name="document"),
]
