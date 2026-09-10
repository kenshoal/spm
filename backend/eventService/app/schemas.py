"""Pydantic request/response shapes for the events API."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.status import EventStatus


class EventCreate(BaseModel):
    title: str


class EventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    status: EventStatus
    organiser_id: str
    coordinator_id: str | None
    created_at: datetime
    updated_at: datetime


class StatusTransitionRequest(BaseModel):
    target_status: EventStatus
