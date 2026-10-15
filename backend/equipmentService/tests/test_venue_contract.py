"""Cross-service regression for SCRUM-13 D11 (AC1-X4, AC1-X6, AC1-X7).

equipmentService runs in-process (TestClient; Supabase is ReservationStore).
venueService runs for real in a subprocess with in-memory storage. A tiny
fake authService serves /auth/me to BOTH services over real HTTP, so the
roles venueService enforces are the ones equipmentService forwarded.

The venue stubs elsewhere in this suite answer whatever the caller's role
(F2), which is how F1 (venueService refusing Technical Support) reached a
merged branch. Nothing here stubs ``httpx.get``: that is the point.

Case IDs trace to docs/testcases/scrum_13_testcases.md.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from reservations_support import PH10, PS10, REQ1, TSS, ReservationStore

from app.config import get_settings
from app.db import get_client
from app.main import app

pytestmark = pytest.mark.cross_service

VENUE_DIR = Path(__file__).resolve().parents[2] / "venueService"
USERS = {
    "staff-token": {
        "id": TSS,
        "role": "technical_support",
        "roles": ["technical_support"],
    },
    "venue-token": {
        "id": "44444444-4444-4444-4444-444444444444",
        "role": "venue_staff",
        "roles": ["venue_staff"],
    },
}
STAFF = {"Authorization": "Bearer staff-token"}
VENUE_STAFF = {"Authorization": "Bearer venue-token"}
LOCAL = "127.0.0.1,localhost"  # never send loopback calls through a proxy
SEED = [
    ("Search Big Hall", "Search Wing"),
    ("Search Small Room", "Search Wing"),
    ("Harbour Room", "Harbour Block"),
]


class _FakeAuth(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        token = (self.headers.get("Authorization") or "").removeprefix("Bearer ")
        user = USERS.get(token.strip())
        if self.path != "/auth/me" or user is None:
            self.send_response(401)
            self.end_headers()
            return
        payload = json.dumps(user).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *_args: object) -> None:
        pass


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _local_client() -> httpx.Client:
    return httpx.Client(trust_env=False, timeout=5)


@pytest.fixture(scope="module")
def auth_url() -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _FakeAuth)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


@pytest.fixture(scope="module")
def venue_url(auth_url: str) -> Iterator[str]:
    port = _free_port()
    # Environment variables beat venueService's local .env in
    # pydantic-settings, so a developer's .env cannot point this at Supabase.
    env = {
        **os.environ,
        "VENUE_STORAGE_BACKEND": "memory",
        "AUTH_SERVICE_URL": auth_url,
        "NO_PROXY": LOCAL,
        "no_proxy": LOCAL,
    }
    for key in ("SUPABASE_URL", "SUPABASE_SECRET_KEY", "SUPABASE_KEY"):
        env.pop(key, None)
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--app-dir",
            str(VENUE_DIR),
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=VENUE_DIR,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    url = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 15
        with _local_client() as http:
            while True:
                if proc.poll() is not None:
                    pytest.fail(f"venueService exited:\n{proc.stdout.read()}")
                try:
                    health = http.get(f"{url}/health")
                    if health.is_success:
                        break
                except httpx.HTTPError:
                    pass
                if time.monotonic() > deadline:
                    proc.terminate()
                    pytest.fail(f"venueService did not start:\n{proc.stdout.read()}")
                time.sleep(0.1)
        # The right ``app`` package booted, not equipmentService's.
        assert health.json()["service"] == "venueService"
        yield url
    finally:
        proc.terminate()
        try:
            proc.wait(5)
        except subprocess.TimeoutExpired:
            proc.kill()


@pytest.fixture(scope="module")
def venue_ids(venue_url: str) -> dict[str, str]:
    """Seed venues through venueService's real API as Venue Staff. This
    succeeding with no Supabase credentials proves the in-memory store."""
    ids = {}
    with _local_client() as http:
        for name, location in SEED:
            response = http.post(
                f"{venue_url}/venues",
                headers=VENUE_STAFF,
                json={
                    "name": name,
                    "location": location,
                    "max_capacity": 100,
                    "facilities": [],
                    "accessibility_features": [],
                    "supported_layouts": ["theatre"],
                    "operating_slots": ["AM", "PM"],
                },
            )
            assert response.status_code == 201, response.text
            ids[name] = response.json()["id"]
    return ids


@pytest.fixture
def store() -> ReservationStore:
    return ReservationStore()


@pytest.fixture
def api(
    monkeypatch: pytest.MonkeyPatch,
    store: ReservationStore,
    auth_url: str,
    venue_url: str,
) -> Iterator[TestClient]:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_test")
    monkeypatch.setenv("AUTH_SERVICE_URL", auth_url)
    monkeypatch.setenv("VENUE_SERVICE_URL", venue_url)
    monkeypatch.setenv("NO_PROXY", LOCAL)
    monkeypatch.setenv("no_proxy", LOCAL)
    get_settings.cache_clear()
    app.dependency_overrides[get_client] = lambda: store
    yield TestClient(app)
    app.dependency_overrides.clear()
    get_settings.cache_clear()


def _reserve(api: TestClient, venue_id: str, equipment_id: str = PH10):
    return api.post(
        "/equipment-reservations",
        headers=STAFF,
        json={
            "requirement_id": REQ1,
            "equipment_id": equipment_id,
            "quantity": 5,
            "start_date": "2026-10-14",
            "end_date": "2026-10-14",
            "venue_id": venue_id,
        },
    )


# AC1-X6 (cross-cutting): reserving works against the real venueService;
# Harbour Room is found in Harbour Block from real venue data (transfer day)
def test_staff_reserve_against_real_venue_service(
    api: TestClient, store: ReservationStore, venue_ids: dict[str, str]
) -> None:
    response = _reserve(api, venue_ids["Search Big Hall"])

    assert response.status_code == 201, response.text
    assert store.rpc_calls[0][1]["p_collection_date"] == "2026-10-12"


# AC1-X6 (cross-cutting): a row in the event venue's building gets no transfer day
def test_same_building_row_gets_no_transfer_day(
    api: TestClient, store: ReservationStore, venue_ids: dict[str, str]
) -> None:
    response = _reserve(api, venue_ids["Search Big Hall"], equipment_id=PS10)

    assert response.status_code == 201, response.text
    assert store.rpc_calls[0][1]["p_collection_date"] == "2026-10-13"


# AC1-X7 (cross-cutting, SCRUM-10 regression): the availability check works
# against the real venueService
def test_staff_availability_check_against_real_venue_service(
    api: TestClient, venue_ids: dict[str, str]
) -> None:
    response = api.post(
        "/equipment/availability-check",
        headers=STAFF,
        json={
            "start_date": "2026-10-14",
            "end_date": "2026-10-14",
            "venue_id": venue_ids["Search Big Hall"],
            "items": [{"type": "Projector", "quantity": 5}],
        },
    )

    assert response.status_code == 200, response.text
    assert isinstance(response.json()["Projector"]["available"], int)


# AC1-X6 (negative): a venue the real service does not know is a 404
def test_unknown_venue_from_real_service_is_404(
    api: TestClient, store: ReservationStore, venue_ids: dict[str, str]
) -> None:
    response = _reserve(api, "v-missing")

    assert response.status_code == 404
    assert response.json() == {"detail": "Venue not found"}
    assert store.rpc_calls == []


# AC1-X4 (cross-cutting): Technical Support did not gain the full catalogue
def test_staff_token_still_refused_by_full_catalogue(
    venue_url: str, venue_ids: dict[str, str]
) -> None:
    with _local_client() as http:
        response = http.get(f"{venue_url}/venues", headers=STAFF)

    assert response.status_code == 403
