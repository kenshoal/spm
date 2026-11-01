import pytest

TEST_INTERNAL_TOKEN = "test-internal-token"


@pytest.fixture(autouse=True)
def internal_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """Services sending events hold this token (hotfix 17)."""
    monkeypatch.setenv("NOTIFICATION_INTERNAL_TOKEN", TEST_INTERNAL_TOKEN)
