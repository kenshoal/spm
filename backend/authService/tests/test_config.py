import pytest
from pydantic import ValidationError

from app.config import Settings


def test_settings_load_supabase_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", "sb_publishable_test")

    settings = Settings()

    assert str(settings.supabase_url) == "https://example.supabase.co/"
    assert settings.supabase_publishable_key.get_secret_value() == (
        "sb_publishable_test"
    )
    assert "sb_publishable_test" not in repr(settings)


def test_settings_require_supabase_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_PUBLISHABLE_KEY", raising=False)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)
