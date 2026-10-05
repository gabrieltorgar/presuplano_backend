"""Documents URLs."""

from django.urls import path

from apps.documents.views import SendDocumentView

app_name = "documents"

urlpatterns = [
    path("documents/send/", SendDocumentView.as_view(), name="send"),
]
