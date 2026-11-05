from functools import lru_cache

from pydantic import AnyHttpUrl, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Server-only configuration for the notification service."""

    supabase_url: AnyHttpUrl
    supabase_secret_key: SecretStr
    auth_service_url: AnyHttpUrl = "http://127.0.0.1:8001"

    # Email (SCRUM-57). With no smtp_host, email is switched off: the service
    # still starts and stores notifications, and an email attempt is logged.
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: SecretStr | None = None
    smtp_starttls: bool = True
    mail_from: str = "SPM Notifications <no-reply@localhost>"
    # Where the emailed link points; the frontend's notifications page.
    inbox_url: str = "http://localhost:3000/notifications"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
