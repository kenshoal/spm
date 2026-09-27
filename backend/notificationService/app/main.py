import logging

from fastapi import FastAPI, status
from pydantic import BaseModel

from app.models import EventAccepted, NotificationEvent

# Uvicorn only configures its own loggers; without this the stub's
# "received" lines never reach `docker compose logs`, which is how callers
# check their hooks are wired up.
logging.basicConfig(level=logging.INFO, format="%(levelname)s:     %(message)s")
logger = logging.getLogger(__name__)


class ServiceResponse(BaseModel):
    service: str
    message: str


class HealthResponse(BaseModel):
    service: str
    status: str


app = FastAPI(
    title="notificationService",
    description="Notification microservice for SPM.",
    version="0.1.0",
)


@app.get("/", response_model=ServiceResponse, tags=["service"])
def hello() -> ServiceResponse:
    return ServiceResponse(
        service="notificationService",
        message="Hello from notificationService",
    )


@app.get("/health", response_model=HealthResponse, tags=["health"])
def health() -> HealthResponse:
    return HealthResponse(service="notificationService", status="ok")


@app.post(
    "/notifications/events",
    response_model=EventAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["notifications"],
)
def receive_event(event: NotificationEvent) -> EventAccepted:
    # Stub: the contract is live so other services can integrate now, but
    # events are only logged. Persistence and delivery follow in SCRUM-37.
    logger.info(
        "Received %s event for recipient %s", event.event_type, event.recipient_id
    )
    return EventAccepted(status="accepted")
