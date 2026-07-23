"""Accounts (auth) URLs. Endpoints are added per user story via TDD."""

from django.urls import path

from apps.accounts.views import RegisterView

app_name = "accounts"

urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
]
