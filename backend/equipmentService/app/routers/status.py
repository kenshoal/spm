from datetime import date, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from postgrest.exceptions import APIError
from pydantic import BaseModel, Field
from supabase import Client

from app.availability import committed_peak
from app.clock import get_today
from app.db import get_client
from app.deps import EVENT_COORDINATOR_ROLE, TECHNICAL_SUPPORT_ROLE, User, require_role
from app.models import OperationalStatus
from app.reservations import reservation_from_row
from app.rpc_errors import rpc_error_to_http

router = APIRouter(prefix="/equipment", tags=["equipment"])

ClientDep = Annotated[Client, Depends(get_client)]
ViewerDep = Annotated[
    User, Depends(require_role(EVENT_COORDINATOR_ROLE, TECHNICAL_SUPPORT_ROLE))
]
StaffDep = Annotated[User, Depends(require_role(TECHNICAL_SUPPORT_ROLE))]
TodayDep = Annotated[date, Depends(get_today)]


class StatusOut(BaseModel):
    equipment_id: UUID
    operational_status: OperationalStatus
    available: bool
    available_quantity: int


class StatusTransitionIn(BaseModel):
    new_status: OperationalStatus
    reason: str | None = Field(default=None, max_length=255)


class StatusTransitionOut(BaseModel):
    equipment_id: UUID
    new_status: OperationalStatus
    changed_by: str
    reason: str | None


class HistoryOut(BaseModel):
    id: int
    equipment_id: UUID
    old_status: OperationalStatus | None
    new_status: OperationalStatus
    reason: str | None
    changed_by: str
    changed_at: datetime


@router.get("/{equipment_id}/status", response_model=StatusOut)
def get_status(
    equipment_id: UUID,
    client: ClientDep,
    _user: ViewerDep,
    today: TodayDep,
) -> StatusOut:
    response = (
        client.table("equipment")
        .select("id, operational_status, total_owned_quantity")
        .eq("id", str(equipment_id))
        .limit(1)
        .execute()
    )
    if not response.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Equipment not found"
        )
    row = response.data[0]
    # `available` means working (status AVAILABLE); `available_quantity` is
    # what is left after the units reserved today (SCRUM-10). Stored
    # reservation windows already include the D-1 and transfer days, so a
    # reservation covers today when collection_date <= today <= return_date.
    serviceable = row["operational_status"] == OperationalStatus.AVAILABLE
    available_quantity = 0
    if serviceable:
        reserved = (
            client.table("equipment_reservations")
            .select("equipment_id, quantity, collection_date, return_date")
            .eq("equipment_id", str(row["id"]))
            .lte("collection_date", today.isoformat())
            .gte("return_date", today.isoformat())
            .execute()
        ).data or []
        reservations = [reservation_from_row(r) for r in reserved]
        peak = committed_peak(str(row["id"]), reservations, today, today)
        available_quantity = max(0, row["total_owned_quantity"] - peak)
    return StatusOut(
        equipment_id=row["id"],
        operational_status=row["operational_status"],
        available=serviceable,
        available_quantity=available_quantity,
    )


@router.patch("/{equipment_id}/status", response_model=StatusTransitionOut)
def transition_status(
    equipment_id: UUID,
    payload: StatusTransitionIn,
    user: StaffDep,
    client: ClientDep,
) -> StatusTransitionOut:
    try:
        client.rpc(
            "transition_equipment_status",
            {
                "p_equipment_id": str(equipment_id),
                "p_new_status": payload.new_status.value,
                "p_changed_by": user.id,
                "p_reason": payload.reason,
            },
        ).execute()
    except APIError as exc:
        raise rpc_error_to_http(exc) from exc
    return StatusTransitionOut(
        equipment_id=equipment_id,
        new_status=payload.new_status,
        changed_by=user.id,
        reason=payload.reason,
    )


@router.get(
    "/{equipment_id}/status/history",
    response_model=list[HistoryOut],
)
def get_status_history(
    equipment_id: UUID,
    client: ClientDep,
    _user: ViewerDep,
) -> list[HistoryOut]:
    exists = (
        client.table("equipment")
        .select("id")
        .eq("id", str(equipment_id))
        .limit(1)
        .execute()
    )
    if not exists.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Equipment not found"
        )
    response = (
        client.table("equipment_status_history")
        .select("*")
        .eq("equipment_id", str(equipment_id))
        .order("changed_at", desc=True)
        .execute()
    )
    return [HistoryOut.model_validate(row) for row in response.data]
