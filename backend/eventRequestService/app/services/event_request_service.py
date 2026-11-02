import json
import logging
from datetime import UTC
from typing import Any, NoReturn

from pydantic import ValidationError

from app.models.arrangement_review import ArrangementReviewResponse
from app.models.event_request import (
    EventChangeBookingConflict,
    EventChangeBookingContext,
    EventChangeBookingContextItem,
    EventChangeBookingPlanItem,
    EventChangeDatePlanBooking,
    EventChangeDatePlanResponse,
    EventChangeDecision,
    EventChangeRequestCreate,
    EventChangeRequestResponse,
    EventChangeRequestStatus,
    EventClarificationResponse,
    EventDetailsUpdate,
    EventFinalEndUpdate,
    EventRequestCreate,
    EventRequestResponse,
    EventRequestStatus,
    EventRequestSubmission,
    EventRequestUpdate,
    EventReviewDecisionResponse,
    EventStatusHistoryResponse,
    SafetyDecision,
    SafetyReviewResponse,
)
from app.models.registration_review import RegistrationReviewResponse
from app.repositories import EventRequestRepository
from app.repositories.event_request_repository import (
    EventRequestRpcError,
    SupabaseRepositoryError,
)
from app.services.event_change_date_plan import (
    DateReschedulePlanError,
    plan_date_only_reschedule,
)
from app.services.notification_client import NotificationClient

logger = logging.getLogger(__name__)


class ArrangementReviewActionError(Exception):
    """A locked review mutation was refused without exposing storage details."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class EventRequestNotFoundError(Exception):
    def __init__(self, event_request_id: str) -> None:
        super().__init__(f"Event request {event_request_id} was not found")
        self.event_request_id = event_request_id


class EventRequestForbiddenError(Exception):
    """The caller may view the request (same client organisation) but not change it."""

    def __init__(self, event_request_id: str) -> None:
        super().__init__("Insufficient permissions")
        self.event_request_id = event_request_id


class EventRequestNotDraftError(Exception):
    def __init__(self, event_request_id: str) -> None:
        super().__init__(f"Event request {event_request_id} is no longer a Draft")
        self.event_request_id = event_request_id


class ClarificationResponseNotAllowedError(Exception):
    def __init__(self, event_request_id: str) -> None:
        super().__init__(
            f"Event request {event_request_id} is not accepting a clarification response"
        )
        self.event_request_id = event_request_id


class EventChangeRequestConflictError(Exception):
    def __init__(self, event_request_id: str) -> None:
        super().__init__(f"Event request {event_request_id} cannot accept that change action")
        self.event_request_id = event_request_id


class EventChangeRequestForbiddenError(Exception):
    def __init__(self, event_request_id: str) -> None:
        super().__init__("Only the currently assigned coordinator can decide this change request")
        self.event_request_id = event_request_id


class EventChangeDatePlanConflictError(Exception):
    """The saved proposal cannot currently produce an advisory date plan."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class EventChangeBookingConflictError(Exception):
    def __init__(self, bookings: list[EventChangeBookingConflict]) -> None:
        super().__init__("One or more venue bookings conflict with the proposed plan.")
        self.bookings = bookings


class EventChangeBookingPlanError(Exception):
    """Invalid complete range input; never forward a raw database message."""


class EventChangeSelectionError(Exception):
    """Hotfix 20: the accepted fields, a missing reason or the booking plan are invalid."""


class EventDetailsConflictError(Exception):
    """The event changed since it was loaded, or its status does not allow edits."""


class EventRequestTransitionConflictError(Exception):
    """The row wasn't in from_status when the transition was attempted —
    a concurrent change, since callers check status before transitioning."""

    def __init__(self, event_request_id: str, from_status: str, to_status: str) -> None:
        super().__init__(
            f"Event request {event_request_id} was not {from_status!r} when "
            f"transitioning to {to_status!r}"
        )
        self.event_request_id = event_request_id


# Where a change request can be raised and decided, including after confirmation
# (hotfix 9, Week 1 brief, Q&A #8).
CHANGEABLE_STATUSES = {
    EventRequestStatus.APPROVED,
    EventRequestStatus.PLANNING,
    EventRequestStatus.CONFIRMED,
}


class EventRequestService:
    """Owns Draft and submission rules independently of Supabase transport."""

    def __init__(
        self, repository: EventRequestRepository,
        notification_client: NotificationClient | None = None,
    ) -> None:
        self.repository = repository
        self.notification_client = notification_client or NotificationClient(None)

    def list_registration_reviews(self, event_request_id: str) -> list[RegistrationReviewResponse]:
        """Return complete retained history after controller relationship checks."""
        try:
            rows = self.repository.list_registration_reviews(event_request_id)
            reviews = [RegistrationReviewResponse.model_validate(row) for row in rows]
            return sorted(reviews, key=lambda row: (row.raised_at.astimezone(UTC), row.id), reverse=True)
        except (SupabaseRepositoryError, ValidationError, ValueError, TypeError, KeyError) as error:
            raise SupabaseRepositoryError("Registration reviews unavailable") from error

    def acknowledge_registration_review(
        self, event_request_id: str, review_id: str, actor_id: str,
    ) -> RegistrationReviewResponse:
        try:
            row = self.repository.acknowledge_registration_review(event_request_id, review_id, actor_id)
            return RegistrationReviewResponse.model_validate(row)
        except EventRequestRpcError as error:
            if error.errcode in {"P0002", "P0003", "P0004"}:
                raise ArrangementReviewActionError(error.errcode) from error
            raise SupabaseRepositoryError("Registration reviews unavailable") from error
        except (SupabaseRepositoryError, ValidationError, ValueError, TypeError) as error:
            raise SupabaseRepositoryError("Registration reviews unavailable") from error

    def list_arrangement_reviews(
        self, event_request_id: str
    ) -> list[ArrangementReviewResponse]:
        """Outstanding work uses the same persisted rows as future readiness reads."""
        try:
            rows = self.repository.list_arrangement_reviews(event_request_id)
        except SupabaseRepositoryError as error:
            raise SupabaseRepositoryError("Arrangement reviews unavailable") from error
        return self._outstanding_arrangement_reviews(rows)

    def list_arrangement_reviews_for_arrangement(
        self, arrangement: str
    ) -> list[ArrangementReviewResponse]:
        """A staff queue spans events but remains scoped to one authorised domain."""
        try:
            rows = self.repository.list_arrangement_reviews_for_arrangement(arrangement)
        except SupabaseRepositoryError as error:
            raise SupabaseRepositoryError("Arrangement reviews unavailable") from error
        return self._outstanding_arrangement_reviews(rows)

    def clear_arrangement_review(
        self, review_id: str, actor_id: str, allowed_arrangements: list[str]
    ) -> ArrangementReviewResponse:
        """The database rechecks domain and stale state while locking the exact row."""
        try:
            row = self.repository.clear_arrangement_review(
                review_id, actor_id, allowed_arrangements
            )
        except EventRequestRpcError as error:
            if error.errcode in {"P0002", "P0003", "P0004"}:
                raise ArrangementReviewActionError(error.errcode) from error
            raise SupabaseRepositoryError("Arrangement reviews unavailable") from error
        except SupabaseRepositoryError as error:
            raise SupabaseRepositoryError("Arrangement reviews unavailable") from error
        return ArrangementReviewResponse.model_validate(row)

    @staticmethod
    def _outstanding_arrangement_reviews(
        rows: list[dict[str, Any]],
    ) -> list[ArrangementReviewResponse]:
        outstanding = (
            ArrangementReviewResponse.model_validate(row)
            for row in rows
            if row["cleared_at"] is None
        )
        return sorted(
            outstanding,
            key=lambda review: (review.raised_at.astimezone(UTC), review.id),
            reverse=True,
        )

    def list_status_history(self, event_request_id: str) -> list[EventStatusHistoryResponse]:
        """Sort deterministically even when several entries have equal timestamps."""
        rows = self.repository.list_status_history(event_request_id)
        return sorted(
            (EventStatusHistoryResponse.model_validate(row) for row in rows),
            key=lambda entry: (entry.occurred_at, entry.id),
        )

    def create(
        self, payload: EventRequestCreate, organiser_id: str
    ) -> EventRequestResponse:
        values = payload.model_dump(mode="json")
        values.update(
            {
                "organiser_id": organiser_id,
                "status": EventRequestStatus.DRAFT.value,
            }
        )
        return self._row_to_response(self.repository.create(values))

    def create_submission(
        self, payload: EventRequestSubmission, organiser_id: str
    ) -> EventRequestResponse:
        values = payload.model_dump(mode="json")
        values.update(
            {
                "organiser_id": organiser_id,
                "status": EventRequestStatus.SUBMITTED.value,
            }
        )
        return self._row_to_response(self.repository.create(values))

    def list_for_organiser(self, organiser_id: str) -> list[EventRequestResponse]:
        """The organiser's own requests plus their organisation's non-Draft ones."""
        rows = {row["id"]: row for row in self.repository.list_for_organiser(organiser_id)}
        organisation_id = self.repository.get_organisation_id(organiser_id)
        if organisation_id is not None:
            for row in self.repository.list_shared_with_organisation(organisation_id):
                rows.setdefault(row["id"], row)
        return sorted(
            (self._row_to_response(row) for row in rows.values()),
            key=lambda request: request.created_at,
            reverse=True,
        )

    def get_viewable(
        self, event_request_id: str, organiser_id: str
    ) -> EventRequestResponse:
        """Read access for an organiser: the owner, or a same-organisation
        colleague once the request has left Draft (SCRUM-39)."""
        row = self.repository.get_by_id(event_request_id)
        if row is None or not self._can_view(row, organiser_id):
            raise EventRequestNotFoundError(event_request_id)
        return self._row_to_response(row)

    def _can_view(self, row: dict[str, Any], organiser_id: str) -> bool:
        if row["organiser_id"] == organiser_id:
            return True
        organisation_id = row.get("organisation_id")
        return (
            row["status"] != EventRequestStatus.DRAFT.value
            and organisation_id is not None
            and organisation_id == self.repository.get_organisation_id(organiser_id)
        )

    def _refusal(self, event_request_id: str, organiser_id: str) -> Exception:
        """403 for a colleague who can already see the request, else 404."""
        row = self.repository.get_by_id(event_request_id)
        if row is not None and self._can_view(row, organiser_id):
            return EventRequestForbiddenError(event_request_id)
        return EventRequestNotFoundError(event_request_id)

    def list_by_status(self, status: EventRequestStatus) -> list[EventRequestResponse]:
        """Unscoped lookup across every organiser, for a caller whose remit is
        the whole queue rather than one organiser's own requests.
        """
        rows = self.repository.list_by_status(status.value)
        return [self._row_to_response(row) for row in rows]

    def list_by_statuses(
        self, statuses: set[EventRequestStatus]
    ) -> list[EventRequestResponse]:
        return sorted(
            (request for status in statuses for request in self.list_by_status(status)),
            key=lambda request: request.created_at,
            reverse=True,
        )

    def get(self, event_request_id: str, organiser_id: str) -> EventRequestResponse:
        row = self.repository.get_for_organiser(event_request_id, organiser_id)
        if row is None:
            raise EventRequestNotFoundError(event_request_id)
        return self._row_to_response(row)

    def get_by_id(self, event_request_id: str) -> EventRequestResponse:
        """Unscoped lookup for a caller who isn't the owning organiser."""
        row = self.repository.get_by_id(event_request_id)
        if row is None:
            raise EventRequestNotFoundError(event_request_id)
        return self._row_to_response(row)

    def get_by_ids(
        self, event_request_ids: list[str]
    ) -> list[EventRequestResponse]:
        rows = self.repository.get_by_ids(event_request_ids)
        return [self._row_to_response(row) for row in rows]

    def transition_status(
        self,
        event_request_id: str,
        from_status: EventRequestStatus,
        to_status: EventRequestStatus,
    ) -> EventRequestResponse:
        row = self.repository.update_status(
            event_request_id, from_status.value, to_status.value
        )
        if row is None:
            raise EventRequestTransitionConflictError(
                event_request_id, from_status.value, to_status.value
            )
        return self._row_to_response(row)

    def set_final_end(
        self, event_request_id: str, coordinator_id: str, payload: EventFinalEndUpdate
    ) -> EventRequestResponse:
        """The native setter rechecks state and assignment under the event lock."""
        row = self.repository.set_final_end(
            event_request_id, coordinator_id,
            payload.final_event_end_at.astimezone(UTC),
        )
        return self._row_to_response(row)

    def advance_by_coordinator(
        self,
        event_request_id: str,
        coordinator_id: str,
        to_status: EventRequestStatus,
    ) -> EventRequestResponse:
        """Coordinator transitions run through one database function, which
        re-checks the assignment under a row lock; the RPC errcodes stay in
        the repo layer and are mapped by the caller."""
        row = self.repository.advance_by_coordinator(
            event_request_id, coordinator_id, to_status.value
        )
        return self._row_to_response(row)

    def send_for_safety_review(
        self, event_request_id: str, coordinator_id: str
    ) -> EventRequestResponse:
        row = self.repository.send_for_safety_review(
            event_request_id, coordinator_id
        )
        return self._row_to_response(row)

    def decide_by_coordinator(
        self,
        event_request_id: str,
        coordinator_id: str,
        decision: EventRequestStatus,
        reason: str | None,
    ) -> EventRequestResponse:
        row = self.repository.decide_by_coordinator(
            event_request_id,
            coordinator_id,
            decision.value,
            reason,
        )
        return self._row_to_response(row)

    def resume_review_by_coordinator(
        self, event_request_id: str, coordinator_id: str
    ) -> EventRequestResponse:
        row = self.repository.resume_review_by_coordinator(
            event_request_id, coordinator_id
        )
        return self._row_to_response(row)

    def list_review_decisions(
        self, event_request_id: str
    ) -> list[EventReviewDecisionResponse]:
        rows = self.repository.list_review_decisions(event_request_id)
        return [EventReviewDecisionResponse.model_validate(row) for row in rows]

    def decide_safety_review(
        self, event_request_id: str, officer_id: str, payload: SafetyDecision
    ) -> EventRequestResponse:
        row = self.repository.decide_safety_review(
            event_request_id,
            officer_id,
            payload.decision,
            payload.reason,
            [target.model_dump(mode="json") for target in payload.targets],
        )
        return self._row_to_response(row)

    def list_safety_reviews(self, event_request_id: str) -> list[SafetyReviewResponse]:
        rows = self.repository.list_safety_reviews(event_request_id)
        return [SafetyReviewResponse.model_validate(row) for row in rows]

    def latest_coordinator_id(self, event_request_id: str) -> str | None:
        return self.repository.latest_coordinator_id(event_request_id)

    def create_change_request(
        self,
        event_request_id: str,
        organiser_id: str,
        payload: EventChangeRequestCreate,
    ) -> EventChangeRequestResponse:
        try:
            row = self.repository.create_change_request(
                event_request_id,
                organiser_id,
                payload.explanation,
                payload.proposed_changes(),
            )
        except EventRequestRpcError as error:
            self._raise_change_request_error(error, event_request_id)
        return EventChangeRequestResponse.model_validate(row)

    def list_change_requests(
        self, event_request_id: str
    ) -> list[EventChangeRequestResponse]:
        return [
            EventChangeRequestResponse.model_validate(row)
            for row in self.repository.list_change_requests(event_request_id)
        ]

    def plan_change_request_dates(
        self, event_request_id: str, change_request_id: str,
    ) -> EventChangeDatePlanResponse | None:
        """Read a complete advisory snapshot without locking or changing state."""
        try:
            event = self.get_by_id(event_request_id)
            row = self.repository.get_change_request(event_request_id, change_request_id)
            if row is None:
                return None
            change = EventChangeRequestResponse.model_validate(row)
            if change.id != change_request_id or change.event_request_id != event_request_id:
                return None
            if (
                event.status not in CHANGEABLE_STATUSES
                or change.status != EventChangeRequestStatus.PENDING
            ):
                raise EventChangeDatePlanConflictError("date_plan_unavailable")
            if set(change.proposed_changes) != {"proposed_date_times"}:
                raise EventChangeDatePlanConflictError("unsupported_date_mapping")
            if event.updated_at.utcoffset() is None or change.base_event_updated_at.utcoffset() is None:
                raise ValueError("Stored event versions must be timezone-aware")
            if event.updated_at.astimezone(UTC) != change.base_event_updated_at.astimezone(UTC):
                raise EventChangeDatePlanConflictError("change_request_stale")

            bookings = self.repository.list_event_venue_bookings(event_request_id)
            candidates = plan_date_only_reschedule(
                [value.isoformat() for value in event.proposed_date_times],
                change.proposed_changes["proposed_date_times"],
                bookings,
            )
            current = {booking["id"]: booking for booking in bookings}
            return EventChangeDatePlanResponse(
                event_request_id=event_request_id,
                change_request_id=change_request_id,
                bookings=[
                    EventChangeDatePlanBooking(
                        booking_id=candidate["id"],
                        venue_id=candidate["venue_id"],
                        status=candidate["status"],
                        current_start_date=current[candidate["id"]]["start_date"],
                        current_end_date=current[candidate["id"]]["end_date"],
                        proposed_start_date=candidate["start_date"],
                        proposed_end_date=candidate["end_date"],
                        start_minute=candidate["start_minute"],
                        end_minute=candidate["end_minute"],
                    )
                    for candidate in candidates
                ],
            )
        except DateReschedulePlanError as error:
            raise EventChangeDatePlanConflictError(error.code) from error
        except (
            SupabaseRepositoryError, ValidationError, ValueError, TypeError,
            KeyError, AttributeError, OverflowError,
        ) as error:
            raise SupabaseRepositoryError("Date change plan unavailable") from error

    def get_change_booking_context(
        self, event_request_id: str, change_request_id: str,
    ) -> EventChangeBookingContext | None:
        """Complete advisory editor input; authoritative mutation checks happen later."""
        try:
            event = self.get_by_id(event_request_id)
            row = self.repository.get_change_request(event_request_id, change_request_id)
            if row is None:
                return None
            change = EventChangeRequestResponse.model_validate(row)
            if change.id != change_request_id or change.event_request_id != event_request_id:
                return None
            if event.status not in CHANGEABLE_STATUSES or change.status != EventChangeRequestStatus.PENDING:
                raise EventChangeDatePlanConflictError("date_plan_unavailable")
            fields = set(change.proposed_changes)
            if "proposed_date_times" not in fields or not fields <= {
                "proposed_date_times", "expected_attendance", "venue_requirements",
                "equipment_requirements", "registration_needs", "accessibility_needs",
            }:
                raise EventChangeDatePlanConflictError("unsupported_date_mapping")
            if event.updated_at.utcoffset() is None or change.base_event_updated_at.utcoffset() is None:
                raise ValueError("Stored event versions must be aware")
            if event.updated_at.astimezone(UTC) != change.base_event_updated_at.astimezone(UTC):
                raise EventChangeDatePlanConflictError("change_request_stale")
            proposed = EventChangeRequestCreate(explanation=change.explanation, **change.proposed_changes)
            if proposed.proposed_date_times == event.proposed_date_times:
                raise EventChangeDatePlanConflictError("no_op_date_mapping")
            rows = self.repository.list_event_venue_bookings(event_request_id)
            bookings = [EventChangeBookingContextItem(
                booking_id=booking["id"], venue_id=booking["venue_id"], status=booking["status"],
                start_date=booking["start_date"], end_date=booking["end_date"],
                start_minute=booking["start_minute"], end_minute=booking["end_minute"],
            ) for booking in rows if booking["status"] in {"pending", "approved"}]
            result = EventChangeBookingContext(
                event_request_id=event_request_id, change_request_id=change_request_id,
                event_updated_at=event.updated_at, bookings=bookings,
            )
            try:
                candidates = plan_date_only_reschedule(
                    [value.isoformat() for value in event.proposed_date_times],
                    change.proposed_changes["proposed_date_times"], rows,
                )
                result.automatic_plan = [EventChangeBookingPlanItem(
                    booking_id=booking["id"], start_date=booking["start_date"], end_date=booking["end_date"],
                    start_minute=booking["start_minute"], end_minute=booking["end_minute"],
                ) for booking in candidates]
            except DateReschedulePlanError as error:
                result.automatic_plan_error = error.code
            return result
        except (SupabaseRepositoryError, ValidationError, ValueError, TypeError, KeyError, AttributeError, OverflowError) as error:
            raise SupabaseRepositoryError("Date change plan unavailable") from error

    def _status_before_change(self, event_request_id: str) -> str | None:
        """Best effort: only used to notice an event leaving Confirmed."""
        try:
            row = self.repository.get_by_id(event_request_id)
        except SupabaseRepositoryError:
            return None
        return row.get("status") if row else None

    def _notify_if_no_longer_confirmed(
        self, event_request_id: str, status_before: str | None
    ) -> None:
        """A saved change that flagged arrangements returned a Confirmed event to
        Planning (0071), so the Organiser is told (Q&A #105). Never fails the change."""
        if status_before != EventRequestStatus.CONFIRMED.value:
            return
        try:
            row = self.repository.get_by_id(event_request_id)
        except SupabaseRepositoryError:
            logger.warning(
                "Could not reread event request %s to see if it left Confirmed",
                event_request_id,
                exc_info=True,
            )
            return
        if row is None or row.get("status") != EventRequestStatus.PLANNING.value:
            return
        self.notification_client.notify_event_no_longer_confirmed(
            event_request_id=event_request_id,
            event_name=row.get("event_name"),
            organiser_id=row["organiser_id"],
            version=str(row.get("updated_at")),
        )

    def update_by_coordinator(
        self, event_request_id: str, coordinator_id: str, payload: EventDetailsUpdate
    ) -> EventRequestResponse:
        """Hotfix 8: the database checks assignment, status and version under the
        event lock, and its triggers flag arrangements for significant changes."""
        changes = payload.model_dump(
            mode="json", exclude_unset=True, exclude={"expected_updated_at"}
        )
        before = None
        try:
            before = self.repository.get_by_id(event_request_id)
        except SupabaseRepositoryError:
            logger.warning("Could not read event request %s first", event_request_id, exc_info=True)
        status_before = before.get("status") if before else None
        try:
            row = self.repository.update_by_coordinator(
                event_request_id,
                coordinator_id,
                payload.expected_updated_at.isoformat(),
                changes,
            )
        except EventRequestRpcError as error:
            if error.errcode == "P0002":
                raise EventRequestNotFoundError(event_request_id) from error
            if error.errcode == "P0003":
                raise EventRequestForbiddenError(event_request_id) from error
            if error.errcode == "P0004":
                raise EventDetailsConflictError(event_request_id) from error
            raise
        response = self._row_to_response(row)
        self._notify_if_no_longer_confirmed(event_request_id, status_before)
        if (
            before is not None
            and "proposed_date_times" in changes
            and row.get("proposed_date_times") != before.get("proposed_date_times")
        ):
            attendee_ids = self._registered_attendee_ids(event_request_id)
            if attendee_ids:
                self.notification_client.notify_event_changed(
                    event_request_id=event_request_id,
                    event_name=row.get("event_name"),
                    change_request_id=f"coordinator-edit:{row.get('updated_at')}",
                    proposed_date_times=changes["proposed_date_times"],
                    attendee_ids=attendee_ids,
                )
        return response

    def get_arrangements(self, event_request_id: str) -> dict[str, list[dict[str, Any]]]:
        return self.repository.get_event_arrangements(event_request_id)

    def decide_change_request(
        self,
        event_request_id: str,
        change_request_id: str,
        coordinator_id: str,
        payload: EventChangeDecision,
    ) -> EventChangeRequestResponse:
        """Save rejection or the supported non-date approval transaction.

        Database functions own current-state checks and atomic plan application.
        """
        status_before = self._status_before_change(event_request_id)
        try:
            row = self.repository.decide_change_request(
                event_request_id,
                change_request_id,
                coordinator_id,
                payload.decision.value,
                payload.reason,
            )
        except EventRequestRpcError as error:
            self._raise_change_request_error(error, event_request_id)
        saved = self._saved_change_decision(
            row, event_request_id, change_request_id, coordinator_id, payload,
        )
        self._notify_if_no_longer_confirmed(event_request_id, status_before)
        return saved

    def approve_date_change_request(
        self, event_request_id: str, change_request_id: str, coordinator_id: str,
        payload: EventChangeDecision,
    ) -> EventChangeRequestResponse:
        """SQL owns complete membership, conflict checks and the atomic write."""
        plan = None if payload.booking_plan is None else [
            booking.model_dump(mode="json") for booking in payload.booking_plan
        ]
        status_before = self._status_before_change(event_request_id)
        try:
            row = self.repository.approve_date_change_request(
                event_request_id, change_request_id, coordinator_id, payload.reason, plan,
            )
        except EventRequestRpcError as error:
            if error.errcode == "P0005":
                try:
                    facts = json.loads(error.details)
                    if not isinstance(facts, list) or not facts:
                        raise ValueError("Missing conflict facts")
                    bookings = [EventChangeBookingConflict.model_validate(item) for item in facts]
                except (ValueError, TypeError, ValidationError) as invalid:
                    raise SupabaseRepositoryError("Event change decision unavailable") from invalid
                raise EventChangeBookingConflictError(bookings) from error
            if error.errcode == "22023":
                raise EventChangeBookingPlanError("Booking plan is invalid; refresh and check every current booking range.") from error
            if error.errcode not in {"P0002", "P0003", "P0004"}:
                raise SupabaseRepositoryError("Event change decision unavailable") from error
            self._raise_change_request_error(error, event_request_id)
        except SupabaseRepositoryError as error:
            raise SupabaseRepositoryError("Event change decision unavailable") from error
        saved = self._saved_change_decision(
            row, event_request_id, change_request_id, coordinator_id, payload,
            require_booking_plan=True,
        )
        self._notify_if_no_longer_confirmed(event_request_id, status_before)
        return saved

    def partially_approve_change_request(
        self, event_request_id: str, change_request_id: str, coordinator_id: str,
        payload: EventChangeDecision,
    ) -> EventChangeRequestResponse:
        """Hotfix 20 (Q&A #104): apply the accepted fields, refuse the rest with reasons.

        The database narrows the request and runs the ordinary approval in one
        transaction, so a refusal leaves the request exactly as it was."""
        plan = None if payload.booking_plan is None else [
            booking.model_dump(mode="json") for booking in payload.booking_plan
        ]
        status_before = self._status_before_change(event_request_id)
        try:
            row = self.repository.partially_approve_change_request(
                event_request_id, change_request_id, coordinator_id,
                list(payload.accepted_fields or []), dict(payload.rejected_reasons or {}),
                payload.reason, plan,
            )
        except EventRequestRpcError as error:
            if error.errcode == "P0005":
                try:
                    facts = json.loads(error.details)
                    if not isinstance(facts, list) or not facts:
                        raise ValueError("Missing conflict facts")
                    bookings = [EventChangeBookingConflict.model_validate(item) for item in facts]
                except (ValueError, TypeError, ValidationError) as invalid:
                    raise SupabaseRepositoryError("Event change decision unavailable") from invalid
                raise EventChangeBookingConflictError(bookings) from error
            if error.errcode == "22023":
                raise EventChangeSelectionError(
                    "Choose at least one field to accept and at least one to refuse, give a "
                    "reason for every refused field, and give a complete booking plan when the "
                    "dates are accepted."
                ) from error
            if error.errcode not in {"P0002", "P0003", "P0004"}:
                raise SupabaseRepositoryError("Event change decision unavailable") from error
            self._raise_change_request_error(error, event_request_id)
        try:
            change = EventChangeRequestResponse.model_validate(row)
        except ValidationError as error:
            raise SupabaseRepositoryError("Event change decision unavailable") from error
        if (
            change.status != EventChangeRequestStatus.PARTIALLY_APPROVED
            or change.id != change_request_id
            or change.event_request_id != event_request_id
            or change.decided_at is None
        ):
            raise SupabaseRepositoryError("Event change decision unavailable")
        try:
            self.notification_client.notify_event_change_partly_approved(
                event_request_id=change.event_request_id,
                change_request_id=change.id,
                organiser_id=change.organiser_id,
                accepted_fields=sorted(change.proposed_changes),
                refused={
                    field: str((detail or {}).get("reason", ""))
                    for field, detail in (change.rejected_changes or {}).items()
                },
                reason=change.decision_reason,
            )
        except Exception:
            logger.warning(
                "Failed to notify organiser of partly approved change %s",
                change.id, exc_info=True,
            )
        try:
            self._notify_attendees_of_date_change(change)
        except Exception:
            logger.warning(
                "Failed to notify attendees of partly approved change %s",
                change.id, exc_info=True,
            )
        self._notify_if_no_longer_confirmed(event_request_id, status_before)
        return change

    def _registered_attendee_ids(self, event_request_id: str) -> list[str]:
        """Who to tell about an event-wide change. Never raises: the change that
        triggered the notice is already saved."""
        try:
            return self.repository.list_registered_attendee_ids(event_request_id)
        except SupabaseRepositoryError:
            logger.warning(
                "Could not list the attendees of event request %s to notify them",
                event_request_id,
                exc_info=True,
            )
            return []

    def change_organiser(
        self, event_request_id: str, coordinator_id: str, organiser_email: str, reason: str
    ) -> tuple[str | None, EventRequestResponse]:
        """Hotfix 24: returns the previous Organiser's id (read just before) and the event."""
        try:
            previous = self.repository.get_by_id(event_request_id)
        except SupabaseRepositoryError:
            previous = None
        row = self.repository.change_organiser(
            event_request_id, coordinator_id, organiser_email, reason
        )
        return (previous or {}).get("organiser_id"), self._row_to_response(row)

    def postpone_by_coordinator(
        self, event_request_id: str, coordinator_id: str, reason: str
    ) -> EventRequestResponse:
        """Hotfix 22 (Q&A #69, #121): release the arrangements and keep the record."""
        return self._row_to_response(
            self.repository.postpone_by_coordinator(event_request_id, coordinator_id, reason)
        )

    def resume_postponed(
        self, event_request_id: str, coordinator_id: str, new_date_times: list[str]
    ) -> EventRequestResponse:
        return self._row_to_response(
            self.repository.resume_postponed(event_request_id, coordinator_id, new_date_times)
        )

    def _people_told_about_postponement(
        self, event_request: EventRequestResponse, *, released_reason: str | None
    ) -> list[str]:
        """The Organiser, every registered Attendee and (after a postponement) the staff
        whose bookings were released. Never raises: the change is already saved."""
        recipient_ids = [event_request.organiser_id]
        recipient_ids += [
            attendee_id
            for attendee_id in self._registered_attendee_ids(event_request.id)
            if attendee_id not in recipient_ids
        ]
        if released_reason is not None:
            try:
                recipient_ids += [
                    staff_id
                    for staff_id in self.repository.cancellation_staff_ids(
                        event_request.id, released_reason
                    )
                    if staff_id not in recipient_ids
                ]
            except SupabaseRepositoryError:
                logger.warning(
                    "Could not find the staff of event request %s to tell them it was postponed",
                    event_request.id,
                    exc_info=True,
                )
        return recipient_ids

    def notify_of_postponement(self, event_request: EventRequestResponse, reason: str) -> None:
        self.notification_client.notify_event_postponed(
            event_request_id=event_request.id,
            event_name=event_request.event_name,
            postponement_key=f"{event_request.id}:{event_request.updated_at.isoformat()}",
            recipient_ids=self._people_told_about_postponement(
                event_request, released_reason="Event postponed"
            ),
            reason=reason,
        )

    def notify_of_resumption(self, event_request: EventRequestResponse) -> None:
        self.notification_client.notify_event_resumed(
            event_request_id=event_request.id,
            event_name=event_request.event_name,
            resume_key=f"{event_request.id}:{event_request.updated_at.isoformat()}",
            recipient_ids=self._people_told_about_postponement(event_request, released_reason=None),
            proposed_date_times=[d.isoformat() for d in event_request.proposed_date_times],
        )

    def notify_owners_of_cancellation(self, event_request: EventRequestResponse) -> None:
        """SCRUM-57 AC1: a saved cancellation reaches the Organiser and the Coordinator."""
        recipient_ids = [event_request.organiser_id]
        try:
            # SCRUM-57 AC1b: and the staff responsible for what the cancellation released.
            recipient_ids += [
                staff_id
                for staff_id in self.repository.cancellation_staff_ids(event_request.id)
                if staff_id not in recipient_ids
            ]
        except SupabaseRepositoryError:
            logger.warning(
                "Could not find the staff of event request %s to tell them it was cancelled",
                event_request.id,
                exc_info=True,
            )
        try:
            coordinator_id = self.repository.latest_coordinator_id(event_request.id)
        except SupabaseRepositoryError:
            # The cancellation is already saved; tell the Organiser anyway.
            logger.warning(
                "Could not find the coordinator of event request %s to tell them "
                "it was cancelled",
                event_request.id,
                exc_info=True,
            )
            coordinator_id = None
        if coordinator_id is not None and coordinator_id not in recipient_ids:
            recipient_ids.append(coordinator_id)
        self.notification_client.notify_event_cancellation_recorded(
            event_request_id=event_request.id,
            event_name=event_request.event_name,
            recipient_ids=recipient_ids,
        )

    def notify_attendees_of_cancellation(self, event_request: EventRequestResponse) -> None:
        """SCRUM-38 AC4: a saved cancellation reaches every registered Attendee."""
        attendee_ids = self._registered_attendee_ids(event_request.id)
        if attendee_ids:
            self.notification_client.notify_event_cancelled(
                event_request_id=event_request.id,
                event_name=event_request.event_name,
                attendee_ids=attendee_ids,
            )

    def _notify_attendees_of_date_change(self, change: EventChangeRequestResponse) -> None:
        """SCRUM-38 AC4: an approved change to the dates reaches every registered
        Attendee. Attendees see only the dates of a change, so any other approved
        change (attendance, venue, equipment) tells them nothing."""
        new_dates = change.proposed_changes.get("proposed_date_times")
        if not new_dates:
            return
        attendee_ids = self._registered_attendee_ids(change.event_request_id)
        if not attendee_ids:
            return
        event = self.repository.get_by_id(change.event_request_id) or {}
        self.notification_client.notify_event_changed(
            event_request_id=change.event_request_id,
            event_name=event.get("event_name"),
            change_request_id=change.id,
            proposed_date_times=new_dates,
            attendee_ids=attendee_ids,
        )

    def _saved_change_decision(
        self, row: dict[str, Any], event_request_id: str, change_request_id: str,
        coordinator_id: str, payload: EventChangeDecision, *, require_booking_plan: bool = False,
    ) -> EventChangeRequestResponse:
        """Validate the saved outcome before any best-effort organiser notice."""
        try:
            change = EventChangeRequestResponse.model_validate(row)
        except ValidationError as error:
            if payload.decision == EventChangeRequestStatus.APPROVED:
                raise SupabaseRepositoryError("Event change decision unavailable") from error
            raise
        if payload.decision == EventChangeRequestStatus.APPROVED:
            # A malformed upstream outcome is not proof of a saved approval.
            # Do not reread after commit or announce a Pending/incomplete result.
            if (
                change.status != EventChangeRequestStatus.APPROVED
                or change.id != change_request_id
                or change.event_request_id != event_request_id
                or change.coordinator_id != coordinator_id
                or change.decided_at is None
                or change.decided_at.utcoffset() is None
                or (require_booking_plan and change.applied_booking_plan is None)
            ):
                raise SupabaseRepositoryError("Event change decision unavailable")
            try:
                self.notification_client.notify_event_change_approved(
                    event_request_id=change.event_request_id,
                    change_request_id=change.id,
                    organiser_id=change.organiser_id,
                    reason=change.decision_reason,
                )
            except Exception:
                # Delivery is an independent best-effort side effect after the
                # stored transaction. Even an unexpected sender bug cannot undo it.
                logger.warning(
                    "Failed to notify organiser of approved change %s",
                    change.id, exc_info=True,
                )
            try:
                self._notify_attendees_of_date_change(change)
            except Exception:
                logger.warning(
                    "Failed to notify attendees of approved change %s",
                    change.id, exc_info=True,
                )
        elif (
            payload.decision == EventChangeRequestStatus.REJECTED
            and change.status == EventChangeRequestStatus.REJECTED
            and change.decision_reason is not None
        ):
            # The returned stored row supplies the owner and audit. No extra
            # database read can make a committed rejection appear to have failed.
            self.notification_client.notify_event_change_rejected(
                event_request_id=change.event_request_id,
                change_request_id=change.id,
                organiser_id=change.organiser_id,
                reason=change.decision_reason,
            )
        return change

    @staticmethod
    def _raise_change_request_error(
        error: EventRequestRpcError, event_request_id: str
    ) -> NoReturn:
        if error.errcode == "P0002":
            raise EventRequestNotFoundError(event_request_id) from error
        if error.errcode == "P0003":
            raise EventChangeRequestForbiddenError(event_request_id) from error
        if error.errcode == "P0004":
            raise EventChangeRequestConflictError(event_request_id) from error
        raise error

    def update(
        self,
        event_request_id: str,
        organiser_id: str,
        payload: EventRequestUpdate,
    ) -> EventRequestResponse:
        changes = payload.model_dump(exclude_unset=True, mode="json")
        if not changes:
            return self.get(event_request_id, organiser_id)

        row = self.repository.update_for_organiser(
            event_request_id,
            organiser_id,
            changes,
        )
        if row is None:
            self._raise_not_found_or_not_draft(event_request_id, organiser_id)
        return self._row_to_response(row)

    def submit(
        self,
        event_request_id: str,
        organiser_id: str,
        payload: EventRequestSubmission,
    ) -> EventRequestResponse:
        row = self.repository.submit_for_organiser(
            event_request_id,
            organiser_id,
            payload.model_dump(mode="json"),
        )
        if row is None:
            self._raise_not_found_or_not_draft(event_request_id, organiser_id)
        return self._row_to_response(row)

    def respond_to_clarification(
        self,
        event_request_id: str,
        organiser_id: str,
        payload: EventClarificationResponse,
    ) -> EventReviewDecisionResponse:
        try:
            row = self.repository.respond_to_clarification(
                event_request_id, organiser_id, payload.response
            )
        except EventRequestRpcError as error:
            if error.errcode == "P0002":
                raise self._refusal(event_request_id, organiser_id) from error
            if error.errcode == "P0004":
                raise ClarificationResponseNotAllowedError(event_request_id) from error
            raise
        return EventReviewDecisionResponse.model_validate(row)

    def delete(self, event_request_id: str, organiser_id: str) -> None:
        deleted = self.repository.delete_for_organiser(event_request_id, organiser_id)
        if not deleted:
            self._raise_not_found_or_not_draft(event_request_id, organiser_id)

    def _raise_not_found_or_not_draft(
        self, event_request_id: str, organiser_id: str
    ) -> NoReturn:
        row = self.repository.get_for_organiser(event_request_id, organiser_id)
        if row is None:
            raise self._refusal(event_request_id, organiser_id)
        raise EventRequestNotDraftError(event_request_id)

    @staticmethod
    def _row_to_response(row: dict[str, Any]) -> EventRequestResponse:
        return EventRequestResponse.model_validate(row)
