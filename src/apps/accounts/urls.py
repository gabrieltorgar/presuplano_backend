"""Accounts (auth) URLs. Endpoints are added per user story via TDD."""

from django.urls import path

from apps.accounts.views import LoginView, RegisterView, VerifyOtpView

app_name = "accounts"

urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("verify-otp/", VerifyOtpView.as_view(), name="verify-otp"),
    path("login/", LoginView.as_view(), name="login"),
]
