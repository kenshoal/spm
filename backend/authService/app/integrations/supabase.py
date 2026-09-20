from supabase import Client, create_client

from app.config import get_settings


def get_supabase_client() -> Client:
    settings = get_settings()
    return create_client(
        str(settings.supabase_url).rstrip("/"),
        settings.supabase_publishable_key.get_secret_value(),
    )


def get_supabase_admin_client() -> Client:
    settings = get_settings()
    if settings.supabase_secret_key is None:
        raise ValueError("SUPABASE_SECRET_KEY is not configured")
    return create_client(
        str(settings.supabase_url).rstrip("/"),
        settings.supabase_secret_key.get_secret_value(),
    )
