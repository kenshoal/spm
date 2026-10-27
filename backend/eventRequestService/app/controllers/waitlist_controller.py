from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from pydantic import ValidationError

from app.clock import get_now
from app.config import get_settings
from app.controllers.registration_controller import AttendeeDependency
from app.repositories.waitlist_repository import SupabaseWaitlistRepository
from app.services.waitlist_service import WaitlistService

router = APIRouter(prefix="/attendee", tags=["attendee waiting list"])


def get_waitlist_service(request: Request) -> WaitlistService:
    """Return the service owned by this FastAPI application instance."""
    service = request.app.state.waitlist_service
    if service is not None:
        return service

    try:
        repository = SupabaseWaitlistRepository.from_settings(get_settings())
    except ValidationError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Supabase is not configured for eventRequestService",
        ) from error

    service = WaitlistService(repository)
    request.app.state.waitlist_service = service
    return service


ServiceDependency = Annotated[WaitlistService, Depends(get_waitlist_service)]
NowDependency = Annotated[datetime, Depends(get_now)]


@router.post("/events/{event_id}/waitlist", status_code=status.HTTP_201_CREATED)
def join_waitlist(
    event_id: UUID,
    attendee_id: AttendeeDependency,
    service: ServiceDependency,
    now: NowDependency,
) -> dict:
    # jsonable_encoder keeps datetime.isoformat()'s "+00:00" rendering, which
    # the route's own pydantic serialization would turn into "Z".
    return jsonable_encoder(service.join(str(event_id), attendee_id, now))


@router.get("/waitlist")
def list_my_waitlist_entries(
    attendee_id: AttendeeDependency,
    service: ServiceDependency,
) -> list[dict]:
    return jsonable_encoder(service.list_entries(attendee_id))


@router.post("/waitlist/{entry_id}/acceptance")
def accept_waitlist_offer(
    entry_id: UUID,
    attendee_id: AttendeeDependency,
    service: ServiceDependency,
    now: NowDependency,
) -> dict:
    return jsonable_encoder(service.accept(str(entry_id), attendee_id, now))


@router.post("/waitlist/{entry_id}/withdrawal")
def withdraw_waitlist_entry(
    entry_id: UUID,
    attendee_id: AttendeeDependency,
    service: ServiceDependency,
    now: NowDependency,
) -> dict:
    return jsonable_encoder(service.withdraw(str(entry_id), attendee_id, now))
