import pytest

from app.block_repository import block_repository
from app.config import Settings, get_settings
from app.main import app
from app.repository import repository


@pytest.fixture(autouse=True)
def _clear_repository() -> None:
    previous = app.dependency_overrides.copy()
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None,
        venue_storage_backend="memory",
        supabase_url=None,
        supabase_secret_key=None,
        venue_environment="development",
        venue_allow_stub_auth=False,
        venue_dev_staff_user_id=None,
        event_allocations_url=None,
        event_allocations_token=None,
    )
    repository.clear()
    block_repository.clear()
    yield
    repository.clear()
    block_repository.clear()
    app.dependency_overrides.clear()
    app.dependency_overrides.update(previous)
