from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from postgrest.exceptions import APIError
from pydantic import BaseModel, Field
from supabase import Client

from app.db import get_client
from app.deps import TECHNICAL_SUPPORT_ROLE, User, get_current_user, require_role
from app.models import OperationalStatus
from app.rpc_errors import rpc_error_to_http

router = APIRouter(prefix="/equipment", tags=["equipment"])

ClientDep = Annotated[Client, Depends(get_client)]
ViewerDep = Annotated[User, Depends(get_current_user)]
StaffDep = Annotated[User, Depends(require_role(TECHNICAL_SUPPORT_ROLE))]


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
    # Pre-reservations semantics (SCRUM-10 will subtract committed units):
    # status is row-level, so a non-AVAILABLE row has zero serviceable units.
    serviceable = row["operational_status"] == OperationalStatus.AVAILABLE
    return StatusOut(
        equipment_id=row["id"],
        operational_status=row["operational_status"],
        available=serviceable,
        available_quantity=row["total_owned_quantity"] if serviceable else 0,
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
