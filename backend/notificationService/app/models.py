from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class NotificationEvent(BaseModel):
    """One domain event another service wants turned into a notification.

    The shape matches what eventRequestService's NotificationClient already
    sends, so existing hooks work unchanged. ``event_id`` is the idempotency
    key: an event repeated for the same recipient is stored only once. Send
    one when you have one (for example the outbox event UUID SCRUM-11
    requires).
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    event_type: str = Field(min_length=1, max_length=100)
    # 64 matches coordinator_id / assigned_by in event_coordinator_assignments.
    recipient_id: str = Field(min_length=1, max_length=64)
    payload: dict[str, Any] = Field(default_factory=dict)
    event_id: str | None = Field(default=None, min_length=1, max_length=64)


class EventAccepted(BaseModel):
    status: str


class NotificationResponse(BaseModel):
    """One inbox entry, as the recipient sees it."""

    id: UUID
    event_type: str
    payload: dict[str, Any]
    read_at: datetime | None
    created_at: datetime
