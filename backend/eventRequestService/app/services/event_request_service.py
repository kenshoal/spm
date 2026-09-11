import json
import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.models.event_request import (
    EventRequestCreate,
    EventRequestResponse,
    EventRequestStatus,
    EventRequestUpdate,
)


class EventRequestNotFoundError(Exception):
    def __init__(self, event_request_id: str) -> None:
        super().__init__(f"Event request {event_request_id} was not found")
        self.event_request_id = event_request_id


class EventRequestService:
    """Owns draft CRUD rules and SQLite persistence."""

    editable_fields = (
        "event_name",
        "purpose",
        "description",
        "proposed_date_times",
        "expected_attendance",
        "venue_requirements",
        "accessibility_needs",
        "equipment_requirements",
        "registration_needs",
    )

    def __init__(self, database_path: str | Path | None = None) -> None:
        default_path = Path(__file__).resolve().parents[2] / "db.sqlite3"
        self.database_path = Path(
            database_path or os.environ.get("EVENT_REQUEST_DB_PATH", default_path)
        )
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialise_database()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialise_database(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS event_requests (
                    id TEXT PRIMARY KEY,
                    organiser_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    event_name TEXT,
                    purpose TEXT,
                    description TEXT,
                    proposed_date_times TEXT NOT NULL DEFAULT '[]',
                    expected_attendance INTEGER,
                    venue_requirements TEXT,
                    accessibility_needs TEXT,
                    equipment_requirements TEXT,
                    registration_needs TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_event_requests_organiser_status
                ON event_requests (organiser_id, status)
                """
            )

    def create(
        self, payload: EventRequestCreate, organiser_id: str
    ) -> EventRequestResponse:
        now = datetime.now(UTC)
        event_request_id = str(uuid4())
        values = payload.model_dump()

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO event_requests (
                    id, organiser_id, status, event_name, purpose, description,
                    proposed_date_times, expected_attendance, venue_requirements,
                    accessibility_needs, equipment_requirements, registration_needs,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_request_id,
                    organiser_id,
                    EventRequestStatus.DRAFT.value,
                    values["event_name"],
                    values["purpose"],
                    values["description"],
                    self._encode_date_times(values["proposed_date_times"]),
                    values["expected_attendance"],
                    values["venue_requirements"],
                    values["accessibility_needs"],
                    values["equipment_requirements"],
                    values["registration_needs"],
                    now.isoformat(),
                    now.isoformat(),
                ),
            )

        return self.get(event_request_id, organiser_id)

    def list_for_organiser(self, organiser_id: str) -> list[EventRequestResponse]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM event_requests
                WHERE organiser_id = ?
                ORDER BY created_at DESC
                """,
                (organiser_id,),
            ).fetchall()
        return [self._row_to_response(row) for row in rows]

    def get(self, event_request_id: str, organiser_id: str) -> EventRequestResponse:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM event_requests
                WHERE id = ? AND organiser_id = ?
                """,
                (event_request_id, organiser_id),
            ).fetchone()

        if row is None:
            raise EventRequestNotFoundError(event_request_id)
        return self._row_to_response(row)

    def update(
        self,
        event_request_id: str,
        organiser_id: str,
        payload: EventRequestUpdate,
    ) -> EventRequestResponse:
        self.get(event_request_id, organiser_id)
        changes = payload.model_dump(exclude_unset=True)
        if not changes:
            return self.get(event_request_id, organiser_id)

        assignments: list[str] = []
        values: list[object] = []
        for field in self.editable_fields:
            if field not in changes:
                continue
            assignments.append(f"{field} = ?")
            value = changes[field]
            if field == "proposed_date_times":
                value = self._encode_date_times(value or [])
            values.append(value)

        assignments.append("updated_at = ?")
        values.append(datetime.now(UTC).isoformat())
        values.extend((event_request_id, organiser_id))

        with self._connect() as connection:
            connection.execute(
                f"""
                UPDATE event_requests
                SET {', '.join(assignments)}
                WHERE id = ? AND organiser_id = ?
                """,
                values,
            )

        return self.get(event_request_id, organiser_id)

    def delete(self, event_request_id: str, organiser_id: str) -> None:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                DELETE FROM event_requests
                WHERE id = ? AND organiser_id = ?
                """,
                (event_request_id, organiser_id),
            )
        if cursor.rowcount == 0:
            raise EventRequestNotFoundError(event_request_id)

    @staticmethod
    def _encode_date_times(values: list[datetime]) -> str:
        return json.dumps([value.isoformat() for value in values])

    @staticmethod
    def _row_to_response(row: sqlite3.Row) -> EventRequestResponse:
        return EventRequestResponse(
            id=row["id"],
            organiser_id=row["organiser_id"],
            status=EventRequestStatus(row["status"]),
            event_name=row["event_name"],
            purpose=row["purpose"],
            description=row["description"],
            proposed_date_times=[
                datetime.fromisoformat(value)
                for value in json.loads(row["proposed_date_times"])
            ],
            expected_attendance=row["expected_attendance"],
            venue_requirements=row["venue_requirements"],
            accessibility_needs=row["accessibility_needs"],
            equipment_requirements=row["equipment_requirements"],
            registration_needs=row["registration_needs"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )
