"""Registration persistence through Supabase's Data API (SCRUM-21)."""

from datetime import UTC, datetime
from typing import Any, Protocol

import httpx

from app.config import Settings
from app.repositories.event_request_repository import SupabaseRepositoryError

# Only what the public view needs: internal planning columns are never fetched.
EVENT_COLUMNS = (
    "id,status,event_name,purpose,description,proposed_date_times,"
    "registration_opens_at,registration_closes_at,registration_capacity"
)
# The Data API's default max-rows; list_for_event pages past it.
PAGE_SIZE = 1000

REGISTRATION_COLUMNS = "id,event_request_id,attendee_id,status,created_at,withdrawn_at"


class RegistrationRpcError(SupabaseRepositoryError):
    """`register_for_event` or `withdraw_registration` refused the call.

    errcode is the Postgres ERRCODE (P0002 event not found, P0004 refused) and
    reason the function's message ('registration not open', 'already registered',
    'event full', and for `withdraw_registration` 'registration not found',
    'already withdrawn', 'withdrawal not permitted'), so callers never parse prose written for people.
    """

    def __init__(
        self, message: str, errcode: str | None = None, reason: str | None = None
    ) -> None:
        super().__init__(message)
        self.errcode = errcode
        self.reason = reason


class RegistrationRepository(Protocol):
    def get_event(self, event_id: str) -> dict[str, Any] | None: ...

    def get_events(self, event_ids: list[str]) -> list[dict[str, Any]]: ...

    def get_organiser_id(self, event_id: str) -> str | None: ...

    def latest_coordinator_id(self, event_id: str) -> str | None: ...

    def list_confirmed_events(self) -> list[dict[str, Any]]: ...

    def count_active(self, event_id: str) -> int: ...

    def count_active_for_events(self, event_ids: list[str]) -> dict[str, int]: ...

    def places_taken(self, event_id: str) -> int: ...

    def has_active(self, event_id: str, attendee_id: str) -> bool: ...

    def list_for_attendee(self, attendee_id: str) -> list[dict[str, Any]]: ...

    def get_event_access(self, event_id: str) -> dict[str, Any] | None: ...

    def list_for_event(self, event_id: str) -> list[dict[str, Any]]: ...

    def register(
        self, event_id: str, attendee_id: str, now: datetime
    ) -> dict[str, Any]: ...

    def coordinator_register(
        self, event_id: str, coordinator_id: str, attendee_email: str
    ) -> dict[str, Any]: ...

    def get_registration(self, registration_id: str) -> dict[str, Any] | None: ...

    def withdraw(
        self, registration_id: str, attendee_id: str, now: datetime
    ) -> dict[str, Any]: ...

    def check_in(
        self, event_id: str, registration_id: str, coordinator_id: str, now: datetime
    ) -> dict[str, Any]: ...


class SupabaseRegistrationRepository:
    def __init__(
        self,
        supabase_url: str,
        secret_key: str,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        headers = {"apikey": secret_key}
        # Legacy service-role keys are JWTs; new sb_secret keys use apikey only.
        if not secret_key.startswith("sb_secret_"):
            headers["Authorization"] = f"Bearer {secret_key}"
        self._client = httpx.Client(
            base_url=f"{supabase_url.rstrip('/')}/rest/v1",
            headers=headers,
            timeout=10,
            transport=transport,
        )

    @classmethod
    def from_settings(cls, settings: Settings) -> "SupabaseRegistrationRepository":
        return cls(
            str(settings.supabase_url),
            settings.supabase_secret_key.get_secret_value(),
        )

    def get_event(self, event_id: str) -> dict[str, Any] | None:
        rows = self._get(
            "/event_requests", {"select": EVENT_COLUMNS, "id": f"eq.{event_id}"}
        )
        return rows[0] if rows else None

    def list_window_boundaries(
        self, *, since: datetime, until: datetime, after_id: str | None, limit: int
    ) -> list[dict[str, Any]]:
        """Confirmed events whose opening or closing time falls in [since, until].

        One page, oldest id first. Only what the notice needs is selected
        (SCRUM-38 AC3), never the internal planning columns.
        """
        def stamp(moment: datetime) -> str:
            return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")

        low, high = stamp(since), stamp(until)
        params = {
            "select": "id,event_name,organiser_id,registration_opens_at,registration_closes_at",
            "status": "eq.Confirmed",
            "or": (
                f"(and(registration_opens_at.gte.{low},registration_opens_at.lte.{high}),"
                f"and(registration_closes_at.gte.{low},registration_closes_at.lte.{high}))"
            ),
            "order": "id.asc",
            "limit": str(limit),
        }
        if after_id is not None:
            params["id"] = f"gt.{after_id}"
        return self._get("/event_requests", params)

    def get_organiser_id(self, event_id: str) -> str | None:
        """Who to tell about the event (SCRUM-38); fetched alone, never publicly."""
        rows = self._get(
            "/event_requests", {"select": "organiser_id", "id": f"eq.{event_id}"}
        )
        return rows[0]["organiser_id"] if rows else None

    def latest_coordinator_id(self, event_id: str) -> str | None:
        """The newest assignment row names the current Coordinator (as SCRUM-60)."""
        rows = self._get(
            "/event_coordinator_assignments",
            {
                "event_request_id": f"eq.{event_id}",
                "order": "id.desc",
                "limit": "1",
                "select": "coordinator_id",
            },
        )
        return rows[0]["coordinator_id"] if rows else None

    def get_events(self, event_ids: list[str]) -> list[dict[str, Any]]:
        if not event_ids:
            return []
        return self._get(
            "/event_requests",
            {"select": EVENT_COLUMNS, "id": f"in.({','.join(event_ids)})"},
        )

    def list_confirmed_events(self) -> list[dict[str, Any]]:
        return self._get(
            "/event_requests",
            {
                "select": EVENT_COLUMNS,
                "status": "eq.Confirmed",
                "order": "registration_opens_at.asc.nullslast",
            },
        )

    def count_active(self, event_id: str) -> int:
        return self.count_active_for_events([event_id]).get(event_id, 0)

    def count_active_for_events(self, event_ids: list[str]) -> dict[str, int]:
        # One exact-count request per event: the Data API caps a page at 1,000
        # rows, so counting fetched rows would undercount a large event.
        counts = {event_id: 0 for event_id in event_ids}
        for event_id in event_ids:
            counts[event_id] = self._count_active(event_id)
        return counts

    def places_taken(self, event_id: str) -> int:
        """D6 (SCRUM-24): pending offers hold capacity like registrations.

        One exact-count request per table per event, as above.
        """
        return self._count_active(event_id) + self._count_offered(event_id)

    def _count_active(self, event_id: str) -> int:
        return self._exact_count(
            "/event_registrations",
            {"status": "eq.Registered", "event_request_id": f"eq.{event_id}"},
        )

    def _count_offered(self, event_id: str) -> int:
        return self._exact_count(
            "/event_waitlist_entries",
            {"status": "eq.Offered", "event_request_id": f"eq.{event_id}"},
        )

    def _exact_count(self, path: str, filters: dict[str, str]) -> int:
        try:
            response = self._client.head(
                path, params=filters, headers={"Prefer": "count=exact"}
            )
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise SupabaseRepositoryError(
                "Supabase could not complete the registration lookup"
            ) from error
        # Content-Range "*/42": PostgREST reports the matched total when
        # count=exact is requested, with no row payload to page through.
        total = response.headers.get("content-range", "").rpartition("/")[2]
        return int(total) if total.isdigit() else 0

    def has_active(self, event_id: str, attendee_id: str) -> bool:
        rows = self._get(
            "/event_registrations",
            {
                "select": "id",
                "status": "eq.Registered",
                "event_request_id": f"eq.{event_id}",
                "attendee_id": f"eq.{attendee_id}",
                "limit": "1",
            },
        )
        return bool(rows)

    def list_for_attendee(self, attendee_id: str) -> list[dict[str, Any]]:
        return self._get(
            "/event_registrations",
            {
                "select": REGISTRATION_COLUMNS,
                "attendee_id": f"eq.{attendee_id}",
                "order": "created_at.desc",
            },
        )

    def get_event_access(self, event_id: str) -> dict[str, Any] | None:
        """Who may manage the event and its capacity (SCRUM-34)."""
        rows = self._get(
            "/event_requests",
            {"select": "id,organiser_id,registration_capacity", "id": f"eq.{event_id}"},
        )
        return rows[0] if rows else None

    def list_for_event(self, event_id: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        while True:
            page = self._get(
                "/event_registrations",
                {
                    "select": (
                        "id,attendee_id,status,created_at,registered_by,"
                        "attended_at,checked_in_by"
                    ),
                    "event_request_id": f"eq.{event_id}",
                    "order": "created_at.asc,id.asc",
                    "limit": str(PAGE_SIZE),
                    "offset": str(len(rows)),
                },
            )
            rows.extend(page)
            if len(page) < PAGE_SIZE:
                return rows

    def register(
        self, event_id: str, attendee_id: str, now: datetime
    ) -> dict[str, Any]:
        return self._rpc(
            "register_for_event",
            {
                "p_event_request_id": event_id,
                "p_attendee_id": attendee_id,
                "p_now": now.isoformat(),
            },
            action="registration",
        )

    def get_registration(self, registration_id: str) -> dict[str, Any] | None:
        rows = self._get(
            "/event_registrations",
            {"select": REGISTRATION_COLUMNS, "id": f"eq.{registration_id}"},
        )
        return rows[0] if rows else None

    def withdraw(
        self, registration_id: str, attendee_id: str, now: datetime
    ) -> dict[str, Any]:
        return self._rpc(
            "withdraw_registration",
            {
                "p_registration_id": registration_id,
                "p_attendee_id": attendee_id,
                "p_now": now.isoformat(),
            },
            action="withdrawal",
        )

    def coordinator_register(
        self, event_id: str, coordinator_id: str, attendee_email: str
    ) -> dict[str, Any]:
        """SCRUM-41: `coordinator_register_attendee` rechecks everything under a lock."""
        return self._rpc(
            "coordinator_register_attendee",
            {
                "p_event_request_id": event_id,
                "p_coordinator_id": coordinator_id,
                "p_attendee_email": attendee_email,
            },
            action="registration",
        )

    def check_in(
        self, event_id: str, registration_id: str, coordinator_id: str, now: datetime
    ) -> dict[str, Any]:
        """SCRUM-25: `check_in_attendee` rechecks everything under a lock."""
        return self._rpc(
            "check_in_attendee",
            {
                "p_event_request_id": event_id,
                "p_registration_id": registration_id,
                "p_coordinator_id": coordinator_id,
                "p_now": now.isoformat(),
            },
            action="check-in",
        )

    def _rpc(
        self, function: str, payload: dict[str, str], action: str
    ) -> dict[str, Any]:
        try:
            response = self._client.post(
                f"/rpc/{function}",
                json=payload,
                headers={"Accept": "application/vnd.pgrst.object+json"},
            )
        except httpx.HTTPError as error:
            raise SupabaseRepositoryError(
                f"Supabase could not complete the {action}"
            ) from error
        if response.is_error:
            try:
                body = response.json()
            except ValueError:
                body = {}
            if not isinstance(body, dict):
                body = {}
            # PostgREST answers a RAISE with our P0002/P0004 SQLSTATEs as HTTP 500,
            # so a P0 code means the function refused, not that Supabase is down.
            if response.status_code >= 500 and not str(body.get("code", "")).startswith("P0"):
                raise SupabaseRepositoryError(f"Supabase could not complete the {action}")
            raise RegistrationRpcError(
                f"Supabase rejected the {action}",
                errcode=body.get("code"),
                reason=body.get("message"),
            )
        return response.json()

    def _get(self, path: str, params: dict[str, str]) -> list[dict[str, Any]]:
        try:
            response = self._client.get(path, params=params)
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise SupabaseRepositoryError(
                "Supabase could not complete the registration lookup"
            ) from error
        return response.json()

    def close(self) -> None:
        self._client.close()
