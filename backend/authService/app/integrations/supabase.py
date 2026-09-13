from functools import lru_cache

from supabase import Client, create_client

from app.config import get_settings


@lru_cache
def get_supabase_client() -> Client:
    settings = get_settings()
    return create_client(
        str(settings.supabase_url).rstrip("/"),
        settings.supabase_publishable_key.get_secret_value(),
    )
