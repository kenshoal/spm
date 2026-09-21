"""Explicit storage selection; credentials are loaded only on the server."""

from functools import lru_cache
from typing import Literal
from uuid import UUID

from fastapi import HTTPException
from pydantic import AnyHttpUrl, SecretStr, ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    venue_storage_backend: Literal["memory", "supabase"] = "memory"
    supabase_url: AnyHttpUrl | None = None
    supabase_secret_key: SecretStr | None = None
    venue_environment: Literal["development", "production"] = "development"
    venue_allow_stub_auth: bool = False
    venue_dev_staff_user_id: UUID | None = None
    # Future notification receiver; unset means no delivery attempts.
    notification_service_url: AnyHttpUrl | None = None
    # Proposed allocation read interface, owned by the booking/event service.
    event_allocations_url: AnyHttpUrl | None = None
    event_allocations_token: SecretStr | None = None

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @model_validator(mode="after")
    def validate_storage(self) -> "Settings":
        if self.venue_storage_backend == "supabase":
            if not self.supabase_url or not self.supabase_secret_key:
                raise ValueError("Supabase URL and secret key are required")
            key = self.supabase_secret_key.get_secret_value()
            if not key or key.startswith("sb_publishable_"):
                raise ValueError("A server-side secret key is required")
        if self.venue_environment == "production":
            # Authentication is deliberately deferred, so do not permit a
            # production server backed by a privileged database key yet.
            raise ValueError("Production use requires real authentication integration")
        return self


@lru_cache
def get_settings() -> Settings:
    try:
        return Settings()
    except ValidationError:
        # Pydantic errors may include configuration input; never echo secrets.
        raise HTTPException(503, "Venue service configuration is invalid") from None
