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


class RegistrationResponse(BaseModel):
    id: str
    event_request_id: str
    attendee_id: str
    status: Literal["Registered"]
    created_at: datetime
    event: PublicEventResponse
