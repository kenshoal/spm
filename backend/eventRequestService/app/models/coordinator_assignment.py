from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.event_request import EventRequestResponse


class CoordinatorAssignRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    coordinator_id: str = Field(min_length=1, max_length=64)


class CoordinatorAssignmentResponse(BaseModel):
    id: int
    event_request_id: str
    coordinator_id: str
    assigned_by: str
    assigned_at: datetime


class CurrentAssignmentResponse(BaseModel):
    event_request: EventRequestResponse
    assignment: CoordinatorAssignmentResponse
