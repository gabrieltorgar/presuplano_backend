"""Accounts (auth) URLs. Endpoints are added per user story via TDD."""

from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from apps.accounts.views import (
    LoginView,
    MyAccountView,
    RegisterView,
    VerifyOtpView,
)

app_name = "accounts"

urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("verify-otp/", VerifyOtpView.as_view(), name="verify-otp"),
    path("login/", LoginView.as_view(), name="login"),
    path("me/", MyAccountView.as_view(), name="me"),
    # Exchange a valid refresh token for a fresh access token (silent renew).
    path("refresh/", TokenRefreshView.as_view(), name="refresh"),
]
