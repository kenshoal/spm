"""Retained registration-review evidence, separate from attendee registration."""

from uuid import UUID

from pydantic import AwareDatetime, BaseModel


class RegistrationReviewResponse(BaseModel):
    id: UUID
    event_request_id: UUID
    event_updated_at: AwareDatetime
    changed_fields: list[str]
    reason: str
    raised_at: AwareDatetime
    cleared_at: AwareDatetime | None
    cleared_by: str | None
