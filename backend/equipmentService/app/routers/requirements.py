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
from app.deps import (
    EVENT_COORDINATOR_ROLE,
    SAFETY_OFFICER_ROLE,
    TECHNICAL_SUPPORT_ROLE,
    User,
    require_role,
)
from app.event_requests_client import EventRequestClient, get_event_request_client
from app.rpc_errors import requirement_rpc_error_to_http

router = APIRouter(prefix="/equipment-requirements", tags=["equipment requirements"])

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


class ArrangementUpdate(BaseModel):
    """One arrangement change by Technical Support (D3/D4): the caller
    states the status it saw, so a stale update is refused by the
    database function under the row lock."""

    model_config = ConfigDict(extra="forbid")

    expected_status: RequirementStatus
    status: RequirementStatus
    support_note: str | None = Field(default=None, max_length=2000)


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


def _list_rows(client: Client, column: str, value: str) -> list[RequirementOut]:
    """One lookup's rows, oldest first (recorded_at, then id, per AC3/AC4)."""
    response = (
        client.table("equipment_requirements")
        .select("*")
        .eq(column, value)
        .order("recorded_at")
        .order("id")
        .execute()
    )
    return [RequirementOut.model_validate(row) for row in response.data]


def _is_support(user: User) -> bool:
    """Technical Support is role-wide (D6) and never asks eventRequestService."""
    return TECHNICAL_SUPPORT_ROLE in user.roles


@router.get("", response_model=list[RequirementOut])
def review_queue(
    user: StaffDep,
    client: ClientDep,
    status: RequirementStatus = "requested",
) -> list[RequirementOut]:
    """Technical Support's review queue across every event (AC4)."""
    return _list_rows(client, "status", status)


# SCRUM-60 AC2: the Safety Officer reads one event's requirements for its
# safety check, role-wide like Technical Support. Read-only.
EventReaderDep = Annotated[
    User,
    Depends(require_role(EVENT_COORDINATOR_ROLE, TECHNICAL_SUPPORT_ROLE, SAFETY_OFFICER_ROLE)),
]


@router.get("/by-event/{event_request_id}", response_model=list[RequirementOut])
def list_for_event(
    event_request_id: UUID,
    user: EventReaderDep,
    client: ClientDep,
    events: EventDep,
    authorization: Annotated[str | None, Header()] = None,
) -> list[RequirementOut]:
    """One event's requirements; Coordinators must currently be assigned."""
    if not _is_support(user) and SAFETY_OFFICER_ROLE not in user.roles:
        events.assert_assigned(str(event_request_id), _token(authorization), user.id)
    return _list_rows(client, "event_request_id", str(event_request_id))


@router.get("/{requirement_id}", response_model=RequirementOut)
def get_requirement(
    requirement_id: UUID,
    user: ViewerDep,
    client: ClientDep,
    events: EventDep,
    authorization: Annotated[str | None, Header()] = None,
) -> RequirementOut:
    """One requirement; Coordinators must currently be assigned (D7)."""
    response = (
        client.table("equipment_requirements")
        .select("*")
        .eq("id", str(requirement_id))
        .limit(1)
        .execute()
    )
    if not response.data:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Equipment requirement not found"
        )
    row = response.data[0]
    if not _is_support(user):
        try:
            events.assert_assigned(
                str(row["event_request_id"]), _token(authorization), user.id
            )
        except HTTPException as error:
            # The requirement exists but not for this caller: it must be
            # indistinguishable from a missing requirement (AC6-X19).
            if error.status_code == status.HTTP_404_NOT_FOUND:
                raise HTTPException(
                    status.HTTP_404_NOT_FOUND, "Equipment requirement not found"
                ) from error
            raise
    return RequirementOut.model_validate(row)


@router.patch("/{requirement_id}/arrangement", response_model=RequirementOut)
def update_arrangement(
    requirement_id: UUID,
    payload: ArrangementUpdate,
    user: StaffDep,
    client: ClientDep,
) -> RequirementOut:
    """Technical Support moves one requirement's arrangement along (AC5).

    The transition table lives in transition_equipment_requirement, so the
    allowed moves, the stale check and the note-only rule are one source of
    truth applied under the row lock; this endpoint owns the contract and
    error mapping.
    """
    try:
        response = client.rpc(
            "transition_equipment_requirement",
            {
                "p_requirement_id": str(requirement_id),
                "p_expected_status": payload.expected_status,
                "p_new_status": payload.status,
                "p_support_note": payload.support_note,
                "p_updated_by": user.id,
            },
        ).execute()
    except APIError as error:
        raise requirement_rpc_error_to_http(error) from error
    return RequirementOut.model_validate(response.data)
