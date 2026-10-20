from datetime import datetime
from typing import Any

from app.repositories.registration_repository import (
    RegistrationRepository,
    RegistrationRpcError,
)
from app.services.registration_rules import (
    EventFullError,
    EventNotVisibleError,
    RegistrationNotOpenError,
    check_registration,
    is_window_open,
    to_public_event,
)

NOT_FOUND_ERRCODE = "P0002"
REFUSED_ERRCODE = "P0004"


class AlreadyRegisteredError(Exception):
    """The attendee already holds an active registration for this event."""


class RegistrationService:
    """Attendee view of Confirmed events and registration for them (SCRUM-21).

    Reads and early refusals use the pure rules; the write goes through the
    `register_for_event` database function, which re-checks under a row lock,
    so its refusals (a race lost between check and write) are mapped to the same
    errors the rules raise. The early checks run in the function's order —
    visible, window, already registered, capacity — so an attendee holding the
    last place is told they are already registered, not that the event is full.
    """

    def __init__(self, repository: RegistrationRepository) -> None:
        self.repository = repository

    def list_open_events(self, now: datetime) -> list[dict[str, Any]]:
        events = [
            event
            for event in self.repository.list_confirmed_events()
            if is_window_open(event, now)
        ]
        counts = self.repository.count_active_for_events([e["id"] for e in events])
        return [to_public_event(e, counts.get(e["id"], 0)) for e in events]

    def get_event(self, event_id: str) -> dict[str, Any]:
        event = self._visible_event(event_id)
        return to_public_event(event, self.repository.count_active(event_id))

    def register(
        self, event_id: str, attendee_id: str, now: datetime
    ) -> dict[str, Any]:
        event = self._visible_event(event_id)
        if not is_window_open(event, now):
            raise RegistrationNotOpenError
        if self.repository.has_active(event_id, attendee_id):
            raise AlreadyRegisteredError
        check_registration(event, now, self.repository.count_active(event_id))
        try:
            registration = self.repository.register(event_id, attendee_id, now)
        except RegistrationRpcError as error:
            raise self._map_refusal(error) from error
        return {
            **registration,
            "event": to_public_event(event, self.repository.count_active(event_id)),
        }

    def list_registrations(self, attendee_id: str) -> list[dict[str, Any]]:
        registrations = self.repository.list_for_attendee(attendee_id)
        event_ids = sorted({r["event_request_id"] for r in registrations})
        events = {e["id"]: e for e in self.repository.get_events(event_ids)}
        counts = self.repository.count_active_for_events(event_ids)
        return [
            {
                **registration,
                "event": to_public_event(
                    events[registration["event_request_id"]],
                    counts.get(registration["event_request_id"], 0),
                ),
            }
            for registration in registrations
            if registration["event_request_id"] in events
        ]

    def _visible_event(self, event_id: str) -> dict[str, Any]:
        event = self.repository.get_event(event_id)
        if event is None or event.get("status") != "Confirmed":
            raise EventNotVisibleError
        return event

    @staticmethod
    def _map_refusal(error: RegistrationRpcError) -> Exception:
        if error.errcode == NOT_FOUND_ERRCODE:
            return EventNotVisibleError()
        if error.errcode == REFUSED_ERRCODE:
            if error.reason == "already registered":
                return AlreadyRegisteredError()
            if error.reason == "event full":
                return EventFullError()
            if error.reason == "registration not open":
                return RegistrationNotOpenError()
        return error
