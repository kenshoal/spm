from unittest.mock import Mock

import pytest

from app.config import get_settings
from app.integrations import supabase as supabase_integration


def test_supabase_client_uses_configured_publishable_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", "sb_publishable_test")
    create_client = Mock(return_value=object())
    monkeypatch.setattr(supabase_integration, "create_client", create_client)
    get_settings.cache_clear()

    first_client = supabase_integration.get_supabase_client()
    second_client = supabase_integration.get_supabase_client()

    assert first_client is create_client.return_value
    assert second_client is create_client.return_value
    assert create_client.call_count == 2
    create_client.assert_called_with(
        "https://example.supabase.co",
        "sb_publishable_test",
    )

    get_settings.cache_clear()
