from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from supabase import Client

from app.db import get_client
from app.deps import User, get_current_user

router = APIRouter(prefix="/equipment", tags=["equipment"])

ClientDep = Annotated[Client, Depends(get_client)]
UserDep = Annotated[User, Depends(get_current_user)]


class OperationalStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    DAMAGED = "DAMAGED"
    UNDER_REPAIR = "UNDER_REPAIR"
    UNDER_MAINTENANCE = "UNDER_MAINTENANCE"
    RETIRED = "RETIRED"


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
    user: UserDep,
    client: ClientDep,
) -> EquipmentOut:
    response = (
        client.table("equipment")
        .insert(
            {
                "type": payload.type,
                "description": payload.description,
                "total_owned_quantity": payload.total_owned_quantity,
                "home_location": payload.home_location,
                "operational_status": payload.operational_status.value,
                "created_by": user.id,
            }
        )
        .select("*")
        .execute()
    )
    equipment = response.data[0]
    client.table("equipment_status_history").insert(
        {
            "equipment_id": equipment["id"],
            "old_status": None,
            "new_status": equipment["operational_status"],
            "changed_by": user.id,
        }
    ).execute()
    return EquipmentOut.model_validate(equipment)


@router.patch("/{equipment_id}/quantity", response_model=EquipmentOut)
def update_quantity(
    equipment_id: UUID,
    payload: QuantityUpdate,
    _user: UserDep,
    client: ClientDep,
) -> EquipmentOut:
    response = (
        client.table("equipment")
        .update(
            {
                "total_owned_quantity": payload.total_owned_quantity,
                "updated_at": datetime.now(UTC).isoformat(),
            }
        )
        .eq("id", str(equipment_id))
        .select()
        .execute()
    )
    if not response.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Equipment not found"
        )
    return EquipmentOut.model_validate(response.data[0])
