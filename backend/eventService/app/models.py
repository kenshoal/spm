"""SQLAlchemy models.

`EventRequestRef` is a **read-only mirror** of eventRequestService's
`event_requests` table — owned and migrated by that service, not this one.
It declares only the columns this service actually reads (id, status).
Never used to create or alter that table: app/init_db.py explicitly
restricts table creation to this service's own table, and SQLAlchemy's
default `create_all(checkfirst=True)` would skip an existing table anyway,
but the restriction keeps that safe regardless.

`EventCoordinatorAssignment` is this service's own table: which Coordinator
is assigned to an event request, and by whom. One row per assignment, not
just the current one — reassigning inserts a new row rather than
overwriting, so who was assigned before is never lost. "Current assignment"
= the most recent row for a given event_request_id, determined by `id`
(autoincrementing, so monotonic by construction) rather than `assigned_at`
— a server-clock timestamp doesn't have reliable enough resolution to
order two assignments made in quick succession.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class EventRequestRef(Base):
    __tablename__ = "event_requests"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    status: Mapped[str] = mapped_column(String(30))


class EventCoordinatorAssignment(Base):
    __tablename__ = "event_coordinator_assignments"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    event_request_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("event_requests.id"), index=True
    )
    coordinator_id: Mapped[str] = mapped_column(String(64))
    assigned_by: Mapped[str] = mapped_column(String(64))
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
