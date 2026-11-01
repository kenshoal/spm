from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, Field, StringConstraints, model_validator


class PublicEventVenue(BaseModel):
    """Where and when: a confirmed booking as attendees may see it (hotfix 5)."""

    name: str
    location: str
    start_date: date
    end_date: date
    start_minute: int
    end_minute: int


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
    venues: list[PublicEventVenue] = []


class EventRegistrationRow(BaseModel):
    """One registration as its organiser or coordinator sees it (hotfix 16: with the
    attendee's email, so staff can look a person up, Q&A #32)."""

    id: str
    attendee_id: str
    attendee_email: str | None = None
    status: str
    created_at: datetime
    registered_by: str | None = None  # SCRUM-41: the coordinator, null if self-registered
    attended_at: datetime | None = None  # SCRUM-25: null until checked in
    checked_in_by: str | None = None


class RegistrationInfoResponse(BaseModel):
    """SCRUM-34 AC3: every registration on the event plus the aggregate counts."""

    event_request_id: str
    registration_capacity: int | None
    # Hotfix 23: the seats of the booked venues; a VIP may be added up to this (Q&A #99).
    venue_capacity: int | None = None
    registration_opens_at: AwareDatetime | None = None
    registration_closes_at: AwareDatetime | None = None
    registered: int
    withdrawn: int
    places_available: int | None
    attended: int  # SCRUM-25: Registered and checked in
    absent: int  # SCRUM-25: Registered, not checked in
    registrations: list[EventRegistrationRow]


class RegistrationSettingsUpdate(BaseModel):
    """Hotfix 4 (Q&A #30, #42, #127): the Coordinator sets the period and capacity."""

    registration_opens_at: AwareDatetime
    registration_closes_at: AwareDatetime
    registration_capacity: int = Field(gt=0, le=2_147_483_647)

    @model_validator(mode="after")
    def closes_after_it_opens(self) -> "RegistrationSettingsUpdate":
        if self.registration_closes_at <= self.registration_opens_at:
            raise ValueError("registration must close after it opens")
        return self


class RegistrationSettingsResponse(BaseModel):
    id: str
    registration_opens_at: AwareDatetime
    registration_closes_at: AwareDatetime
    registration_capacity: int


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
    status: Literal["Registered", "Withdrawn"]
    created_at: datetime
    withdrawn_at: datetime | None = None
    event: PublicEventResponse
