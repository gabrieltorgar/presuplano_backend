"""Root pytest fixtures shared across apps."""

import pytest
from rest_framework.test import APIClient

from apps.accounts.tests.factories import UserFactory


@pytest.fixture
def api_client() -> APIClient:
    """Unauthenticated DRF API client."""
    return APIClient()


@pytest.fixture
def user_factory() -> type[UserFactory]:
    """Expose the user factory to tests."""
    return UserFactory


@pytest.fixture
def user(db):
    """A persisted, verified user."""
    return UserFactory()


@pytest.fixture
def authenticated_client(user) -> APIClient:
    """DRF API client force-authenticated as ``user``."""
    client = APIClient()
    client.force_authenticate(user=user)
    return client
