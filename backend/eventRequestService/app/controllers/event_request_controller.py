from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status

from app.models.event_request import (
    EventRequestCreate,
    EventRequestResponse,
    EventRequestUpdate,
)
from app.services.event_request_service import EventRequestService

router = APIRouter(prefix="/event-requests", tags=["event requests"])


def get_event_request_service(request: Request) -> EventRequestService:
    """Return the service owned by this FastAPI application instance."""
    return request.app.state.event_request_service


def get_organiser_id(
    x_organiser_id: Annotated[str, Header(alias="X-Organiser-Id")],
) -> str:
    """Temporary identity boundary until the authentication service is integrated."""
    organiser_id = x_organiser_id.strip()
    if not organiser_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="X-Organiser-Id must not be blank",
        )
    return organiser_id


ServiceDependency = Annotated[EventRequestService, Depends(get_event_request_service)]
OrganiserDependency = Annotated[str, Depends(get_organiser_id)]


@router.post(
    "",
    response_model=EventRequestResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_event_request(
    payload: EventRequestCreate,
    organiser_id: OrganiserDependency,
    service: ServiceDependency,
) -> EventRequestResponse:
    return service.create(payload, organiser_id)


@router.get("", response_model=list[EventRequestResponse])
def list_event_requests(
    organiser_id: OrganiserDependency,
    service: ServiceDependency,
) -> list[EventRequestResponse]:
    return service.list_for_organiser(organiser_id)


@router.get("/{event_request_id}", response_model=EventRequestResponse)
def get_event_request(
    event_request_id: str,
    organiser_id: OrganiserDependency,
    service: ServiceDependency,
) -> EventRequestResponse:
    return service.get(event_request_id, organiser_id)


@router.patch("/{event_request_id}", response_model=EventRequestResponse)
def update_event_request(
    event_request_id: str,
    payload: EventRequestUpdate,
    organiser_id: OrganiserDependency,
    service: ServiceDependency,
) -> EventRequestResponse:
    return service.update(event_request_id, organiser_id, payload)


@router.delete("/{event_request_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_event_request(
    event_request_id: str,
    organiser_id: OrganiserDependency,
    service: ServiceDependency,
) -> Response:
    service.delete(event_request_id, organiser_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

