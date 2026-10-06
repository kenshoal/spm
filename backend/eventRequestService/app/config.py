from functools import lru_cache

from pydantic import AnyHttpUrl, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Server-only configuration for the event request service."""

    supabase_url: AnyHttpUrl
    supabase_secret_key: SecretStr
    auth_service_url: AnyHttpUrl = "http://127.0.0.1:8001"
    # notificationService's POST /notifications/events. Unset means nothing is
    # sent and the outbox relay does not run, so submission events stay queued.
    notification_service_url: AnyHttpUrl | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
