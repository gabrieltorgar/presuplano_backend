"""Tests for the session refresh endpoint (silent session renewal).

A valid refresh must yield a fresh access so an active session is never dropped
when the short-lived access expires. Since iteracion-12 both travel in HttpOnly
cookies; since iteracion-26 #10 a refresh in the body is not read (no client
sends it, and a script holding one cannot turn it into a session).
"""

import pytest
from rest_framework import status
from rest_framework.test import APIClient

LOGIN_URL = "/api/auth/login/"
REFRESH_URL = "/api/auth/refresh/"


@pytest.mark.django_db
class TestTokenRefresh:
    """POST /api/auth/refresh/ exchanges the refresh for a new session."""

    def test_valid_refresh_cookie_renews_the_session(
        self, api_client, user_factory
    ) -> None:
        """The refresh cookie set at login yields new session cookies."""
        account = user_factory(is_email_verified=True, password="testpass123")
        api_client.post(LOGIN_URL, {"email": account.email, "password": "testpass123"})

        response = api_client.post(REFRESH_URL)

        assert response.status_code == status.HTTP_200_OK
        assert response.cookies["itzaka_access"].value
        assert "access" not in response.data

    def test_a_refresh_sent_in_the_body_is_ignored(
        self, api_client, user_factory
    ) -> None:
        """CRD-02.1 · iteracion-26 #10 — Only the cookie renews the session."""
        account = user_factory(is_email_verified=True, password="testpass123")
        login = api_client.post(
            LOGIN_URL, {"email": account.email, "password": "testpass123"}
        )
        refresh = login.cookies["itzaka_refresh"].value

        response = APIClient().post(REFRESH_URL, {"refresh": refresh})

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert not response.cookies["itzaka_access"].value

    def test_invalid_refresh_returns_401(self, api_client) -> None:
        """A bogus refresh token is rejected with 401."""
        response = api_client.post(REFRESH_URL, {"refresh": "not-a-real-token"})

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
