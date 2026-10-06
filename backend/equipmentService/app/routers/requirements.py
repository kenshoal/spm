"""Equipment requirements (SCRUM-33): record, read and arrange.

An assigned Event Coordinator records what equipment an event needs;
Technical Support reviews the queue and moves each requirement's
arrangement along. Relationship access goes through eventRequestService
with the caller's own token (see app/event_requests_client.py);
Technical Support is role-wide and never asks eventRequestService (D6).
"""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from postgrest.exceptions import APIError
from pydantic import BaseModel, ConfigDict, Field, field_validator
from supabase import Client

from app.availability import norm
from app.db import get_client
from app.deps import TECHNICAL_SUPPORT_ROLE, User, require_role
from app.event_requests_client import EventRequestClient, get_event_request_client

router = APIRouter(prefix="/equipment-requirements", tags=["equipment requirements"])

# SCRUM-39 (feat/scoped-resource-access) adds this constant to app/deps.py;
# keep the local definition until that branch merges, then use the shared one.
EVENT_COORDINATOR_ROLE = "event_coordinator"

# Event statuses that refuse new requirements (AC7). Everything else is open.
CLOSED_EVENT_STATUSES = frozenset({"Cancelled", "Completed", "Rejected"})

RequirementStatus = Literal["requested", "in_progress", "arranged"]

ClientDep = Annotated[Client, Depends(get_client)]
EventDep = Annotated[EventRequestClient, Depends(get_event_request_client)]
CoordinatorDep = Annotated[User, Depends(require_role(EVENT_COORDINATOR_ROLE))]
StaffDep = Annotated[User, Depends(require_role(TECHNICAL_SUPPORT_ROLE))]
ViewerDep = Annotated[
    User, Depends(require_role(EVENT_COORDINATOR_ROLE, TECHNICAL_SUPPORT_ROLE))
]


class RequirementOut(BaseModel):
    id: UUID
    event_request_id: UUID
    equipment_type: str
    quantity: int
    technical_requirements: str | None
    status: str
    support_note: str | None
    event_name: str | None
    event_date_times: list[str]
    recorded_by: UUID
    recorded_at: str
    updated_by: UUID | None
    updated_at: str | None


class RequirementCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_request_id: UUID
    equipment_type: str
    quantity: int = Field(ge=1, le=2_147_483_647)
    technical_requirements: str | None = Field(default=None, max_length=2000)

    @field_validator("equipment_type")
    @classmethod
    def _type_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("equipment type must not be blank")
        return value

    @field_validator("technical_requirements")
    @classmethod
    def _blank_is_none(cls, value: str | None) -> str | None:
        return value if value is not None and value.strip() else None


def _token(authorization: str | None) -> str:
    """The bearer token get_current_user already validated."""
    return (authorization or "").removeprefix("Bearer ").strip()


def _match_catalogue_type(client: Client, requested: str) -> str:
    """The catalogue's spelling for ``requested``, ignoring case and spaces.

    A type whose only rows are RETIRED counts as unknown (D1); damaged or
    under-repair types are accepted, availability is SCRUM-13's concern (D2).
    """
    rows = (
        client.table("equipment")
        .select("type")
        .neq("operational_status", "RETIRED")
        .execute()
        .data
    )
    for row in rows:
        if norm(row["type"]) == norm(requested):
            return row["type"]
    raise HTTPException(
        status.HTTP_422_UNPROCESSABLE_CONTENT, "Unknown equipment type"
    )


@router.post("", response_model=RequirementOut, status_code=status.HTTP_201_CREATED)
def record_requirement(
    payload: RequirementCreate,
    user: CoordinatorDep,
    client: ClientDep,
    events: EventDep,
    authorization: Annotated[str | None, Header()] = None,
) -> RequirementOut:
    """Record one requirement for an event the caller currently coordinates.

    Check order per D8: role (403) and body (422) come from the framework,
    then assignment (404), event status (409), catalogue type (422), insert.
    """
    snapshot = events.snapshot_for_coordinator(
        str(payload.event_request_id), _token(authorization), user.id
    )
    if snapshot.status in CLOSED_EVENT_STATUSES:
        raise HTTPException(status.HTTP_409_CONFLICT, "Event is closed")
    equipment_type = _match_catalogue_type(client, payload.equipment_type)
    try:
        response = (
            client.table("equipment_requirements")
            .insert(
                {
                    "event_request_id": str(payload.event_request_id),
                    "equipment_type": equipment_type,
                    "quantity": payload.quantity,
                    "technical_requirements": payload.technical_requirements,
                    "event_name": snapshot.event_name,
                    "event_date_times": snapshot.proposed_date_times,
                    "recorded_by": user.id,
                }
            )
            .execute()
        )
    except APIError as error:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, "Database operation failed"
        ) from error
    return RequirementOut.model_validate(response.data[0])
