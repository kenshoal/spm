from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel


class ArrangementReviewResponse(BaseModel):
    """Recorded arrangement review evidence, separate from lifecycle status."""

    id: UUID
    event_request_id: UUID
    arrangement: Literal["venue_booking", "equipment_reservation"]
    arrangement_id: UUID
    trigger_id: UUID
    trigger_type: Literal[
        "event_change", "equipment_unavailable", "safety_recheck", "venue_timing_change"
    ]
    changed_fields: list[str]
    reason: str
    raised_at: AwareDatetime
    cleared_at: AwareDatetime | None
    cleared_by: UUID | None
