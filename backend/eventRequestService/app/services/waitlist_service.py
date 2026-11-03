"""Attendee waiting list: joining and listing (SCRUM-24 AC1).

Reads and early refusals use the pure rules; the write goes through the
`join_waitlist` database function, which re-checks visibility, the window, the
duplicate entries and the D6 capacity under the event row lock, so its
refusals (a race lost between check and write) map to the same errors the
rules raise. The early checks run in the function's order, so an attendee who
is already registered is told that, not that the list is closed.
"""

import logging
from datetime import datetime
from typing import Any

from app.repositories.event_request_repository import SupabaseRepositoryError
from app.repositories.registration_repository import RegistrationRpcError
from app.services.notification_client import NotificationClient
from app.services.registration_rules import (
    EventNotVisibleError,
    RegistrationNotOpenError,
)
from app.services.waitlist_rules import (
    AlreadyRegisteredError,
    AlreadyWaitlistedError,
    AlreadyWithdrawnError,
    CoordinatorNotAssignedError,
    NoOpenPlaceError,
    NotOfferedError,
    NotWaitingError,
    OfferExpiredError,
    OfferWindowClosedError,
    PlacesAvailableError,
    WaitlistEntryNotFoundError,
    check_join,
)

NOT_FOUND_ERRCODE = "P0002"
REFUSED_ERRCODE = "P0004"
logger = logging.getLogger(__name__)

EVENT_COORDINATOR_ROLE = "event_coordinator"


class WaitlistService:
    def __init__(
        self, repository: Any, notification_client: NotificationClient | None = None
    ) -> None:
        self.repository = repository
        self.notification_client = notification_client or NotificationClient(None)

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
        """The attendee's entries, each with its event's name (hotfix 5), so the
        waiting-list page can say which event a place is for."""
        entries = self.repository.list_entries_for(attendee_id)
        events = {
            event["id"]: event
            for event in self.repository.get_events(
                sorted({entry["event_request_id"] for entry in entries})
            )
        }
        return [
            {**entry, "event_name": events.get(entry["event_request_id"], {}).get("event_name")}
            for entry in entries
        ]

    def list_for_event(
        self, event_id: str, caller_id: str, caller_roles: tuple[str, ...]
    ) -> list[dict[str, Any]]:
        """The assigned Coordinator's view of the queue (SCRUM-24 AC3, Q&A #26)."""
        if EVENT_COORDINATOR_ROLE not in caller_roles:
            raise CoordinatorNotAssignedError
        latest = self.repository.latest_coordinator_id(event_id)
        if latest is None or latest != caller_id:
            raise CoordinatorNotAssignedError
        return self.repository.list_event_entries(event_id)

    def accept(
        self, entry_id: str, attendee_id: str, now: datetime
    ) -> dict[str, Any]:
        """Register through the offer (SCRUM-24 AC4).

        The database function re-checks the entry's owner, its Offered status
        and the inclusive D1 window under the event row lock, so a race with
        the timer or a withdrawal is refused there and mapped to the same
        errors the rules raise.
        """
        try:
            entry = self.repository.accept_waitlist_offer(entry_id, attendee_id, now)
        except RegistrationRpcError as error:
            raise self._map_accept_refusal(error) from error
        # The registration was written by the function; read it back for the
        # response. Nothing below may fail the acceptance.
        registration = next(
            (
                r
                for r in self.repository.list_for_attendee(attendee_id)
                if r["event_request_id"] == entry["event_request_id"]
                and r["status"] == "Registered"
            ),
            None,
        )
        self._notify_registration_confirmed(entry, registration)
        return {"entry": entry, "registration": registration}

    def _notify_registration_confirmed(
        self, entry: dict[str, Any], registration: dict[str, Any] | None
    ) -> None:
        """SCRUM-38 AC1: accepting an offered place registers the Attendee, so tell them.

        "Full" is not announced: the offer already held this place, so the occupied
        places did not change. Best-effort, after the commit.
        """
        if registration is None:
            logger.warning(
                "No registration found to confirm for waiting-list entry %s", entry.get("id")
            )
            return
        try:
            event = self.repository.get_event(entry["event_request_id"])
        except SupabaseRepositoryError:
            logger.warning(
                "Could not read event request %s to confirm an accepted offer",
                entry["event_request_id"],
                exc_info=True,
            )
            event = None
        self.notification_client.notify_registration_confirmed(
            event_request_id=entry["event_request_id"],
            attendee_id=registration["attendee_id"],
            event_name=event.get("event_name") if event else None,
            registration_id=registration["id"],
        )

    def withdraw(
        self, entry_id: str, attendee_id: str, now: datetime
    ) -> dict[str, Any]:
        """Withdraw the attendee's own entry (AC6); an offer passes on (AC7)."""
        try:
            return self.repository.withdraw_from_waitlist(entry_id, attendee_id, now)
        except RegistrationRpcError as error:
            raise self._map_withdrawal_refusal(error) from error

    def choose_recipient(
        self,
        event_id: str,
        entry_id: str,
        caller_id: str,
        caller_roles: tuple[str, ...],
        now: datetime,
    ) -> dict[str, Any]:
        """D9 (AC3): the assigned Coordinator picks who receives an open place.

        The assignment is checked here (403 for anyone else) and again inside
        the database function under the event row lock, so a reassignment
        between check and write is refused there.
        """
        if EVENT_COORDINATOR_ROLE not in caller_roles:
            raise CoordinatorNotAssignedError
        latest = self.repository.latest_coordinator_id(event_id)
        if latest is None or latest != caller_id:
            raise CoordinatorNotAssignedError
        try:
            return self.repository.choose_waitlist_recipient(
                event_id, entry_id, caller_id, now
            )
        except RegistrationRpcError as error:
            raise self._map_choice_refusal(error) from error

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

    @staticmethod
    def _map_accept_refusal(error: RegistrationRpcError) -> Exception:
        if error.errcode == NOT_FOUND_ERRCODE:
            return WaitlistEntryNotFoundError()
        if error.errcode == REFUSED_ERRCODE:
            if error.reason == "not offered":
                return NotOfferedError()
            if error.reason == "offer expired":
                return OfferExpiredError()
        return error

    @staticmethod
    def _map_choice_refusal(error: RegistrationRpcError) -> Exception:
        if error.errcode == NOT_FOUND_ERRCODE:
            return EventNotVisibleError()
        if error.errcode == REFUSED_ERRCODE:
            if error.reason == "not waiting":
                return NotWaitingError()
            if error.reason == "no open place":
                return NoOpenPlaceError()
            if error.reason == "offer window":
                return OfferWindowClosedError()
        return error

    @staticmethod
    def _map_withdrawal_refusal(error: RegistrationRpcError) -> Exception:
        if error.errcode == NOT_FOUND_ERRCODE:
            return WaitlistEntryNotFoundError()
        if error.errcode == REFUSED_ERRCODE:
            if error.reason == "already withdrawn":
                return AlreadyWithdrawnError()
            if error.reason == "not offered":
                return NotOfferedError()
        return error
