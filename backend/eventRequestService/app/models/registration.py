from datetime import datetime
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, StringConstraints


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
    registered_by: str | None = None  # SCRUM-41: the coordinator, null if self-registered
    attended_at: datetime | None = None  # SCRUM-25: null until checked in
    checked_in_by: str | None = None


class RegistrationInfoResponse(BaseModel):
    """SCRUM-34 AC3: every registration on the event plus the aggregate counts."""

    event_request_id: str
    registration_capacity: int | None
    registered: int
    withdrawn: int
    places_available: int | None
    attended: int  # SCRUM-25: Registered and checked in
    absent: int  # SCRUM-25: Registered, not checked in
    registrations: list[EventRegistrationRow]


class ManualRegistrationCreate(BaseModel):
    """SCRUM-41: the email of an existing attendee account."""

    attendee_email: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=320)
    ]


class ManualRegistrationResponse(BaseModel):
    id: str
    event_request_id: str
    attendee_id: str
    status: Literal["Registered"]
    created_at: datetime
    registered_by: str


class CheckInResponse(BaseModel):
    id: str
    event_request_id: str
    attendee_id: str
    status: Literal["Registered"]
    attended_at: datetime
    checked_in_by: str


class RegistrationResponse(BaseModel):
    id: str
    event_request_id: str
    attendee_id: str
    status: Literal["Registered"]
    created_at: datetime
    event: PublicEventResponse
