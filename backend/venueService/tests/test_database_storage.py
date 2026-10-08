"""Exercise database wiring without making requests to a real shared database."""

import json
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app import storage
from app.block_models import VenueBlock
from app.block_repository import block_repository
from app.config import Settings, get_settings
from app.main import app
from app.models import Venue
from app.repository import get_repository, repository
from app.supabase_block_repository import (
    StorageError,
    SupabaseBlockRepository,
    SupabaseDataAPI,
)
from app.supabase_repository import SupabaseVenueRepository

# The verified caller set up in conftest.py.
CREATOR = "00000000-0000-0000-0000-000000000001"


def settings(**overrides):
    return Settings(
        _env_file=None,
        **(
            {
                "venue_storage_backend": "supabase",
                "supabase_url": "https://database.example",
                "supabase_secret_key": "sb_secret_test-only",
            }
            | overrides
        ),
    )


@pytest.fixture
def database(monkeypatch):
    tables = {"venues": [], "venue_blocks": []}
    calls = []
    clients = []

    def handle(request):
        calls.append(request)
        assert request.headers["apikey"] == "sb_secret_test-only"
        table = request.url.path.rsplit("/", 1)[-1]
        params = request.url.params
        if request.method == "POST" and table == "create_venue_block":
            # The locked create_venue_block function (0024) returns one row.
            assert request.url.path.endswith("/rest/v1/rpc/create_venue_block")
            assert "authorization" not in request.headers
            args = json.loads(request.content)
            row = VenueBlock(
                venue_id=args["p_venue_id"],
                start_date=args["p_start_date"],
                end_date=args["p_end_date"],
                slots=args["p_slots"],
                reason_category=args["p_reason_category"],
                reason_detail=args["p_reason_detail"],
                created_by=args["p_created_by"],
            ).model_dump(mode="json")
            tables["venue_blocks"].append(row)
            return httpx.Response(200, json=row)
        if request.method == "POST":
            payload = json.loads(request.content)
            if table == "venue_blocks":
                assert "authorization" not in request.headers
                assert "id" not in payload and "created_at" not in payload
            assert request.headers["prefer"] == "return=representation"
            model = Venue if table == "venues" else VenueBlock
            row = model(**payload).model_dump(mode="json")
            tables[table].append(row)
            return httpx.Response(201, json=[row])
        rows = tables[table]
        for column in ["id", "venue_id"]:
            if column in params:
                rows = [
                    r for r in rows if r[column] == params[column].removeprefix("eq.")
                ]
        if request.method == "PATCH":
            assert request.headers["prefer"] == "return=representation"
            for row in rows:
                row.update(json.loads(request.content))
            return httpx.Response(200, json=rows)
        assert request.method == "GET"
        if table == "venues":
            return httpx.Response(200, json=rows)
        # Simulate a database row cap below the requested page size.
        rows = sorted(rows, key=lambda row: row["id"])
        offset = int(params.get("offset", "0"))
        return httpx.Response(200, json=rows[offset : offset + 1])

    # Venues use the shared SupabaseVenueRepository; built before patching so
    # its long-lived client is not counted among the per-request block clients.
    venues = SupabaseVenueRepository(
        "https://database.example",
        "sb_secret_test-only",
        transport=httpx.MockTransport(handle),
    )
    original_client = httpx.Client

    def make_client(*args, **kwargs):
        client = original_client(*args, transport=httpx.MockTransport(handle), **kwargs)
        clients.append(client)
        return client

    monkeypatch.setattr(storage.httpx, "Client", make_client)
    app.dependency_overrides[get_settings] = lambda: settings()
    app.dependency_overrides[get_repository] = lambda: venues
    yield tables, calls
    assert all(client.is_closed for client in clients)


def create_venue(client):
    response = client.post(
        "/venues", json={"name": "Hall", "location": "Campus", "max_capacity": 100}
    )
    assert response.status_code == 201
    return response.json()


def create_block(client, venue_id, slots=None):
    return client.post(
        f"/venues/{venue_id}/blocks",
        json={
            "start_date": "2026-09-20",
            "end_date": "2026-09-21",
            "slots": slots or ["AM"],
            "reason_category": "maintenance",
            "reason_detail": "Repairs",
        },
    )


# AC1-H6 (happy): blocks persist in the database across requests and drive search
def test_database_creation_retrieval_update_and_search_across_requests(database):
    tables, calls = database
    with TestClient(app) as client:
        venue = create_venue(client)
        assert client.get(f"/venues/{venue['id']}").json() == venue
        first = create_block(client, venue["id"])
        assert first.status_code == 201
        assert first.json()["created_by"] == CREATOR
        # Make sure pagination includes a later active block too.
        second = create_block(client, venue["id"], ["PM"])
        assert second.status_code == 201
        tables["venue_blocks"][0]["status"] = "lifted"

    with TestClient(app) as client:
        result = client.get(f"/venues/{venue['id']}/blocks")
        assert result.status_code == 200
        assert {r["id"] for r in result.json()} == {
            first.json()["id"],
            second.json()["id"],
        }
        assert (
            client.get(
                "/venues/search", params={"date": "2026-09-20", "slot": "PM"}
            ).json()
            == []
        )
        assert (
            len(
                client.get(
                    "/venues/search", params={"date": "2026-09-20", "slot": "AM"}
                ).json()
            )
            == 1
        )
        assert client.get("/venues").json()[0]["id"] == venue["id"]
        response = client.patch(f"/venues/{venue['id']}", json={"max_capacity": 200})
        assert response.status_code == 200
        assert response.json()["max_capacity"] == 200
        assert response.json()["name"] == venue["name"]
        assert response.json()["updated_at"] >= venue["updated_at"]

    assert repository.list() == [] and block_repository.list() == []
    assert any(r.url.params.get("offset") == "1" for r in calls)


# AC1-N16 (negative): unknown or malformed venue ids store nothing in the database
def test_database_missing_and_invalid_venue_ids(database):
    with TestClient(app) as client:
        for venue_id in ["not-a-uuid", str(uuid4())]:
            assert client.get(f"/venues/{venue_id}").status_code == 404
            assert client.get(f"/venues/{venue_id}/blocks").status_code == 404
            assert create_block(client, venue_id).status_code == 404
            assert (
                client.patch(
                    f"/venues/{venue_id}", json={"name": "Missing"}
                ).status_code
                == 404
            )
    assert database[0] == {"venues": [], "venue_blocks": []}


# AC2-P10 (partition): a database block hides only its own venue
def test_database_blocks_are_scoped_to_venue(database):
    with TestClient(app) as client:
        first, second = create_venue(client), create_venue(client)
        assert create_block(client, first["id"]).status_code == 201
        assert client.get(f"/venues/{second['id']}/blocks").json() == []
        results = client.get(
            "/venues/search", params={"date": "2026-09-20", "slot": "AM"}
        )
        assert {v["id"] for v in results.json()} == {second["id"]}


# AC1-N17 (negative): database errors map to 409, 422 or 502 without leaking details
@pytest.mark.parametrize(
    "code,expected",
    [("23503", 409), ("23514", 422), ("42501", 502)],
    ids=["AC1-N17a", "AC1-N17b", "AC1-N17c"],
)
def test_database_errors_are_sanitized_and_mapped(code, expected):
    def handle(request):
        return httpx.Response(
            400, json={"code": code, "message": "PRIVATE DATABASE DETAIL"}
        )

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        api = SupabaseDataAPI(client, "https://database.example", "sb_secret_test")
        app.dependency_overrides[storage.get_block_repository] = (
            lambda: SupabaseBlockRepository(api)
        )
        with TestClient(app) as test_client:
            venue = create_venue(test_client)
            response = test_client.get(f"/venues/{venue['id']}/blocks")
        assert response.status_code == expected
        assert "PRIVATE" not in response.text


# AC4-N5 (negative): a database timeout is an error, never an empty block list
def test_timeout_does_not_return_false_empty_availability():
    def handle(request):
        raise httpx.ReadTimeout("private", request=request)

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        api = SupabaseDataAPI(client, "https://database.example", "sb_secret_test")
        with pytest.raises(StorageError, match="Database is unavailable"):
            api.list_rows("venue_blocks")


# AC1-N18 (negative): a non-UUID creator is refused before reaching the database
def test_invalid_creator_is_not_sent_to_database():
    def handle(request):
        pytest.fail("An invalid creator must not reach the database")

    from app.block_models import VenueBlockCreate

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        repo = SupabaseBlockRepository(
            SupabaseDataAPI(client, "https://database.example", "sb_secret_test")
        )
        data = VenueBlockCreate(
            start_date="2026-09-20",
            end_date="2026-09-20",
            slots=["AM"],
            reason_category="maintenance",
        )
        with pytest.raises(StorageError, match="creator UUID"):
            repo.create(str(uuid4()), data, "stub-venue-staff")


# AC1-X5 (cross-cutting): database mode requires a URL and a server-side secret key
@pytest.mark.parametrize(
    "overrides",
    [
        {"supabase_secret_key": None},
        {"supabase_url": None},
        {"supabase_secret_key": "sb_publishable_wrong"},
    ],
    ids=["AC1-X5a", "AC1-X5b", "AC1-X5c"],
)
def test_invalid_settings_rejected(overrides):
    with pytest.raises(ValidationError):
        settings(**overrides)
