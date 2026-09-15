"""Shared test fixtures: an app wired to an in-memory SQLite database.

Uses a StaticPool so the same in-memory DB survives across connections,
letting tests run without a live Postgres instance — matching CI, which
doesn't start one.
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app

ORGANISER = {"X-User-Id": "org-1", "X-User-Role": "organiser"}
COORDINATOR = {"X-User-Id": "coord-1", "X-User-Role": "event_coordinator"}
OTHER_COORDINATOR = {"X-User-Id": "coord-2", "X-User-Role": "event_coordinator"}
OPERATIONS_MANAGER = {"X-User-Id": "ops-1", "X-User-Role": "operations_manager"}


@pytest.fixture
def session_factory() -> Iterator[sessionmaker]:
    # SQLite has no concept of app.db's "event_service" schema, so translate
    # it away for this engine — models stay schema-qualified for Postgres
    # without the test DB needing to know about it.
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    ).execution_options(schema_translate_map={Base.metadata.schema: None})
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


def create_event(client: TestClient, headers: dict[str, str] = ORGANISER) -> str:
    response = client.post("/events", json={"title": "Orientation"}, headers=headers)
    assert response.status_code == 201
    return response.json()["id"]
