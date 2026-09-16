"""Shared test fixtures: an app wired to an in-memory SQLite database.

Uses a StaticPool so the same in-memory DB survives across connections,
letting tests run without a live Postgres instance — matching CI, which
doesn't start one.

`event_requests` is eventRequestService's table, not ours (see
app/models.py — EventRequestRef is a read-only mirror). Tests still need
rows in it to assign a Coordinator against, so `seed_event_request` inserts
one directly, standing in for what eventRequestService would have created.
"""

import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.models import EventRequestRef

OPERATIONS_MANAGER = {"X-User-Id": "ops-1", "X-User-Role": "operations_manager"}
COORDINATOR = {"X-User-Id": "coord-1", "X-User-Role": "event_coordinator"}
OTHER_COORDINATOR = {"X-User-Id": "coord-2", "X-User-Role": "event_coordinator"}
ORGANISER = {"X-User-Id": "org-1", "X-User-Role": "organiser"}


@pytest.fixture
def session_factory() -> Iterator[sessionmaker]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    testing_session_local = sessionmaker(bind=engine)

    def override_get_db() -> Iterator:
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield testing_session_local
    app.dependency_overrides.clear()


@pytest.fixture
def client(session_factory: sessionmaker) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


def seed_event_request(
    session_factory: sessionmaker, status: str = "Submitted"
) -> uuid.UUID:
    """Insert a stand-in event_requests row, as if eventRequestService had
    created it. Returns its id."""
    event_request_id = uuid.uuid4()
    with session_factory() as db:
        db.add(EventRequestRef(id=event_request_id, status=status))
        db.commit()
    return event_request_id
