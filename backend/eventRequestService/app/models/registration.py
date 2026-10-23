from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel


class PublicEventResponse(BaseModel):
    """What an attendee may see of an event (SCRUM-21 D4). Nothing internal."""

    id: str
    event_name: str | None
    purpose: str | None
    description: str | None
    proposed_date_times: list[AwareDatetime]
    registration_opens_at: AwareDatetime | None
    registration_closes_at: AwareDatetime | None
    registration_capacity: int | None
    places_remaining: int | None


class EventRegistrationRow(BaseModel):
    """One registration as its organiser or coordinator sees it: no contact data."""

    id: str
    attendee_id: str
    status: str
    created_at: datetime


class RegistrationInfoResponse(BaseModel):
    """SCRUM-34 AC3: every registration on the event plus the aggregate counts."""

    event_request_id: str
    registration_capacity: int | None
    registered: int
    withdrawn: int
    places_available: int | None
    registrations: list[EventRegistrationRow]


class RegistrationResponse(BaseModel):
    id: str
    event_request_id: str
    attendee_id: str
    status: Literal["Registered"]
    created_at: datetime
    event: PublicEventResponse
