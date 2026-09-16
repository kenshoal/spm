"""Pydantic request/response shapes for the coordinator-assignment API."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CoordinatorAssignRequest(BaseModel):
    coordinator_id: str


class CoordinatorAssignmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_request_id: uuid.UUID
    coordinator_id: str
    assigned_by: str
    assigned_at: datetime
