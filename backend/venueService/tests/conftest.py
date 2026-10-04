import pytest

from app.block_repository import block_repository
from app.config import get_settings
from app.dependencies import Principal, require_authenticated, require_venue_staff
from app.main import app
from app.repository import _supabase_repository, repository


@pytest.fixture(autouse=True)
def _clear_repository(monkeypatch: pytest.MonkeyPatch) -> None:
    # Unit tests always use the in-memory store, whatever the local .env says.
    monkeypatch.setenv("VENUE_STORAGE_BACKEND", "memory")
    get_settings.cache_clear()
    _supabase_repository.cache_clear()
    principal = Principal(
        user_id="00000000-0000-0000-0000-000000000001",
        roles=("venue_staff",),
    )
    app.dependency_overrides[require_authenticated] = lambda: principal
    app.dependency_overrides[require_venue_staff] = lambda: principal
    repository.clear()
    block_repository.clear()
    yield
    repository.clear()
    block_repository.clear()
    app.dependency_overrides.clear()
