from functools import lru_cache

from pydantic import AnyHttpUrl, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class NotificationSettings(BaseSettings):
    """Optional delivery config independent of a repository's credentials."""

    # notificationService's POST /notifications/events. Unset means nothing is
    # sent and neither outbox relay runs; submission/review work stays queued.
    notification_service_url: AnyHttpUrl | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


class Settings(NotificationSettings):
    """Server-only configuration for the event request service."""

    supabase_url: AnyHttpUrl
    supabase_secret_key: SecretStr
    auth_service_url: AnyHttpUrl = "http://127.0.0.1:8001"


def get_notification_settings() -> NotificationSettings:
    # Constructed only when a client is wired; keep injected repositories usable
    # without unrelated Supabase configuration or a second settings cache.
    return NotificationSettings()


@lru_cache
def get_settings() -> Settings:
    return Settings()
