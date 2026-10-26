import logging
from datetime import UTC, datetime
from typing import Any
from uuid import NAMESPACE_URL, uuid5

import httpx

from app.config import NotificationSettings

logger = logging.getLogger(__name__)


class NotificationClient:
    """Send domain events without failing the originating workflow.

    Assignment and clarification methods remain best-effort side effects.
    Durable outbox methods return acceptance to their relays; review delivery
    records progress only for notificationService's 202 response.
    """

    def __init__(self, notification_service_url: str | None) -> None:
        self._url = notification_service_url

    @classmethod
    def from_settings(cls, settings: NotificationSettings) -> "NotificationClient":
        url = (
            str(settings.notification_service_url)
            if settings.notification_service_url
            else None
        )
        return cls(url)

    def notify_coordinator_assigned(
        self, *, event_request_id: str, coordinator_id: str, assigned_by: str
    ) -> None:
        self._notify_coordinator(
            "coordinator_assigned",
            "assignment to",
            event_request_id=event_request_id,
            coordinator_id=coordinator_id,
            assigned_by=assigned_by,
        )

    def notify_coordinator_unassigned(
        self, *, event_request_id: str, coordinator_id: str, assigned_by: str
    ) -> None:
        """Tell a coordinator an event they held now has someone else (SCRUM-62 AC4)."""
        self._notify_coordinator(
            "coordinator_unassigned",
            "reassignment away from",
            event_request_id=event_request_id,
            coordinator_id=coordinator_id,
            assigned_by=assigned_by,
        )

    def _notify_coordinator(
        self,
        event_type: str,
        described_as: str,
        *,
        event_request_id: str,
        coordinator_id: str,
        assigned_by: str,
    ) -> None:
        if self._url is None:
            return
        try:
            response = httpx.post(
                self._url,
                json={
                    "event_type": event_type,
                    "recipient_id": coordinator_id,
                    "payload": {
                        "event_request_id": event_request_id,
                        "coordinator_id": coordinator_id,
                        "assigned_by": assigned_by,
                    },
                },
                timeout=5,
            )
            response.raise_for_status()
        except httpx.HTTPError:
            logger.warning(
                "Failed to notify coordinator %s of %s event request %s",
                coordinator_id,
                described_as,
                event_request_id,
                exc_info=True,
            )

    def notify_technical_support_assigned(
        self,
        *,
        event_request_id: str,
        event_name: str | None,
        requirement_id: str,
        skill_tag: str,
        staff_id: str,
        assigned_by: str,
        assignment_id: str,
    ) -> None:
        """Tell the assigned staff member what they are on (SCRUM-19 AC5).

        Sent once, after the assignment commits, with the assignment id as the
        event id so notificationService's (recipient_id, event_id) key dedupes
        a retry; a failed notice is logged and the assignment stands.
        """
        if self._url is None:
            return
        try:
            response = httpx.post(
                self._url,
                json={
                    "event_type": "technical_support_assigned",
                    "recipient_id": staff_id,
                    "event_id": assignment_id,
                    "payload": {
                        "event_request_id": event_request_id,
                        "event_name": event_name,
                        "requirement_id": requirement_id,
                        "skill_tag": skill_tag,
                        "assigned_by": assigned_by,
                    },
                },
                timeout=5,
            )
            response.raise_for_status()
        except httpx.HTTPError:
            logger.warning(
                "Failed to notify technical support staff %s of assignment to "
                "requirement %s on event request %s",
                staff_id,
                requirement_id,
                event_request_id,
                exc_info=True,
            )

    def notify_clarification_requested(
        self, *, event_request_id: str, organiser_id: str, reason: str
    ) -> None:
        """Tell the Organiser what the Coordinator needs clarified (SCRUM-37 AC3).

        Sent once, after the decision is recorded, with no retry: if
        notificationService is down the Organiser still finds the clarification
        on the request itself.
        """
        if self._url is None:
            return
        try:
            response = httpx.post(
                self._url,
                json={
                    "event_type": "clarification_requested",
                    "recipient_id": organiser_id,
                    "payload": {
                        "event_request_id": event_request_id,
                        "reason": reason,
                    },
                },
                timeout=5,
            )
            response.raise_for_status()
        except httpx.HTTPError:
            logger.warning(
                "Failed to notify organiser %s of the clarification requested on "
                "event request %s",
                organiser_id,
                event_request_id,
                exc_info=True,
            )

    def notify_event_request_approved(
        self, *, event_request_id: str, organiser_id: str
    ) -> None:
        """Tell the Organiser their request was approved (SCRUM-36 AC1)."""
        self._notify_organiser_of_outcome(
            "event_request_approved",
            event_request_id=event_request_id,
            organiser_id=organiser_id,
            payload={"event_request_id": event_request_id},
        )

    def notify_event_request_rejected(
        self, *, event_request_id: str, organiser_id: str, reason: str
    ) -> None:
        """Tell the Organiser their request was rejected, and why (SCRUM-36 AC1)."""
        self._notify_organiser_of_outcome(
            "event_request_rejected",
            event_request_id=event_request_id,
            organiser_id=organiser_id,
            payload={"event_request_id": event_request_id, "reason": reason},
        )

    def notify_event_confirmed(
        self, *, event_request_id: str, organiser_id: str
    ) -> None:
        """Tell the Organiser their event is confirmed (SCRUM-36 AC3)."""
        self._notify_organiser_of_outcome(
            "event_confirmed",
            event_request_id=event_request_id,
            organiser_id=organiser_id,
            payload={"event_request_id": event_request_id},
        )

    def notify_registration_confirmed(
        self,
        *,
        event_request_id: str,
        attendee_id: str,
        event_name: str | None,
        registration_id: str,
    ) -> None:
        """Tell an Attendee their registration is saved (SCRUM-38 AC1)."""
        self._notify_of_registration(
            "registration_confirmed",
            recipient_id=attendee_id,
            registration_id=registration_id,
            payload={
                "event_request_id": event_request_id,
                "event_name": event_name,
                "registration_id": registration_id,
                "status": "Registered",
            },
        )

    def notify_registration_withdrawn(
        self,
        *,
        event_request_id: str,
        attendee_id: str,
        event_name: str | None,
        registration_id: str,
    ) -> None:
        """Tell an Attendee their withdrawal is saved (SCRUM-22 AC5)."""
        self._notify_of_registration(
            "registration_withdrawn",
            recipient_id=attendee_id,
            registration_id=registration_id,
            payload={
                "event_request_id": event_request_id,
                "event_name": event_name,
                "registration_id": registration_id,
                "status": "Withdrawn",
            },
        )

    def notify_registration_full(
        self,
        *,
        event_request_id: str,
        recipient_id: str,
        event_name: str | None,
        registration_id: str,
        capacity: int,
    ) -> None:
        """Tell an Organiser or Coordinator the last place was taken (SCRUM-38 AC2)."""
        self._notify_of_registration(
            "registration_full",
            recipient_id=recipient_id,
            registration_id=registration_id,
            per_recipient_key=True,
            payload={
                "event_request_id": event_request_id,
                "event_name": event_name,
                "registration_id": registration_id,
                "capacity": capacity,
            },
        )

    def notify_event_cancelled(
        self, *, event_request_id: str, event_name: str | None, attendee_ids: list[str]
    ) -> None:
        """Tell each registered Attendee the event is cancelled (SCRUM-38 AC4)."""
        for attendee_id in attendee_ids:
            self._post_notice(
                "event_cancelled",
                recipient_id=attendee_id,
                key=f"event-cancelled:{event_request_id}:{attendee_id}",
                payload={"event_request_id": event_request_id, "event_name": event_name},
            )

    def notify_event_changed(
        self,
        *,
        event_request_id: str,
        event_name: str | None,
        change_request_id: str,
        proposed_date_times: list[str],
        attendee_ids: list[str],
    ) -> None:
        """Tell each registered Attendee the event's dates changed (SCRUM-38 AC4)."""
        for attendee_id in attendee_ids:
            self._post_notice(
                "event_changed",
                recipient_id=attendee_id,
                key=f"event-changed:{change_request_id}:{attendee_id}",
                payload={
                    "event_request_id": event_request_id,
                    "event_name": event_name,
                    "change_request_id": change_request_id,
                    "proposed_date_times": proposed_date_times,
                },
            )

    def notify_registration_window(
        self,
        *,
        kind: str,
        event_request_id: str,
        event_name: str | None,
        boundary_at: datetime,
        recipient_id: str,
    ) -> None:
        """Tell an Organiser or Coordinator registration opened or closed (SCRUM-38 AC3).

        The key holds the boundary time, so repeating a pass sends the same key
        (stored once) and a moved window sends a new one.
        """
        moment = boundary_at.astimezone(UTC).isoformat()
        self._post_notice(
            f"registration_{kind}",
            recipient_id=recipient_id,
            key=f"registration-{kind}:{event_request_id}:{moment}:{recipient_id}",
            payload={
                "event_request_id": event_request_id,
                "event_name": event_name,
                "boundary_at": moment,
            },
        )

    def _post_notice(
        self, event_type: str, *, recipient_id: str, key: str, payload: dict[str, Any]
    ) -> None:
        """One best-effort notice with a stable key; a failure is logged, never raised."""
        if self._url is None:
            return
        try:
            response = httpx.post(
                self._url,
                json={
                    "event_type": event_type,
                    "recipient_id": recipient_id,
                    "event_id": str(uuid5(NAMESPACE_URL, key)),
                    "payload": payload,
                },
                timeout=5,
            )
            response.raise_for_status()
        except httpx.HTTPError:
            logger.warning(
                "Failed to notify %s of %s (%s)",
                recipient_id,
                event_type,
                payload.get("event_request_id"),
                exc_info=True,
            )

    def _notify_of_registration(
        self,
        event_type: str,
        *,
        recipient_id: str,
        registration_id: str,
        payload: dict[str, Any],
        per_recipient_key: bool = False,
    ) -> None:
        """Best-effort registration notice, sent once after the registration saved.

        The key is per registration and type (and per recipient when one
        registration notifies several people), so a repeat is stored once while a
        place freed and filled again notifies again.
        """
        if self._url is None:
            return
        try:
            response = httpx.post(
                self._url,
                json={
                    "event_type": event_type,
                    "recipient_id": recipient_id,
                    "event_id": str(
                        uuid5(
                            NAMESPACE_URL,
                            f"{event_type.replace('_', '-')}:{registration_id}"
                            + (f":{recipient_id}" if per_recipient_key else ""),
                        )
                    ),
                    "payload": payload,
                },
                timeout=5,
            )
            response.raise_for_status()
        except httpx.HTTPError:
            logger.warning(
                "Failed to notify %s of %s for registration %s",
                recipient_id,
                event_type,
                registration_id,
                exc_info=True,
            )

    def _notify_organiser_of_outcome(
        self,
        event_type: str,
        *,
        event_request_id: str,
        organiser_id: str,
        payload: dict[str, Any],
    ) -> None:
        """Best-effort outcome notice, sent once after the decision has committed.

        The key is stable per request and type, so an accidental repeat is stored
        once. A failure is logged and never raised: the saved decision stands.
        """
        if self._url is None:
            return
        try:
            response = httpx.post(
                self._url,
                json={
                    "event_type": event_type,
                    "recipient_id": organiser_id,
                    "event_id": str(
                        uuid5(
                            NAMESPACE_URL,
                            f"{event_type.replace('_', '-')}:{event_request_id}",
                        )
                    ),
                    "payload": payload,
                },
                timeout=5,
            )
            response.raise_for_status()
        except httpx.HTTPError:
            logger.warning(
                "Failed to notify organiser %s of %s on event request %s",
                organiser_id,
                event_type,
                event_request_id,
                exc_info=True,
            )

    def notify_event_change_rejected(
        self, *, event_request_id: str, change_request_id: str,
        organiser_id: str, reason: str,
    ) -> None:
        """Best-effort outcome notice after the rejection has committed.

        The stable key lets the receiver deduplicate an accidental repeat; this
        sender has no durable retry queue and cannot undo the saved decision.
        """
        if self._url is None:
            return
        try:
            response = httpx.post(
                self._url,
                json={
                    "event_type": "event_change_rejected",
                    "recipient_id": organiser_id,
                    "event_id": str(uuid5(
                        NAMESPACE_URL, f"event-change-rejected:{change_request_id}"
                    )),
                    "payload": {
                        "event_request_id": event_request_id,
                        "change_request_id": change_request_id,
                        "reason": reason,
                    },
                },
                timeout=5,
            )
            if response.status_code != 202:
                logger.warning(
                    "Rejection notification was not accepted (HTTP %s) for change %s",
                    response.status_code, change_request_id,
                )
        except httpx.HTTPError:
            logger.warning(
                "Failed to notify organiser of rejected change %s",
                change_request_id, exc_info=True,
            )

    def notify_event_change_approved(
        self, *, event_request_id: str, change_request_id: str,
        organiser_id: str, reason: str | None,
    ) -> None:
        """One best-effort organiser outcome after the approved plan is stored."""
        if self._url is None:
            return
        try:
            response = httpx.post(
                self._url,
                json={
                    "event_type": "event_change_approved",
                    "recipient_id": organiser_id,
                    "event_id": str(uuid5(
                        NAMESPACE_URL, f"event-change-approved:{change_request_id}"
                    )),
                    "payload": {
                        "event_request_id": event_request_id,
                        "change_request_id": change_request_id,
                        "reason": reason,
                    },
                },
                timeout=5,
            )
            if response.status_code != 202:
                logger.warning(
                    "Approval notification was not accepted (HTTP %s) for change %s",
                    response.status_code, change_request_id,
                )
        except httpx.HTTPError:
            logger.warning(
                "Failed to notify organiser of approved change %s",
                change_request_id, exc_info=True,
            )

    def notify_safety_changes_requested(
        self, *, event_request_id: str, coordinator_id: str, reason: str
    ) -> None:
        """Tell the assigned Coordinator what the Safety Officer wants changed
        (SCRUM-60 AC4b). Sent once after the decision commits, like the
        clarification notice; the reason also stays readable on the request."""
        if self._url is None:
            return
        try:
            response = httpx.post(
                self._url,
                json={
                    "event_type": "safety_changes_requested",
                    "recipient_id": coordinator_id,
                    "payload": {
                        "event_request_id": event_request_id,
                        "reason": reason,
                    },
                },
                timeout=5,
            )
            response.raise_for_status()
        except httpx.HTTPError:
            logger.warning(
                "Failed to notify coordinator %s of the safety changes requested on "
                "event request %s",
                coordinator_id,
                event_request_id,
                exc_info=True,
            )

    def notify_event_request_submitted(
        self, *, event_id: str, organiser_id: str, payload: dict[str, Any]
    ) -> bool:
        """Send the Organiser's submission confirmation (SCRUM-37 AC1).

        Returns whether it was delivered, so the outbox relay marks an event as
        published only once notificationService has accepted it.
        """
        if self._url is None:
            return False
        try:
            response = httpx.post(
                self._url,
                json={
                    "event_type": "event_request_submitted",
                    "recipient_id": organiser_id,
                    "event_id": event_id,
                    "payload": payload,
                },
                timeout=5,
            )
            response.raise_for_status()
        except httpx.HTTPError:
            logger.warning(
                "Failed to send submission confirmation %s to organiser %s",
                event_id,
                organiser_id,
                exc_info=True,
            )
            return False
        return True

    def notify_arrangement_needs_review(
        self, *, event_id: str, recipient_id: str, payload: dict[str, Any]
    ) -> bool:
        """Only durable 202 acceptance permits recording review-delivery progress."""
        if self._url is None:
            return False
        try:
            response = httpx.post(
                self._url,
                json={
                    "event_type": "arrangement_needs_review",
                    "recipient_id": recipient_id,
                    "event_id": event_id,
                    "payload": payload,
                },
                timeout=5,
            )
            if response.status_code != 202:
                logger.warning(
                    "Review notification %s was not accepted for %s",
                    event_id,
                    recipient_id,
                )
                return False
        except httpx.HTTPError:
            logger.warning(
                "Review notification %s could not reach recipient %s",
                event_id,
                recipient_id,
                exc_info=True,
            )
            return False
        return True
