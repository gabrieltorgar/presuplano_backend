"""Health endpoint tests (scaffold baseline)."""

import pytest
from rest_framework import status


@pytest.mark.django_db
class TestHealth:
    """The health endpoint is public and reports service status."""

    def test_health_returns_200_ok(self, api_client) -> None:
        response = api_client.get("/api/health/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == "ok"
