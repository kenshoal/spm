# POST /equipment/availability-check (SCRUM-10): how many units of each
# requested type the service could commit to an event, without booking them.
from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from postgrest.exceptions import APIError
from pydantic import BaseModel, Field, model_validator
from supabase import Client

from app.availability import (
    TRANSFER_DAYS,
    EquipmentRow,
    RequestedItem,
    check_availability,
    norm,
)
from app.db import get_client
from app.deps import TECHNICAL_SUPPORT_ROLE, User, require_role
from app.models import OperationalStatus
from app.reservations import reservation_from_row
from app.rpc_errors import rpc_error_to_http
from app.venues_client import fetch_venues

router = APIRouter(prefix="/equipment", tags=["equipment"])

ClientDep = Annotated[Client, Depends(get_client)]
StaffDep = Annotated[User, Depends(require_role(TECHNICAL_SUPPORT_ROLE))]


class RequestedItemIn(BaseModel):
    type: str
    quantity: int = Field(gt=0)


class AvailabilityCheckIn(BaseModel):
    start_date: date
    end_date: date
    venue_id: str
    items: list[RequestedItemIn] = Field(min_length=1)

    @model_validator(mode="after")
    def check_rules(self):
        if self.end_date < self.start_date:
            raise ValueError("end_date must not be before start_date")
        keys = [norm(i.type) for i in self.items]
        if len(keys) != len(set(keys)):
            raise ValueError("each equipment type may be listed once")
        return self


class AvailabilityOut(BaseModel):
    requested: int
    available: int
    shortfall: int


def to_row(row: dict) -> EquipmentRow:
    return EquipmentRow(
        id=str(row["id"]),
        type=row["type"],
        total_owned_quantity=int(row["total_owned_quantity"]),
        home_location=row["home_location"],
        operational_status=row["operational_status"],
    )


@router.post(
    "/availability-check", response_model=dict[str, AvailabilityOut]
)
def check_equipment_availability(
    payload: AvailabilityCheckIn,
    _user: StaffDep,
    client: ClientDep,
    authorization: Annotated[str, Header()],
) -> dict[str, dict[str, int]]:
    # Venue lookup happens here, not in a dependency, so a 422 from the
    # request model is reported before venueService is called.
    venues = fetch_venues(authorization)
    event_venue = next((v for v in venues if v.id == payload.venue_id), None)
    if event_venue is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Venue not found"
        )

    wanted = {norm(i.type) for i in payload.items}
    try:
        rows_data = (
            client.table("equipment")
            .select(
                "id, type, total_owned_quantity, home_location, operational_status"
            )
            .eq("operational_status", OperationalStatus.AVAILABLE.value)
            .execute()
        ).data or []
        rows = [
            to_row(r)
            for r in rows_data
            if r["operational_status"] == "AVAILABLE"
            and norm(r["type"]) in wanted
        ]
        reservations = []
        if rows:
            # Widest possible hold: D-1 plus the transfer buffer, so one
            # query covers every row whatever building it is based in.
            widest_start = payload.start_date - timedelta(days=1 + TRANSFER_DAYS)
            res_data = (
                client.table("equipment_reservations")
                .select("equipment_id, quantity, collection_date, return_date")
                .in_("equipment_id", [r.id for r in rows])
                .lte("collection_date", payload.end_date.isoformat())
                .gte("return_date", widest_start.isoformat())
                .execute()
            ).data or []
            reservations = [reservation_from_row(r) for r in res_data]
    except APIError as exc:
        raise rpc_error_to_http(exc) from exc

    return check_availability(
        rows=rows,
        reservations=reservations,
        start_date=payload.start_date,
        end_date=payload.end_date,
        event_venue=event_venue,
        venues=list(venues),
        items=[RequestedItem(type=i.type, quantity=i.quantity) for i in payload.items],
    )
