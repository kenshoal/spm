from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from postgrest.exceptions import APIError
from pydantic import BaseModel, Field
from supabase import Client

from app.db import get_client
from app.deps import EVENT_COORDINATOR_ROLE, TECHNICAL_SUPPORT_ROLE, User, require_role
from app.models import OperationalStatus
from app.rpc_errors import rpc_error_to_http

router = APIRouter(prefix="/equipment", tags=["equipment"])

ClientDep = Annotated[Client, Depends(get_client)]
ViewerDep = Annotated[
    User, Depends(require_role(EVENT_COORDINATOR_ROLE, TECHNICAL_SUPPORT_ROLE))
]
StaffDep = Annotated[User, Depends(require_role(TECHNICAL_SUPPORT_ROLE))]


class EquipmentOut(BaseModel):
    id: UUID
    type: str
    description: str | None
    total_owned_quantity: int
    home_location: str
    operational_status: OperationalStatus
    created_by: UUID | None
    created_at: datetime
    updated_at: datetime


class EquipmentCreate(BaseModel):
    type: str = Field(max_length=120)
    description: str | None = None
    total_owned_quantity: int = Field(ge=0)
    home_location: str = Field(max_length=120)
    operational_status: OperationalStatus = OperationalStatus.AVAILABLE


class QuantityUpdate(BaseModel):
    total_owned_quantity: int = Field(ge=0)


@router.get("", response_model=list[EquipmentOut])
def list_equipment(
    client: ClientDep,
    _user: ViewerDep,
    type: str | None = None,
    operational_status: OperationalStatus | None = None,
) -> list[EquipmentOut]:
    query = client.table("equipment").select("*")
    if type is not None:
        query = query.eq("type", type)
    if operational_status is not None:
        query = query.eq("operational_status", operational_status.value)
    response = query.execute()
    return [EquipmentOut.model_validate(row) for row in response.data]


@router.get("/{equipment_id}", response_model=EquipmentOut)
def get_equipment(
    equipment_id: UUID,
    client: ClientDep,
    _user: ViewerDep,
) -> EquipmentOut:
    response = (
        client.table("equipment")
        .select("*")
        .eq("id", str(equipment_id))
        .limit(1)
        .execute()
    )
    if not response.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Equipment not found"
        )
    return EquipmentOut.model_validate(response.data[0])


@router.post("", response_model=EquipmentOut, status_code=status.HTTP_201_CREATED)
def create_equipment(
    payload: EquipmentCreate,
    user: StaffDep,
    client: ClientDep,
) -> EquipmentOut:
    try:
        response = client.rpc(
            "create_equipment",
            {
                "p_type": payload.type,
                "p_description": payload.description,
                "p_total_owned_quantity": payload.total_owned_quantity,
                "p_home_location": payload.home_location,
                "p_operational_status": payload.operational_status.value,
                "p_created_by": user.id,
            },
        ).execute()
    except APIError as exc:
        raise rpc_error_to_http(exc) from exc
    return EquipmentOut.model_validate(response.data)


@router.patch("/{equipment_id}/quantity", response_model=EquipmentOut)
def update_quantity(
    equipment_id: UUID,
    payload: QuantityUpdate,
    user: StaffDep,
    client: ClientDep,
) -> EquipmentOut:
    try:
        response = client.rpc(
            "update_equipment_quantity",
            {
                "p_equipment_id": str(equipment_id),
                "p_new_quantity": payload.total_owned_quantity,
                "p_changed_by": user.id,
            },
        ).execute()
    except APIError as exc:
        raise rpc_error_to_http(exc) from exc
    return EquipmentOut.model_validate(response.data)
