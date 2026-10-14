"""Equipment reservations (SCRUM-13): reserve and list.

Technical Support reserves units of one catalogue row against a
recorded equipment requirement, so the same units are never committed
to two overlapping holds. Availability is the chosen row's own rule
(app/availability.py row_available); the write goes through the
reserve_equipment RPC, which repeats the checks under the row lock, so
a refusal that only appears under the lock is the database's word.

The caller states the event's dates and venue (the requirement's
snapshot shows them) but never the event itself: the RPC copies
event_request_id from the requirement (D7).
"""

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from postgrest.exceptions import APIError
from pydantic import BaseModel, ConfigDict, Field, model_validator
from supabase import Client

from app.availability import EquipmentRow, Venue, norm, row_available, row_hold
from app.db import get_client
from app.deps import TECHNICAL_SUPPORT_ROLE, User, require_role
from app.reservations import reservation_from_row
from app.rpc_errors import reservation_rpc_error_to_http
from app.venues_client import fetch_venues

router = APIRouter(prefix="/equipment-reservations", tags=["equipment reservations"])

ClientDep = Annotated[Client, Depends(get_client)]
StaffDep = Annotated[User, Depends(require_role(TECHNICAL_SUPPORT_ROLE))]

EQUIPMENT_COLUMNS = "id, type, total_owned_quantity, home_location, operational_status"


class ReservationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")  # the caller cannot set the event or creator

    requirement_id: UUID
    equipment_id: UUID
    quantity: int = Field(gt=0, le=2_147_483_647)
    start_date: date
    end_date: date
    venue_id: str = Field(min_length=1)

    @model_validator(mode="after")
    def _dates_ordered(self):
        if self.end_date < self.start_date:
            raise ValueError("end_date must not be before start_date")
        return self


class ReservationOut(BaseModel):
    id: UUID
    requirement_id: UUID
    event_request_id: UUID
    equipment_id: UUID
    quantity: int
    collection_date: date
    return_date: date
    created_by: UUID
    created_at: str  # round-trips the stored timestamp byte for byte


def _to_row(row: dict) -> EquipmentRow:
    return EquipmentRow(
        id=str(row["id"]),
        type=row["type"],
        total_owned_quantity=int(row["total_owned_quantity"]),
        home_location=row["home_location"],
        operational_status=row["operational_status"],
    )


def _venue(venues, venue_id: str) -> Venue:
    for venue in venues:
        if venue.id == venue_id:
            return venue
    raise HTTPException(status.HTTP_404_NOT_FOUND, "Venue not found")


@router.post("", response_model=ReservationOut, status_code=status.HTTP_201_CREATED)
def reserve_equipment(
    payload: ReservationCreate,
    user: StaffDep,
    client: ClientDep,
    authorization: Annotated[str | None, Header()] = None,
) -> ReservationOut:
    """Reserve units of one catalogue row against one requirement (AC1).

    Check order per D10: role and body come from the framework, then the
    cheap database reads and rule refusals, then the venue lookup, the
    per-row shortfall report, and finally the locked re-check inside
    reserve_equipment.
    """
    try:
        requirement_data = (
            client.table("equipment_requirements")
            .select("id, event_request_id, equipment_type, quantity")
            .eq("id", str(payload.requirement_id))
            .limit(1)
            .execute()
        ).data or []
        if not requirement_data:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, "Equipment requirement not found"
            )
        requirement = requirement_data[0]

        equipment_data = (
            client.table("equipment")
            .select(EQUIPMENT_COLUMNS)
            .eq("id", str(payload.equipment_id))
            .limit(1)
            .execute()
        ).data or []
        if not equipment_data:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Equipment not found")
        row = _to_row(equipment_data[0])

        if norm(row.type) != norm(requirement["equipment_type"]):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "Equipment type does not match the requirement",
            )
        if row.operational_status != "AVAILABLE":
            raise HTTPException(
                status.HTTP_409_CONFLICT, "Equipment not available"
            )

        held_data = (
            client.table("equipment_reservations")
            .select("quantity")
            .eq("requirement_id", str(payload.requirement_id))
            .execute()
        ).data or []
        held = sum(int(r["quantity"]) for r in held_data)
        if held + payload.quantity > int(requirement["quantity"]):
            raise HTTPException(
                status.HTTP_409_CONFLICT, "Exceeds the equipment requirement"
            )

        # Venue lookup happens after the cheap refusals, not in a
        # dependency, so those are reported before venueService is called.
        venues = fetch_venues(authorization or "")
        event_venue = _venue(venues, payload.venue_id)

        hold_start, hold_end = row_hold(
            row=row,
            start_date=payload.start_date,
            end_date=payload.end_date,
            event_venue=event_venue,
            venues=list(venues),
        )
        res_data = (
            client.table("equipment_reservations")
            .select("equipment_id, quantity, collection_date, return_date")
            .eq("equipment_id", str(payload.equipment_id))
            .lte("collection_date", hold_end.isoformat())
            .gte("return_date", hold_start.isoformat())
            .execute()
        ).data or []
        available = row_available(
            row=row,
            reservations=[reservation_from_row(r) for r in res_data],
            start_date=payload.start_date,
            end_date=payload.end_date,
            event_venue=event_venue,
            venues=list(venues),
        )
        if available < payload.quantity:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                {
                    "message": "Insufficient equipment available",
                    "requested": payload.quantity,
                    "available": available,
                    "shortfall": payload.quantity - available,
                },
            )

        try:
            response = client.rpc(
                "reserve_equipment",
                {
                    "p_requirement_id": str(payload.requirement_id),
                    "p_equipment_id": str(payload.equipment_id),
                    "p_quantity": payload.quantity,
                    "p_collection_date": hold_start.isoformat(),
                    "p_return_date": payload.end_date.isoformat(),
                    "p_created_by": user.id,
                },
            ).execute()
        except APIError as error:
            raise reservation_rpc_error_to_http(error) from error
    except APIError as error:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, "Database operation failed"
        ) from error

    data = response.data
    if isinstance(data, list):  # PostgREST may return the row wrapped in a list
        data = data[0]
    return ReservationOut.model_validate(data)


@router.get("/by-event/{event_request_id}", response_model=list[ReservationOut])
def list_event_reservations(
    event_request_id: UUID,
    _user: StaffDep,
    client: ClientDep,
) -> list[ReservationOut]:
    """One event's reservations, oldest first (D9); closes SCRUM-39 AC7."""
    try:
        response = (
            client.table("equipment_reservations")
            .select("*")
            .eq("event_request_id", str(event_request_id))
            .order("created_at")
            .order("id")
            .execute()
        )
    except APIError as error:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, "Database operation failed"
        ) from error
    return [ReservationOut.model_validate(row) for row in response.data]
