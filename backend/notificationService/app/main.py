import logging
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError

from app.auth import get_current_user_id
from app.config import get_settings
from app.delivery import Delivery
from app.models import EventAccepted, NotificationEvent, NotificationResponse
from app.repository import (
    NotificationRepository,
    NotificationStoreError,
    SupabaseNotificationRepository,
)

# Uvicorn only configures its own loggers; without this the "received" lines
# never reach `docker compose logs`, which is how callers check their hooks
# are wired up.
logging.basicConfig(level=logging.INFO, format="%(levelname)s:     %(message)s")
logger = logging.getLogger(__name__)


class ServiceResponse(BaseModel):
    service: str
    message: str


class HealthResponse(BaseModel):
    service: str
    status: str


def get_repository(request: Request) -> NotificationRepository:
    """Return the repository owned by this FastAPI application instance."""
    repository = request.app.state.notification_repository
    if repository is not None:
        return repository

    try:
        repository = SupabaseNotificationRepository.from_settings(get_settings())
    except ValidationError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Supabase is not configured for notificationService",
        ) from error

    request.app.state.notification_repository = repository
    return repository


RepositoryDependency = Annotated[NotificationRepository, Depends(get_repository)]
UserIdDependency = Annotated[str, Depends(get_current_user_id)]


def create_app(
    repository: NotificationRepository | None = None,
    delivery: Delivery | None = None,
) -> FastAPI:
    application = FastAPI(
        title="notificationService",
        description="Notification microservice for SPM.",
        version="0.2.0",
    )
    application.state.notification_repository = repository
    application.state.delivery = delivery

    @application.exception_handler(NotificationStoreError)
    async def store_unavailable(
        request: Request, error: NotificationStoreError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={"detail": str(error)},
        )

    @application.get("/", response_model=ServiceResponse, tags=["service"])
    def hello() -> ServiceResponse:
        return ServiceResponse(
            service="notificationService",
            message="Hello from notificationService",
        )

    @application.get("/health", response_model=HealthResponse, tags=["health"])
    def health() -> HealthResponse:
        return HealthResponse(service="notificationService", status="ok")

    @application.post(
        "/notifications/events",
        response_model=EventAccepted,
        status_code=status.HTTP_202_ACCEPTED,
        tags=["notifications"],
    )
    def receive_event(
        event: NotificationEvent, repository: RepositoryDependency, request: Request
    ) -> EventAccepted:
        # Internal, service-to-service only: not yet authenticated (see README).
        created = repository.save(
            event_type=event.event_type,
            recipient_id=event.recipient_id,
            payload=event.payload,
            event_id=event.event_id,
        )
        logger.info(
            "Received %s event for recipient %s%s",
            event.event_type,
            event.recipient_id,
            "" if created else " (duplicate event_id, ignored)",
        )
        delivery = request.app.state.delivery
        if created and delivery is not None:
            delivery.deliver(
                event_type=event.event_type,
                recipient_id=event.recipient_id,
                payload=event.payload,
            )
        return EventAccepted(status="accepted")

    @application.get(
        "/notifications",
        response_model=list[NotificationResponse],
        tags=["notifications"],
    )
    def list_notifications(
        user_id: UserIdDependency,
        repository: RepositoryDependency,
        unread_only: bool = False,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
    ) -> list[dict]:
        return repository.list_for_recipient(
            user_id, unread_only=unread_only, limit=limit
        )

    @application.patch(
        "/notifications/{notification_id}/read",
        response_model=NotificationResponse,
        tags=["notifications"],
    )
    def mark_notification_read(
        notification_id: UUID,
        user_id: UserIdDependency,
        repository: RepositoryDependency,
    ) -> dict:
        notification = repository.mark_read(str(notification_id), user_id)
        if notification is None:
            # Same answer for "missing" and "someone else's", so ids can't be probed.
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Notification not found")
        return notification

    return application


app = create_app()
