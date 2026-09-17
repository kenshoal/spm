import pytest

from app.block_repository import block_repository
from app.repository import repository


@pytest.fixture(autouse=True)
def _clear_repository() -> None:
    repository.clear()
    block_repository.clear()
    yield
    repository.clear()
    block_repository.clear()
