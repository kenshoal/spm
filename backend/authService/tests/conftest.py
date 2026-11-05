from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.integrations import supabase as supabase_integration
from app.main import app, verified_users


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def _fresh_auth_caches() -> Iterator[None]:
    """Stop a remembered /auth/me result or shared client leaking across tests."""
    verified_users.clear()
    supabase_integration.get_supabase_verifier_client.cache_clear()
    supabase_integration.get_supabase_admin_client.cache_clear()
    yield
    verified_users.clear()
    supabase_integration.get_supabase_verifier_client.cache_clear()
    supabase_integration.get_supabase_admin_client.cache_clear()
