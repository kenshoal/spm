"""Coordinator-assignment endpoints.

Owns one thing: who is assigned to coordinate an event request, and the
history of who's been assigned. Event creation, drafting, and status all
belong to eventRequestService — this service only reads an event request's
id and status (via EventRequestRef, a read-only mirror) to enforce its own
rule: can't assign before submission, and can't assign once the request has
reached a terminal status.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi import status as http_status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import CurrentUser, Role, get_current_user
from app.models import EventCoordinatorAssignment, EventRequestRef
from app.schemas import CoordinatorAssignmentRead, CoordinatorAssignRequest

router = APIRouter(prefix="/event-requests", tags=["coordinator assignment"])

_DRAFT_STATUS = "Draft"
# eventRequestService's status set isn't fully confirmed beyond Draft/
# Submitted yet — update this once the full lifecycle is settled with them.
_TERMINAL_STATUSES = {"Completed", "Cancelled", "Rejected"}


def _get_event_request_or_404(
    db: Session, event_request_id: uuid.UUID
) -> EventRequestRef:
    event_request = db.get(EventRequestRef, event_request_id)
    if event_request is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="Event request not found",
        )
    return event_request


def _current_assignment(
    db: Session, event_request_id: uuid.UUID
) -> EventCoordinatorAssignment | None:
    stmt = (
        select(EventCoordinatorAssignment)
        .where(EventCoordinatorAssignment.event_request_id == event_request_id)
        .order_by(EventCoordinatorAssignment.id.desc())
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none()


@router.get(
    "/{event_request_id}/coordinator", response_model=CoordinatorAssignmentRead
)
def get_current_coordinator(
    event_request_id: uuid.UUID, db: Session = Depends(get_db)
) -> EventCoordinatorAssignment:
    _get_event_request_or_404(db, event_request_id)
    assignment = _current_assignment(db, event_request_id)
    if assignment is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="No Coordinator has been assigned to this event request",
        )
    return assignment


@router.post(
    "/{event_request_id}/coordinator",
    response_model=CoordinatorAssignmentRead,
    status_code=http_status.HTTP_201_CREATED,
)
def assign_coordinator(
    event_request_id: uuid.UUID,
    body: CoordinatorAssignRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> EventCoordinatorAssignment:
    """Assign (or reassign) the Coordinator for an event request.

    Only an Operations Manager may do this, only once the request has been
    submitted, and not once it's reached a terminal status. Reassignment
    inserts a new row rather than overwriting, so the assignment history is
    preserved.
    """
    if current_user.role is not Role.OPERATIONS_MANAGER:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="Only an Event Operations Manager can assign a Coordinator",
        )

    event_request = _get_event_request_or_404(db, event_request_id)

    if event_request.status == _DRAFT_STATUS:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail="Cannot assign a Coordinator before the request is submitted",
        )
    if event_request.status in _TERMINAL_STATUSES:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail=f"Cannot assign a Coordinator to a {event_request.status} request",
        )

    assignment = EventCoordinatorAssignment(
        event_request_id=event_request.id,
        coordinator_id=body.coordinator_id,
        assigned_by=current_user.id,
    )
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    return assignment
