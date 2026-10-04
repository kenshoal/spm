"""Server-only configuration for venueService.

Storage is chosen explicitly: ``memory`` (the default, used by unit tests and
standalone development) or ``supabase`` (the shared ``public.venues`` table).
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import AnyHttpUrl, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    venue_storage_backend: Literal["memory", "supabase"] = "memory"
    supabase_url: AnyHttpUrl | None = None
    supabase_secret_key: SecretStr | None = None
    # Future notification receiver; unset means no delivery attempts.
    notification_service_url: AnyHttpUrl | None = None
    # Proposed allocation read interface, owned by the booking/event service.
    event_allocations_url: AnyHttpUrl | None = None
    event_allocations_token: SecretStr | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @model_validator(mode="after")
    def _require_supabase_credentials(self) -> Settings:
        if self.venue_storage_backend == "supabase":
            if self.supabase_url is None or self.supabase_secret_key is None:
                raise ValueError(
                    "SUPABASE_URL and SUPABASE_SECRET_KEY are required when "
                    "VENUE_STORAGE_BACKEND=supabase"
                )
            if self.supabase_secret_key.get_secret_value().startswith(
                "sb_publishable_"
            ):
                raise ValueError("SUPABASE_SECRET_KEY must be the server-side secret key")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
