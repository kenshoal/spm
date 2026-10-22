from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class SkillTag(str, Enum):
    """The fixed vocabulary a technical-support requirement can ask for."""

    AUDIO_VISUAL = "audio_visual"
    LIGHTING = "lighting"
    IT_NETWORK = "it_network"
    LIVESTREAM = "livestream"


class RequirementCreate(BaseModel):
    """What the Coordinator records: free text plus one skill tag."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    description: str = Field(min_length=1, max_length=2_000)
    skill_tag: SkillTag


class AssignmentCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    staff_id: str = Field(min_length=1, max_length=64)


class RequirementResponse(BaseModel):
    id: str
    event_request_id: str
    description: str
    skill_tag: SkillTag
    recorded_by: str
    recorded_at: datetime


class AssignmentResponse(BaseModel):
    id: str
    requirement_id: str
    event_request_id: str
    staff_id: str
    assigned_by: str
    assigned_at: datetime


class CandidateResponse(BaseModel):
    """A suitable staff member and whether they are already on the requirement."""

    staff_id: str
    already_assigned: bool


class AssignedStaffResponse(BaseModel):
    """Who is assigned, by whom and when — what the event page shows (AC4)."""

    staff_id: str
    assigned_by: str
    assigned_at: datetime


class EventTechnicalSupportResponse(RequirementResponse):
    """One requirement with everyone assigned to it, in stable order."""

    assigned_staff: list[AssignedStaffResponse]
