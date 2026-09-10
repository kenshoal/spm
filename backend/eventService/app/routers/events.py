"""Event endpoints.

`transition_status` is where the allowed-transition and role-gated rules
from app.status come together: legality of the move comes from
`can_transition`, and the two role checks (cancel, complete) implement the
acceptance criteria that aren't just "is this transition on the graph".
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi import status as http_status
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import CurrentUser, Role, get_current_user
from app.models import Event, StatusHistory
from app.schemas import EventCreate, EventRead, StatusTransitionRequest
from app.status import EventStatus, can_transition

router = APIRouter(prefix="/events", tags=["events"])


def _get_event_or_404(db: Session, event_id: str) -> Event:
    event = db.get(Event, event_id)
    if event is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND, detail="Event not found"
        )
    return event


@router.post("", response_model=EventRead, status_code=http_status.HTTP_201_CREATED)
def create_event(
    body: EventCreate,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Event:
    event = Event(title=body.title, organiser_id=current_user.id)
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


@router.get("/{event_id}", response_model=EventRead)
def read_event(event_id: str, db: Session = Depends(get_db)) -> Event:
    return _get_event_or_404(db, event_id)


@router.post("/{event_id}/status", response_model=EventRead)
def transition_status(
    event_id: str,
    body: StatusTransitionRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Event:
    event = _get_event_or_404(db, event_id)
    target = body.target_status

    if not can_transition(event.status, target):
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail=f"Cannot transition from {event.status} to {target}",
        )

    if target is EventStatus.CANCELLED and event.coordinator_id is not None:
        is_assigned_coordinator = (
            current_user.role is Role.EVENT_COORDINATOR
            and current_user.id == event.coordinator_id
        )
        if not is_assigned_coordinator:
            raise HTTPException(
                status_code=http_status.HTTP_403_FORBIDDEN,
                detail="Only the assigned Event Coordinator can cancel this event",
            )

    if target is EventStatus.COMPLETED and current_user.role is not Role.EVENT_COORDINATOR:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="Only an Event Coordinator can mark an event complete",
        )

    previous_status = event.status
    event.status = target
    db.add(
        StatusHistory(
            event_id=event.id,
            from_status=previous_status,
            to_status=target,
            changed_by=current_user.id,
        )
    )
    db.commit()
    db.refresh(event)
    return event


@router.delete("/{event_id}", status_code=http_status.HTTP_204_NO_CONTENT)
def discard_event(
    event_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    event = _get_event_or_404(db, event_id)

    if event.status is not EventStatus.DRAFT:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail="Only a Draft event can be discarded",
        )
    if current_user.id != event.organiser_id:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="Only the Organiser can discard this Draft",
        )

    db.delete(event)
    db.commit()
