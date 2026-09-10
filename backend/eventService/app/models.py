"""SQLAlchemy models.

Kept separate from schemas.py (API request/response shapes) so persistence
and the wire format can change independently.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.status import EventStatus


def _new_id() -> str:
    return str(uuid.uuid4())


class Event(Base):
    __tablename__ = "events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    title: Mapped[str] = mapped_column(String(200))
    status: Mapped[EventStatus] = mapped_column(
        SAEnum(EventStatus, native_enum=False, length=30),
        default=EventStatus.DRAFT,
    )
    organiser_id: Mapped[str] = mapped_column(String(64))
    coordinator_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    history: Mapped[list["StatusHistory"]] = relationship(
        back_populates="event", cascade="all, delete-orphan"
    )


class StatusHistory(Base):
    """Audit trail of every status change, in support of the requirement
    that current (and by extension past) status be visible to users with
    access to the event."""

    __tablename__ = "event_status_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id"))
    from_status: Mapped[EventStatus | None] = mapped_column(
        SAEnum(EventStatus, native_enum=False, length=30), nullable=True
    )
    to_status: Mapped[EventStatus] = mapped_column(
        SAEnum(EventStatus, native_enum=False, length=30)
    )
    changed_by: Mapped[str] = mapped_column(String(64))
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    event: Mapped["Event"] = relationship(back_populates="history")
