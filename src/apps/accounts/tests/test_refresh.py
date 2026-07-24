"""Tests for the token refresh endpoint (silent session renewal).

A valid refresh token must yield a fresh access token so an active session is
never dropped when the short-lived access token expires.
"""

import pytest
from rest_framework import status

LOGIN_URL = "/api/auth/login/"
REFRESH_URL = "/api/auth/refresh/"


@pytest.mark.django_db
class TestTokenRefresh:
    """POST /api/auth/refresh/ exchanges a refresh token for a new access."""

    def test_valid_refresh_returns_new_access_token(
        self, api_client, user_factory
    ) -> None:
        """A refresh token obtained at login yields a new access token."""
        account = user_factory(is_phone_verified=True, password="testpass123")
        login = api_client.post(
            LOGIN_URL, {"phone": account.phone, "password": "testpass123"}
        )
        refresh = login.data["refresh"]

        response = api_client.post(REFRESH_URL, {"refresh": refresh})

        assert response.status_code == status.HTTP_200_OK
        assert response.data["access"]

    def test_invalid_refresh_returns_401(self, api_client) -> None:
        """A bogus refresh token is rejected with 401."""
        response = api_client.post(REFRESH_URL, {"refresh": "not-a-real-token"})

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
