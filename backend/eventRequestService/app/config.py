from functools import lru_cache

from pydantic import AnyHttpUrl, Field, SecretStr
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


class PeriodicTaskSettings(BaseSettings):
    """Timer configuration is independent of optional notification delivery."""

    auto_completion_enabled: bool = False
    # SCRUM-38 AC3: opening/closing notices, switched on separately from completion.
    registration_window_notices_enabled: bool = False
    # SCRUM-24: the waiting-list timer and its outbox relay, on their own switch.
    waitlist_timers_enabled: bool = False
    # How far back a missed boundary is still announced; older ones are dropped.
    registration_window_lookback_hours: float = Field(
        default=72, gt=0, allow_inf_nan=False
    )
    periodic_task_interval_seconds: float = Field(default=60, gt=0, allow_inf_nan=False)

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore",
    )


def get_periodic_task_settings() -> PeriodicTaskSettings:
    return PeriodicTaskSettings()


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
