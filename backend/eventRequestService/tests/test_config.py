import pytest
from pydantic import ValidationError

from app.config import Settings


# Purpose: Confirms the service reads its Supabase server configuration from the environment.
def test_settings_load_supabase_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://project.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_test")

    settings = Settings(_env_file=None)

    assert str(settings.supabase_url) == "https://project.supabase.co/"
    assert settings.supabase_secret_key.get_secret_value() == "sb_secret_test"


# Purpose: Prevents the service from silently starting database operations without a secret.
def test_settings_require_supabase_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://project.supabase.co")
    monkeypatch.delenv("SUPABASE_SECRET_KEY", raising=False)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)
