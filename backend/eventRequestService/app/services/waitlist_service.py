"""Attendee waiting list: joining and listing (SCRUM-24 AC1).

Reads and early refusals use the pure rules; the write goes through the
`join_waitlist` database function, which re-checks visibility, the window, the
duplicate entries and the D6 capacity under the event row lock, so its
refusals (a race lost between check and write) map to the same errors the
rules raise. The early checks run in the function's order, so an attendee who
is already registered is told that, not that the list is closed.
"""

from datetime import datetime
from typing import Any

from app.repositories.registration_repository import RegistrationRpcError
from app.services.registration_rules import (
    EventNotVisibleError,
    RegistrationNotOpenError,
)
from app.services.waitlist_rules import (
    AlreadyRegisteredError,
    AlreadyWaitlistedError,
    PlacesAvailableError,
    check_join,
)

NOT_FOUND_ERRCODE = "P0002"
REFUSED_ERRCODE = "P0004"


class WaitlistService:
    def __init__(self, repository: Any) -> None:
        self.repository = repository

    def join(
        self, event_id: str, attendee_id: str, now: datetime
    ) -> dict[str, Any]:
        event = self.repository.get_event(event_id)
        if event is None or event.get("status") != "Confirmed":
            raise EventNotVisibleError
        check_join(
            event,
            now,
            self.repository.places_taken(event_id),
            self.repository.has_active(event_id, attendee_id),
            self.repository.active_entry(event_id, attendee_id),
        )
        try:
            entry = self.repository.join_waitlist(event_id, attendee_id, now)
        except RegistrationRpcError as error:
            raise self._map_refusal(error) from error
        return self._with_position(entry, attendee_id)

    def list_entries(self, attendee_id: str) -> list[dict[str, Any]]:
        return self.repository.list_entries_for(attendee_id)

    def _with_position(
        self, entry: dict[str, Any], attendee_id: str
    ) -> dict[str, Any]:
        for row in self.repository.list_entries_for(attendee_id):
            if row["id"] == entry["id"]:
                return {**entry, "position": row.get("position")}
        return {**entry, "position": None}

    @staticmethod
    def _map_refusal(error: RegistrationRpcError) -> Exception:
        if error.errcode == NOT_FOUND_ERRCODE:
            return EventNotVisibleError()
        if error.errcode == REFUSED_ERRCODE:
            if error.reason == "already registered":
                return AlreadyRegisteredError()
            if error.reason == "already waitlisted":
                return AlreadyWaitlistedError()
            if error.reason == "registration not open":
                return RegistrationNotOpenError()
            if error.reason == "places available":
                return PlacesAvailableError()
        return error
