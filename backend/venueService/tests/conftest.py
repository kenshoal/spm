import pytest

from app.dependencies import Principal, require_authenticated, require_venue_staff
from app.main import app
from app.repository import repository


@pytest.fixture(autouse=True)
def _clear_repository() -> None:
    principal = Principal(
        user_id="00000000-0000-0000-0000-000000000001",
        roles=("venue_staff",),
    )
    app.dependency_overrides[require_authenticated] = lambda: principal
    app.dependency_overrides[require_venue_staff] = lambda: principal
    repository.clear()
    yield
    repository.clear()
    app.dependency_overrides.clear()
