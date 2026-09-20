import pytest

from app.repository import repository


@pytest.fixture(autouse=True)
def _clear_repository() -> None:
    repository.clear()
    yield
    repository.clear()
