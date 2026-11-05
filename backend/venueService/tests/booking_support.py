"""Shared helpers for the booking-request tests (SCRUM-32).

``FakeEventService`` stands in for eventRequestService at the HTTP boundary, so
the real ``EventRequestClient`` is exercised by the router tests. It answers the
two reads the client makes and records every call it receives.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx

from app.booking_models import BookingRequest
from app.booking_repository import booking_repository
from app.dependencies import Principal, require_authenticated, require_venue_staff
from app.event_requests import EventRequestClient, get_event_client
from app.main import app
from app.models import Venue, VenueCreate, VenueStatus, VenueUpdate
from app.repository import repository

COORDINATOR = "11111111-1111-4111-8111-111111111111"
OTHER_COORDINATOR = "22222222-2222-4222-8222-222222222222"
ORGANISER = "33333333-3333-4333-8333-333333333333"
STAFF = "44444444-4444-4444-8444-444444444444"
EVENT = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
OTHER_EVENT = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
EVENT_URL = "http://event-requests.test"
OMIT = object()


class FakeEventService:
    def __init__(self) -> None:
        self.events: dict[str, dict[str, Any]] = {}
        self.calls: list[tuple[str, str | None]] = []
        self.failure: str | None = None

    def add_event(
        self,
        event_id: str = EVENT,
        coordinator_id: str = COORDINATOR,
        event_name: str | None = "Annual Gala",
        expected_attendance: int | None = 120,
        venue_requirements: str | None = "Stage and projector",
        status: str = "Planning",
        accessibility_needs: str | None = "Step-free access",
    ) -> None:
        self.events[event_id] = {
            "coordinator_id": coordinator_id,
            "event_name": event_name,
            "expected_attendance": expected_attendance,
            "venue_requirements": venue_requirements,
            "accessibility_needs": accessibility_needs,
            "updated_at": "2026-10-22T00:00:00+00:00",
            "status": status,
        }

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls.append((request.url.path, request.headers.get("authorization")))
        if self.failure == "connect":
            raise httpx.ConnectError("down", request=request)
        if self.failure == "timeout":
            raise httpx.ReadTimeout("slow", request=request)
        if self.failure == "500":
            return httpx.Response(500, json={"detail": "boom"})
        if self.failure == "401":
            return httpx.Response(401, json={"detail": "Invalid session"})
        match = re.fullmatch(r"/event-requests/([^/]+)(/coordinator)?", request.url.path)
        event = self.events.get(match.group(1)) if match else None
        if match is None or event is None:
            return httpx.Response(404, json={"detail": "Event request not found"})
        if match.group(2):
            if self.failure == "malformed":
                return httpx.Response(200, json={})
            if event["coordinator_id"] != self._caller_hint:
                return httpx.Response(404, json={"detail": "Event request not found"})
            return httpx.Response(
                200,
                json={"event_request_id": match.group(1), "coordinator_id": event["coordinator_id"]},
            )
        return httpx.Response(200, json={"id": match.group(1), **event})

    # eventRequestService answers a Coordinator only for events assigned to
    # them; the fake reproduces that using the caller set by ``install``.
    _caller_hint: str = COORDINATOR

    def install(self, caller_id: str) -> None:
        self._caller_hint = caller_id
        client = EventRequestClient(EVENT_URL, transport=httpx.MockTransport(self.handler))
        app.dependency_overrides[get_event_client] = lambda: client


def as_user(user_id: str, *roles: str, events: FakeEventService | None = None) -> None:
    """Act as ``user_id`` with ``roles``; the real role checks stay in force."""
    principal = Principal(user_id=user_id, roles=tuple(roles))
    app.dependency_overrides[require_authenticated] = lambda: principal
    app.dependency_overrides.pop(require_venue_staff, None)
    if events is not None:
        events.install(user_id)


def make_venue(**overrides: Any) -> Venue:
    status = overrides.pop("status", None)
    data = {"name": "Orchard Hall", "location": "Orchard Road", "max_capacity": 200}
    data.update(overrides)
    venue = repository.create(VenueCreate(**data))
    if status is not None:
        venue = repository.update(venue.id, VenueUpdate(status=VenueStatus(status))) or venue
    return venue


def submit_body(venue_id: str, /, **overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "venue_id": venue_id,
        "event_request_id": EVENT,
        "start_date": "2030-01-10",
        "end_date": "2030-01-10",
        # 07:00-12:00, the old AM slot (SCRUM-65).
        "start_minute": 420,
        "end_minute": 720,
    }
    body.update(overrides)
    return {key: value for key, value in body.items() if value is not OMIT}


BASE_TIME = datetime(2030, 1, 1, tzinfo=UTC)


def seed_booking(minutes: int = 0, **overrides: Any) -> BookingRequest:
    """Store a booking request directly, so any status can be set up."""

    fields: dict[str, Any] = {
        "venue_id": "venue-1",
        "requested_by": COORDINATOR,
        "event_request_id": EVENT,
        "start_date": date(2030, 1, 10),
        "end_date": date(2030, 1, 10),
        "slots": ["AM"],
        "created_at": BASE_TIME + timedelta(minutes=minutes),
    }
    fields.update(overrides)
    return booking_repository.create(BookingRequest(**fields))
