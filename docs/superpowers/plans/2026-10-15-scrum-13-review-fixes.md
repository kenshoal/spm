# SCRUM-13 Review Fixes: Venue-Locations Contract, Type Check in `reserve_equipment`, Cross-Service Test and Evidence

Drafted 15 October 2026 by Claude (Cowork) for Yang Xue (SCRUM-13 owner). **Status: approved.** Gate G1 (§2) agreed by Jaren (SCRUM-39) and koeiloo23 / Kennedy (venue catalogue) on 15 October 2026.

Follows `docs/superpowers/plans/2026-10-14-scrum-13-reserve-equipment.md` (on the SCRUM-13 branch). This plan covers the two defects found in the teammate review, the cross-service regression test, the live authenticated run, and the evidence corrections.

**Branch:** keep working on `feat/scrum-13-reserve-equipment` (tip `6617258`, 10 commits ahead of the old `dev`). `origin/dev` has since moved to `6b36647` (SCRUM-58 merged, adding `0026_event_request_planning.sql`). Nothing is merged into `dev` yet, so these fixes go on the same branch and PR.

---

## 1. Findings being fixed

| ID | Finding | Verified how | Consequence |
| --- | --- | --- | --- |
| F1 | equipmentService forwards the caller's token to venueService `GET /venues`. That route uses `require_venue_viewer`, which only admits `event_coordinator` and `venue_staff` (`backend/venueService/app/dependencies.py`, added in `6859656 fix(auth): restrict resource reads by role`, 4 Oct). venueService answers **403** to `technical_support`; `app/venues_client.py` maps any non-success except 401 to **502 "Venue service unavailable"**. | Code read on 15 Oct | Every real `POST /equipment-reservations` fails. **SCRUM-10's `POST /equipment/availability-check` is broken the same way** and has been since 4 Oct (it is merged and Done). |
| F2 | Both equipmentService venue stubs (`tests/reservations_support.py`, `tests/test_availability_check.py`) return 200 for `/venues` whatever the caller's role. | Code read | Why F1 passed CI: the stub agreed with equipmentService rather than with venueService. Needs a test that runs venueService's real permission code. |
| F3 | `reserve_equipment` (migration `0027`, applied to shared dev 14 Oct) does not compare the equipment row's `type` with the requirement's `equipment_type`. Only the API checks it. | Code read | Any other caller of the function (SCRUM-58, SCRUM-64, a manual SQL call) can store Speaker stock against a Projector requirement. |
| F4 | Evidence record cites `288daa9`, an unreachable pre-rebase commit; Green runs are attributed to "Claude (Sonnet 5.5)" although GLM wrote and ran the code. | `git cat-file`, `git branch --contains` | Breaks traceability (testing.md §8). |
| F5 | DB-layer cases (AC1-N9, AC2-N2, AC3-N1, AC3-N2, AC4-H2) and AC3-X1 are still "Not executed" on shared Supabase. The teammate reports concurrency results that passed on a **disposable PostgreSQL** instance. | Branch docs at `6617258` (the disposable-Postgres run is not committed on the branch I can see) | testing.md §8: "Keep local, shared-database, browser and pull-request CI results separate; one does not substitute for another." A disposable-Postgres pass cannot be recorded as shared-Supabase verification. |
| F6 | My plan of 14 Oct put Red test-only commits first; three were pushed (`afc544c`, `6268726`, `ca03bed`). commits.md §4: "Never push a red commit to a shared branch … commit the test together with the change that makes it pass." | commits.md | Already pushed, so leave history alone (rewriting a shared branch needs team agreement). **This plan follows §4:** write tests first and record Red in the matrix, but commit each test with its fix. |

---

## 2. Gate G1: agree the venue-access contract (before any Part A code)

Owners: **Jaren** (SCRUM-39, owns the role matrix, where Technical Support currently reads only "Reservation records") and **koeiloo23 / Kennedy** (venue catalogue, `routers/venues.py`).

**What equipmentService needs:** for each venue, `id`, `name` and `location` (building). It uses them in `needs_transfer()` to (a) find the event venue's building from `venue_id` and (b) find which building a catalogue row's `home_location` is in, by venue name. It needs *all* venues, including blocked ones, because a blocked room still locates stock (comment in `venues_client.py`). It never needs capacity, facilities, layouts, slots, status, timestamps, blocks or bookings.

**Proposal D11 (recommended):** a new read-only `GET /venues/locations` in venueService returning `[{ "id", "name", "location" }]` for every venue, allowed for `technical_support`, `event_coordinator` and `venue_staff`. All existing venue routes keep their current guards, so Technical Support still gets 403 on `/venues`, `/venues/search`, `/venues/{id}`, blocks, suitability and booking routes.

Rejected alternatives:

| Option | Why not |
| --- | --- |
| Add `technical_support` to `require_venue_viewer` | Grants the full catalogue, search and single-venue reads, which Technical Support does not need; widens SCRUM-39's matrix more than necessary. |
| equipmentService calls venueService with a service credential | No service-to-service auth exists in the project; new secret and auth path for one read. |
| equipmentService reads `public.venues` directly with its Supabase key | Crosses the service boundary the team keeps (each service owns its tables); breaks if venueService runs in memory mode. |
| Copy venue buildings into equipmentService | Duplicate data that goes stale when a venue is renamed or moved. |

Message to send (edit as you like):

> Hi Jaren, koeiloo23, Kennedy: SCRUM-13 and SCRUM-10 call venueService `GET /venues` with the Technical Support token to work out transfer days, but `require_venue_viewer` (from 6859656) returns 403 for `technical_support`, so both endpoints 502 against the real services. Proposal: add a read-only `GET /venues/locations` returning only `id`, `name`, `location` for every venue, open to technical_support, event_coordinator and venue_staff. No other venue route changes. Jaren, this adds "venue locations (id, name, building)" to Technical Support's row in the SCRUM-39 matrix. OK to go ahead?

Record the agreement (who, date) in the SCRUM-13 catalogue under D11, and ask Jaren to add the row to `scrum_39_testcases.md` or agree that Yang adds it.

---

## 3. Order of work and commits

Each fix is written test-first: write the tests, run them, record the **Red** result in the SCRUM-13 matrix, implement, run Green, then commit test + fix together (commits.md §4).

| # | Commit | Contains | Pushed state |
| --- | --- | --- | --- |
| 0 | `chore: merge dev into feat/scrum-13-reserve-equipment` | `origin/dev` `6b36647` (SCRUM-58). **In progress as of 15 Oct:** the `database/README.md` conflict is resolved, the merge is not yet committed. Before committing, put the `0027` row directly under `0026` with no blank line between them (a blank line ends a Markdown table; the blank line before the `0025` row on `dev` already breaks the table, so remove that one too). equipmentService on the merged tree: 323 passed (checked 15 Oct). | Green |
| 1 | `docs(scrum-13): record review findings, D11 and D12, and new test cases` | Catalogue updates in §8.1 (decisions, new IDs, Red results once run) | n/a (docs) |
| 2 | `feat(venue): expose venue locations to Technical Support (SCRUM-13)` | Part A: venueService model, dependency, route, `tests/test_venue_locations.py`, venueService README | Green |
| 3 | `fix(equipment): read venue locations for reservations and availability (SCRUM-13)` | Part B: `venues_client.py`, both venue stubs, `tests/test_venue_contract.py`, equipmentService README | Green |
| 4 | `fix(db): check equipment type inside reserve_equipment (SCRUM-13)` | Part C: `0028`, verify-script cases, `rpc_errors.py` 22023 mapping, API test AC1-N12, database README | Green (0028 applied to shared dev before push, see §6) |
| 5 | `fix(equipment): guard an empty reserve_equipment result (SCRUM-13)` | Part D (optional nit) | Green |
| 6 | `docs(scrum-13): record Green, shared-database and live evidence` | Part E evidence, F4 corrections | n/a |

Every commit ends with the agent attribution lines and, per commits.md §3, names migrations and whether they are applied, and lists tests added (count and file). Commit 3's body must say it updates the two venue stubs that its own change legitimately broke.

---

## 4. Part A: venueService `GET /venues/locations` (D11)

### 4.1 Tests first: `backend/venueService/tests/test_venue_locations.py` (new)

Follow `tests/test_venues_catalogue.py`: module-level `client = TestClient(app)`; `conftest.py` already overrides `require_authenticated` and `require_venue_staff` with a `venue_staff` principal and clears the in-memory repository. Seed as venue staff, then swap the principal.

```python
def _as(*roles: str) -> None:
    app.dependency_overrides[require_authenticated] = lambda: Principal(
        user_id="00000000-0000-0000-0000-000000000013", roles=tuple(roles)
    )

def _seed() -> dict[str, str]:
    """Two buildings, one blocked venue: as SCRUM-10's VENUES."""
    ids = {}
    for name, location in [("Search Big Hall", "Search Wing"),
                           ("Harbour Room", "Harbour Block")]:
        ids[name] = client.post("/venues", json=_payload(name=name, location=location)).json()["id"]
    closed = client.post("/venues", json=_payload(name="Search Closed Hall", location="Search Wing")).json()["id"]
    client.patch(f"/venues/{closed}", json={"status": "blocked"})
    ids["Search Closed Hall"] = closed
    return ids
```

| Test | Case ID | Asserts |
| --- | --- | --- |
| `test_staff_read_venue_locations` | AC1-X3 | `_as("technical_support")`; `GET /venues/locations` → 200; body is exactly the 3 seeded venues; **each item's keys are exactly `{"id", "name", "location"}`**; the blocked venue is included |
| `test_locations_are_not_the_full_catalogue` | AC1-X3 | same call; no item has `max_capacity`, `facilities`, `status`, `created_at` (guards against someone switching `response_model` to `Venue`) |
| `test_existing_readers_can_read_locations` (parametrized `event_coordinator`, `venue_staff`, `("event_operations_manager", "technical_support")`) | AC1-X5 | 200 for each |
| `test_other_roles_cannot_read_locations` (parametrized `attendee`, `event_organiser`, `event_operations_manager`) | AC1-X5 | 403 "Insufficient permissions" |
| `test_locations_require_a_session` | AC1-X5 | `app.dependency_overrides.pop(require_authenticated)`; no header → 401 |
| `test_staff_still_cannot_read_the_catalogue` | AC1-X4 | `_as("technical_support")`; `GET /venues`, `GET /venues/search`, `GET /venues/{id}`, `GET /venues/{id}/blocks`, `POST /venues/{id}/suitability` (`{"expected_attendance": 10}`), `GET /booking-requests` → all 403 |
| `test_locations_route_is_not_a_venue_id` | AC1-X3 | as `venue_staff`, `GET /venues/locations` → 200 and a list (not 404 "Venue not found"): proves the route is declared before `/{venue_id}` |

Expected **Red** (record it): AC1-X3/X5 fail with 403 for `technical_support` and 404 "Venue not found" for `venue_staff` (the path is captured by `GET /venues/{venue_id}`); AC1-X4 already passes (it pins existing behaviour).

Check `/booking-requests`' guard before writing that row: it uses `require_booking_reader` (`venue_staff`, `event_coordinator`), so 403 is the expected current behaviour.

### 4.2 Implementation

`app/models.py`, after `class Venue`:

```python
class VenueLocation(BaseModel):
    """The minimum venue facts other services need to place equipment (SCRUM-13 D11)."""

    id: str
    name: str
    location: str
```

`app/dependencies.py`, after `require_venue_viewer`:

```python
VENUE_LOCATION_READERS = frozenset({"event_coordinator", "venue_staff", "technical_support"})


def require_venue_location_reader(
    principal: Annotated[Principal, Depends(require_authenticated)],
) -> Principal:
    """Venue id, name and building only (SCRUM-13 D11): Technical Support needs
    them to work out equipment transfer days, and nothing else in the catalogue."""
    if set(principal.roles).isdisjoint(VENUE_LOCATION_READERS):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permissions")
    return principal
```

`app/routers/venues.py`:

- import `VenueLocation` and `require_venue_location_reader`; add `VenueLocationReaderDep = Annotated[Principal, Depends(require_venue_location_reader)]`;
- add the route **directly after `list_venues` and before `GET /{venue_id}`** (currently line ~192). FastAPI matches in declaration order, so declaring it later makes `locations` a venue id.

```python
@router.get("/locations", response_model=list[VenueLocation])
def list_venue_locations(
    principal: VenueLocationReaderDep, repo: RepoDep
) -> list[VenueLocation]:
    """Every venue's id, name and building, blocked venues included: a blocked
    room still locates the equipment stored in it (SCRUM-13 D11)."""
    del principal
    return [
        VenueLocation(id=v.id, name=v.name, location=v.location) for v in repo.list()
    ]
```

`repo.list()` works for both the memory and Supabase stores; no new storage code.

`backend/venueService/README.md`: endpoint row (`GET /venues/locations`, roles, response shape, why it exists).

Run from `backend/venueService/`: `pytest -q` (expect previous count + new tests, 0 failed), `ruff check .`.

---

## 5. Part B: equipmentService reads `/venues/locations` and the cross-service test

### 5.1 Switch the client

`app/venues_client.py`:

- URL `f"{base}/venues"` → `f"{base}/venues/locations"`;
- docstring: name the endpoint and D11; keep "closed venues are included on purpose";
- keep the error mapping unchanged (401 → 401 "Invalid session"; any other non-success, including 403, → 502). Add one line to the docstring that a 403 here means a venueService permission regression, which the cross-service test catches.

Both callers (`routers/availability.py`, `routers/reservations.py`) use `fetch_venues` and need no change.

### 5.2 Update the two venue stubs (tests this change legitimately breaks)

| File | Change |
| --- | --- |
| `tests/reservations_support.py` | `Services.get`: match `url.rstrip("/").endswith("/venues/locations")`; same for `venue_calls`; docstring "venueService `GET /venues/locations`". Drop `"status"` from `VENUES_JSON` items so the fixture matches the new shape. |
| `tests/test_availability_check.py` | Same two matches (lines ~87 and ~95) and the docstring at ~72; drop `"status"` from its `VENUES_JSON`. |
| `docs/testcases/scrum_10_testcases.md` | AC1-H2 expected result: "`GET /venues/locations` called once with the caller's `Authorization` header"; "Venues (`VENUES`)" heading: "returned by venueService `GET /venues/locations`". Add a dated note that SCRUM-10's live path was broken from `6859656` (4 Oct) until this fix. |

Expected **Red** after the stub change and before 5.1: every reservation and availability-check API test errors with `AssertionError: unexpected GET …/venues` raised by the stub. After 5.1: Green.

### 5.3 Cross-service regression test: `backend/equipmentService/tests/test_venue_contract.py` (new)

**Purpose (F2):** run equipmentService's real `fetch_venues` and auth seam over real HTTP against the **real venueService app and its real role check**, so a future guard change in either service fails CI.

**Why it can live in equipmentService's normal CI job:** venueService's runtime dependencies (`fastapi`, `httpx`, `pydantic-settings`, `uvicorn[standard]`) are a subset of equipmentService's, which CI already installs. venueService runs as a **subprocess** (`python -m uvicorn app.main:app --app-dir backend/venueService`), so its `app` package never clashes with equipmentService's `app` in the test process. No new CI job, no new install step.

**Harness:**

```python
"""Cross-service regression for SCRUM-13 D11 (AC1-X6, AC1-X7).

equipmentService runs in-process (TestClient; Supabase is ReservationStore).
venueService runs for real in a subprocess with in-memory storage. A tiny
fake authService serves /auth/me to BOTH services over real HTTP, so the
roles venueService enforces are the ones equipmentService forwarded.
"""

import json, os, socket, subprocess, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from reservations_support import PH10, P10, REQ1, TSS, ReservationStore

from app.config import get_settings
from app.db import get_client
from app.main import app

VENUE_DIR = Path(__file__).resolve().parents[2] / "venueService"
USERS = {
    "staff-token": {"id": TSS, "role": "technical_support", "roles": ["technical_support"]},
    "venue-token": {"id": "44444444-4444-4444-4444-444444444444",
                    "role": "venue_staff", "roles": ["venue_staff"]},
}
LOCAL = "127.0.0.1,localhost"  # never send loopback calls through a proxy
```

Fixtures (all `scope="module"` except the per-test settings/override one):

1. `auth_url`: `ThreadingHTTPServer(("127.0.0.1", 0), _FakeAuth)` in a daemon thread. `_FakeAuth.do_GET` returns `USERS[token]` as JSON for `GET /auth/me`, else 401; silence `log_message`. Yield `http://127.0.0.1:<port>`; `shutdown()` after.
2. `venue_url`: pick a free port (`socket.bind(("127.0.0.1", 0))`), then
   ```python
   env = {**os.environ, "VENUE_STORAGE_BACKEND": "memory",
          "AUTH_SERVICE_URL": auth_url, "NO_PROXY": LOCAL, "no_proxy": LOCAL}
   proc = subprocess.Popen(
       [sys.executable, "-m", "uvicorn", "app.main:app", "--app-dir", str(VENUE_DIR),
        "--host", "127.0.0.1", "--port", str(port)],
       cwd=VENUE_DIR, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
   ```
   Poll `GET /health` every 0.1 s for up to 15 s; **assert the health body's `service` is `"venueService"`** (proves the right `app` package booted). If the process exits or times out, `pytest.fail` with its captured output. Teardown: `terminate()`, `wait(5)`, `kill()` on timeout.
   - Env vars beat venueService's local `.env` in pydantic-settings, so a developer's `.env` with `VENUE_STORAGE_BACKEND=supabase` cannot make the test touch the shared database. Assert this once: `POST /venues` must succeed with no Supabase credentials set.
3. `venue_ids`: seed through the real API with `venue-token`: "Search Big Hall"/"Search Wing", "Search Small Room"/"Search Wing", "Harbour Room"/"Harbour Block" (valid `VenueCreate` bodies, `max_capacity` > 0). Return `{name: id}`.
4. `api` (function scope): `monkeypatch.setenv` `SUPABASE_URL`, `SUPABASE_SECRET_KEY` (dummy), `AUTH_SERVICE_URL=auth_url`, `VENUE_SERVICE_URL=venue_url`, `NO_PROXY`/`no_proxy`; `get_settings.cache_clear()`; `app.dependency_overrides[get_client] = lambda: store`; yield `TestClient(app)`; clear overrides and settings cache. **Do not monkeypatch `httpx.get`** (that is the whole point).

| Test | Case ID | Steps | Asserts |
| --- | --- | --- | --- |
| `test_staff_reserve_against_real_venue_service` | AC1-X6 | `POST /equipment-reservations` with `staff-token`, body `{requirement_id: REQ1, equipment_id: PH10, quantity: 5, start_date/end_date: "2026-10-14", venue_id: venue_ids["Search Big Hall"]}` | 201; `store.rpc_calls[0][1]["p_collection_date"] == "2026-10-12"` (Harbour Room found in Harbour Block from **real** venue data: transfer day applied) |
| `test_same_building_row_gets_no_transfer_day` | AC1-X6 | same body with `equipment_id: PS10` (home "Search Small Room", same building as the event venue) | 201; collection `"2026-10-13"` |
| `test_staff_availability_check_against_real_venue_service` | AC1-X7 (SCRUM-10 regression) | `POST /equipment/availability-check` with `staff-token`, `venue_id` from `venue_ids`, one Projector item. The availability router reads `equipment` and `equipment_reservations` via the same client; `ReservationStore` supports `.eq`/`.in_`/`.lte`/`.gte` | 200 (not 502); `available` is a number |
| `test_unknown_venue_from_real_service_is_404` | AC1-X6 | `venue_id: "v-missing"` | 404 "Venue not found" |
| `test_staff_token_still_refused_by_full_catalogue` | AC1-X4 (cross-service) | direct `httpx.get(f"{venue_url}/venues", headers=staff)` | 403: Technical Support did not gain the catalogue |

Expected **Red** on the current code (record it): AC1-X6/X7 → 502 "Venue service unavailable" (this is F1 reproduced). With Part A only: still 502 (equipmentService still calls `/venues`). With Parts A and B: Green. That pairing is the regression guard.

Runtime target: under 5 s for the module. If CI on a cold runner is slow, raise the health-poll timeout, not the per-request timeout.

Register a marker in `backend/equipmentService/pyproject.toml` so developers can skip it offline but CI still runs it:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
markers = ["cross_service: starts venueService in a subprocess"]
```

and `pytestmark = pytest.mark.cross_service` in the module. CI keeps running plain `pytest`, which includes it.

`backend/equipmentService/README.md`: SCRUM-10 and SCRUM-13 rows now say "calls venueService `GET /venues/locations` with the caller's token"; add a "Tests" line about the cross-service module.

---

## 6. Part C: type check inside `reserve_equipment` (D12), migration `0028`

### 6.1 Decision D12

`reserve_equipment` refuses a catalogue row whose type differs from the requirement's type, comparing the way Python's `norm()` does (case-insensitive, surrounding spaces trimmed, internal runs of whitespace collapsed). It raises **SQLSTATE `22023`** (`invalid_parameter_value`), not `P0004`, because a wrong type is a bad request, not a lost race. equipmentService maps `22023` → **422 "Equipment type does not match the requirement"** (the same message as the API pre-check). The check runs after both rows are locked and before the status check, so the order inside the function matches the API's (D10).

Note: SQL `lower()` and Python `casefold()` differ only for a few non-ASCII letters (e.g. "ß"); equipment types are ASCII in practice. Record this as a known limit in D12.

### 6.2 Tests first

**DB: add to `database/verify_equipment_reservation_writes.sql`** (inside the `DO` block, after AC2-N2 and before AC3-N1, so the AC3-N1 sums on `v_equipment` are untouched). Declare `v_speaker uuid; v_spaced uuid;`.

```sql
    -- AC1-N10 (negative): Speaker stock against a Projector requirement is refused under the lock
    INSERT INTO equipment (type, total_owned_quantity, home_location, created_by)
    VALUES ('VERIFY-13 Speaker', 10, 'Store Room B', v_staff)
    RETURNING id INTO v_speaker;
    BEGIN
        PERFORM public.reserve_equipment(
            v_requirement, v_speaker, 1, DATE '2026-10-13', DATE '2026-10-14', v_staff
        );
        RAISE EXCEPTION 'AC1-N10: a Speaker row must not be reserved against a Projector requirement';
    EXCEPTION
        WHEN SQLSTATE '22023' THEN NULL;  -- expected
    END;
    SELECT count(*) INTO v_count FROM equipment_reservations WHERE equipment_id = v_speaker;
    ASSERT v_count = 0, 'AC1-N10: nothing stored for the mismatched row';

    -- AC1-N11 (partition): a type differing only by case and spacing is the same type
    INSERT INTO equipment (type, total_owned_quantity, home_location, created_by)
    VALUES ('  verify-13   PROJECTOR ', 10, 'Store Room B', v_staff)
    RETURNING id INTO v_spaced;
    SELECT * INTO v_row FROM public.reserve_equipment(
        v_requirement, v_spaced, 1, DATE '2026-10-13', DATE '2026-10-14', v_staff
    );
    ASSERT v_row.equipment_id = v_spaced, 'AC1-N11: normalised type match accepted';
```

Arithmetic check: `v_requirement` needs 5 and holds 2 after AC4-H2, so 1 more is within D3. Update the script header's "Contract under test" to list the type check and `22023`, and change "AFTER applying migration 0027" to "AFTER 0027 and 0028".

`equipment.type` is `varchar(120) NOT NULL` with no CHECK (`0001_baseline.sql`), so the spaced value is accepted.

**API: add to `tests/test_reservations_api.py`** under AC1:

```python
# AC1-N12 (negative): a type mismatch caught only under the lock (D12) is a 422, not a 500
def test_type_mismatch_under_lock_is_unprocessable(
    api: TestClient, store: ReservationStore
) -> None:
    store.rpc_error = api_error("22023")
    before = store.reservations()

    response = reserve(api)

    assert response.status_code == 422
    assert response.json() == {"detail": "Equipment type does not match the requirement"}
    assert store.writes == []
    assert store.reservations() == before
```

Expected **Red**: AC1-N12 → 500 "Database operation failed"; AC1-N10 → script stops at the `RAISE EXCEPTION 'AC1-N10: …'` line (the function stores the row); AC1-N11 passes already.

Run the Red DB check on shared dev **before** applying 0028, in the SQL Editor (the script rolls back). Record it as "Shared Supabase dev, SQL Editor, before 0028: Fail (expected)".

### 6.3 Migration `database/migrations/0028_reserve_equipment_type_check.sql`

Number check first: after merging `dev`, `ls database/migrations` must end at `0027`. If someone has taken `0028`, use the next free number and update every reference.

```sql
-- Type check inside reserve_equipment (SCRUM-13 D12). Safe to re-run.
-- 0027 is applied to shared development, so it is not edited; this
-- replaces the function body. Everything else is 0027's logic unchanged:
-- lock order requirement -> equipment (D6a), status, outstanding quantity,
-- busiest-day peak, insert with the event copied from the requirement.

CREATE OR REPLACE FUNCTION public.reserve_equipment(
    p_requirement_id uuid,
    p_equipment_id uuid,
    p_quantity integer,
    p_collection_date date,
    p_return_date date,
    p_created_by uuid
)
RETURNS public.equipment_reservations
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ''
AS $$
DECLARE
    v_requirement public.equipment_requirements;
    v_equipment public.equipment;
    v_held integer;
    v_peak integer;
    v_row public.equipment_reservations;
BEGIN
    SELECT * INTO v_requirement FROM public.equipment_requirements
    WHERE id = p_requirement_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'equipment requirement not found' USING ERRCODE = 'P0002';
    END IF;

    SELECT * INTO v_equipment FROM public.equipment
    WHERE id = p_equipment_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'equipment not found' USING ERRCODE = 'P0002';
    END IF;

    -- D12: same comparison as Python norm(): trim, collapse whitespace, ignore case.
    IF lower(btrim(regexp_replace(v_equipment.type, '\s+', ' ', 'g')))
       <> lower(btrim(regexp_replace(v_requirement.equipment_type, '\s+', ' ', 'g'))) THEN
        RAISE EXCEPTION 'equipment type % does not match requirement type %',
            v_equipment.type, v_requirement.equipment_type
            USING ERRCODE = '22023';
    END IF;

    IF v_equipment.operational_status <> 'AVAILABLE' THEN
        RAISE EXCEPTION 'equipment is %', v_equipment.operational_status USING ERRCODE = 'P0004';
    END IF;

    SELECT coalesce(sum(quantity), 0) INTO v_held
    FROM public.equipment_reservations WHERE requirement_id = p_requirement_id;
    IF v_held + p_quantity > v_requirement.quantity THEN
        RAISE EXCEPTION 'exceeds requirement' USING ERRCODE = 'P0004';
    END IF;

    SELECT coalesce(max(day_total), 0) INTO v_peak
    FROM (
        SELECT sum(r.quantity) AS day_total
        FROM generate_series(p_collection_date, p_return_date, interval '1 day') AS g(day)
        JOIN public.equipment_reservations r
          ON r.equipment_id = p_equipment_id
         AND r.collection_date <= g.day::date
         AND r.return_date >= g.day::date
        GROUP BY g.day
    ) per_day;
    IF v_peak + p_quantity > v_equipment.total_owned_quantity THEN
        RAISE EXCEPTION 'insufficient units' USING ERRCODE = 'P0004';
    END IF;

    INSERT INTO public.equipment_reservations
        (requirement_id, event_request_id, equipment_id, quantity,
         collection_date, return_date, created_by)
    VALUES
        (p_requirement_id, v_requirement.event_request_id, p_equipment_id, p_quantity,
         p_collection_date, p_return_date, p_created_by)
    RETURNING * INTO v_row;

    RETURN v_row;
END;
$$;

-- CREATE OR REPLACE keeps existing privileges; restated so a fresh
-- environment that runs 0028 alone is also locked down (0006/0013 pattern).
REVOKE ALL ON FUNCTION public.reserve_equipment(uuid, uuid, integer, date, date, uuid)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.reserve_equipment(uuid, uuid, integer, date, date, uuid)
    TO service_role;
```

Diff the function body against `0027` before committing (`diff <(sed -n '/CREATE OR REPLACE/,/^\$\$;/p' 0027…) <(… 0028…)`): the only difference must be the D12 block and comments.

### 6.4 API mapping: `app/rpc_errors.py`

```python
TYPE_MISMATCH_ERRCODE = "22023"
```

In `reservation_rpc_error_to_http`, before the P0004 branch:

```python
    if exc.code == TYPE_MISMATCH_ERRCODE:
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Equipment type does not match the requirement",
        )
```

Update the docstring (D12). No router change: `reservations.py` already routes RPC `APIError` through this mapper.

### 6.5 Apply and verify on shared dev (Yang)

1. SQL Editor: run `0028`.
2. Run `verify_equipment_reservation_writes.sql` → `ALL EQUIPMENT RESERVATION WRITE VERIFICATIONS PASSED` (covers AC1-N9, N10, N11, AC2-N2, AC3-N1, AC4-H2).
3. Run `verify_equipment_reservations.sql` (SCRUM-10, updated for 0027) → its PASSED notice.
4. Confirm grants: `SELECT grantee, privilege_type FROM information_schema.routine_privileges WHERE routine_name = 'reserve_equipment';` → `service_role` (and the owner) only.
5. Screenshot each result into `docs/testcases/screenshots/scrum_13/` and record in the matrix with environment "Shared Supabase dev, SQL Editor".

`database/README.md`: `0028` row (what, why `0027` is not edited, applied date), and the verify script now needing `0027` + `0028`.

---

## 7. Part D (optional nit): empty RPC result

In `reservations.py`, after `data = response.data`:

```python
    if isinstance(data, list):
        if not data:
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR, "Database operation failed"
            )
        data = data[0]
```

Test (AC1-N8 family, new ID AC1-N13): `store.rpc_result = []` → 500 "Database operation failed". Skip this part if the PR is getting large; it is not reachable with the current function.

---

## 8. Part E: evidence

### 8.1 Catalogue updates (`docs/testcases/scrum_13_testcases.md`, commit 1, then results in commit 6)

- **Decisions:** add D11 (venue-locations contract, who agreed and when) and D12 (type check under the lock, `22023` → 422, the `lower`/`casefold` limit). Amend D10's message list with the 22023 mapping.
- **Scope table:** add "`GET /venues/locations` in venueService (D11)" and "Migration `0028`".
- **AC1 matrix:** add rows AC1-X3, X4, X5 (venueService API), X6, X7 (cross-service), N10, N11 (DB), N12 (API), N13 (API, if Part D), and the live row L1 below.
- **"How the suites will run":** add venueService `pytest -q tests/test_venue_locations.py`; equipmentService `pytest -q tests/test_venue_contract.py` (cross-service, starts venueService); DB scripts after `0028`.
- **Test files table:** add the two new test modules and the stub changes.
- **Disclosures** (new short section): F1 and F2 (why CI missed it: role-blind stubs), F3, F6 (Red commits already pushed against commits.md §4; left as is).

### 8.2 Execution record: one row per environment

testing.md §8 requires local, shared-database, browser and CI results to be kept separate. Use these environment labels exactly:

| Label | Means | Can satisfy |
| --- | --- | --- |
| **Local, mocked** | pytest with `ReservationStore` and stubbed services | unit and API rows |
| **Local, cross-service** | `test_venue_contract.py`: real venueService subprocess (memory store), fake authService, in-process equipmentService | AC1-X4, X6, X7 |
| **Disposable PostgreSQL** | a throwaway local Postgres with the migrations applied | **AC3-N2 only** (team convention for race tests that commit rows, `database/README.md` SCRUM-48 section); supplementary for every other DB row |
| **Shared Supabase dev, SQL Editor** | the verify scripts against the shared project | AC1-N9–N11, AC2-N2, AC3-N1, AC4-H2 |
| **Live stack on shared Supabase** | all services running, real logins | AC3-X1, L1 |
| **PR CI** | GitHub Actions on the PR head | final regression rows |

**AC3-N2 (two sessions racing) runs on a disposable database, not shared Supabase.** This follows the team's existing rule in `database/README.md` (SCRUM-48): a two-connection race test commits fixture rows, so it is "local only" on a disposable migrated database that is thrown away afterwards, and the script refuses non-loopback URLs. SCRUM-58 records its disposable-cluster runs the same way.

- Record the teammate's run as `AC3-N2 | … | Pass | <commit>, Disposable PostgreSQL <version>, migrations 0001–0028 | <who>, <date> | race test, local by team convention (database/README.md)`. Re-run it after `0028`, since the function changed.
- Do **not** write "shared Supabase" or "shared development" anywhere in that row or in the PR body for it.
- Shared Supabase gets only the rolled-back verify scripts (§6.5) and the live run (§8.4).
- Optional, recommended: turn the manual two-terminal steps into `database/tests/test_equipment_reservation_concurrency.py`, copying `test_event_status_history_concurrency.py` (two `psql` connections, loopback-only DSN guard, standard library only), so the race is repeatable rather than a one-off manual run.

### 8.3 F4 corrections

- Replace every `288daa9` with the commit actually tested (`48638ce` for the 14 Oct Green run, then this round's head).
- Replace "Claude (Sonnet 5.5)" with **"GLM (via <tool>), run by Yang Xue"** for the 14 Oct rows; future rows name whoever (or whichever agent) ran them.
- 14 Oct row environment: "Local, mocked: macOS, Python 3.14.2, `backend/equipmentService/.venv`".

### 8.4 Live authenticated workflow (L1, plus AC3-X1). Run by Yang.

Setup: `.env` with the shared dev `SUPABASE_URL`/keys; `docker compose up --build` (auth 8001, equipment 8002, event-request 8003, venue 8004 with `VENUE_STORAGE_BACKEND=supabase`). Accounts from `database/seed_test_accounts.sql` (password `12345678`, dev only). Use the branch head with `0028` applied. Prefix every row you create with `MANUAL-13`.

```bash
login() { curl -s localhost:8001/auth/login -H 'Content-Type: application/json' \
  -d "{\"email\":\"$1\",\"password\":\"12345678\"}" | jq -r .access_token; }
TSS=$(login technical_support@example.com)
VS=$(login venue_staff@example.com)
H="Authorization: Bearer $TSS"
```

| Step | Request | Expected | Proves |
| --- | --- | --- | --- |
| L1-1 | `GET :8004/venues/locations` with `$TSS` | 200, only `id`/`name`/`location` | D11 live |
| L1-2 | `GET :8004/venues` with `$TSS` | 403 | access not widened |
| L1-3 | `GET :8002/equipment-requirements?status=requested` with `$TSS` | 200; pick a requirement `REQ` (type `T`, quantity `Q`, event date from `event_date_times`) | TSS can find what to reserve |
| L1-4 | `POST :8002/equipment` with `$TSS`: type `T`, quantity `Q`+2, `home_location` = a venue name from L1-1 in another building | 201; note `ROW` | test stock |
| L1-5 | `POST :8002/equipment/availability-check` with `$TSS`, the event date, a venue id from L1-1, item `T` × `Q` | **200** (was 502 before the fix) | SCRUM-10 live |
| L1-6 | `POST :8002/equipment-reservations` with `$TSS`: `REQ`, `ROW`, quantity `Q`, event dates, venue id | **201**; `collection_date` = start − 2 (transfer day), `event_request_id` = the requirement's event, `created_by` = TSS id | AC1, AC4 live |
| L1-7 | `GET :8002/equipment-reservations/by-event/<event>` with `$TSS` | 200; the L1-6 row | AC4 read |
| L1-8 | Repeat L1-6 with quantity 1 | 409 "Exceeds the equipment requirement" | D3 live |
| L1-9 | Create a second `MANUAL-13` row of a different type; L1-6 with it | 422 "Equipment type does not match the requirement" | AC1-N5 live |
| L1-10 | SQL Editor: `select * from public.reserve_equipment('<REQ>', '<L1-9 row>', 1, '<d-1>', '<d>', '<TSS id>');` | error `22023`; no row | D12 live |
| L1-11 (AC3-X1) | `POST :8002/equipment/availability-check` for an overlapping event (same dates, same venue); then `GET :8002/equipment/<ROW>/status` | check: available = (`Q`+2) − `Q` = 2. Status: `available_quantity` 2 **only if today is inside the hold**, because the status endpoint reads today's date (`get_today`), not a query parameter. So run L1-6 for a one-day event **tomorrow**: with the transfer day the hold is yesterday → tomorrow, which contains today. The requirement's own event date does not have to match; the body's dates are what count (D1) | reservation visible to SCRUM-10/16 |
| L1-12 | Same reservation call with `$VS` (venue staff) | 403 | role guard live |

Save each request/response (redact tokens) to `docs/testcases/screenshots/scrum_13/live-2026-10-xx.md` or screenshots.

Cleanup (SQL Editor, service role): delete the `MANUAL-13` reservations by `equipment_id`, then move the `MANUAL-13` equipment rows to `RETIRED` through `PATCH /equipment/{id}/status` (equipment has history rows, so prefer retiring to deleting). Leave the requirement untouched.

---

## 9. Hand-offs

| To | What |
| --- | --- |
| Jaren (SCRUM-39) | Gate G1; add Technical Support "venue locations (id, name, building)" to the role matrix |
| koeiloo23 / Kennedy (venues) | Gate G1; review commit 2 |
| Heng Rui (SCRUM-64) | If the equipment-status trigger flags requirements, lock **requirement before equipment** like `reserve_equipment`, or the two can deadlock. Also: `reserve_equipment` now raises `22023` on a type mismatch. |
| SCRUM-58 owner | `reserve_equipment` refuses mismatched types (`22023`) as of `0028`; reservations are readable at `GET /equipment-reservations/by-event/{id}` |
| Teammate reviewer | Record their review under "Review" in the catalogue (testing.md §10) |

---

## 10. Definition of done for this round

- [ ] G1 agreed and recorded (who, date) under D11
- [ ] `dev` merged in; equipmentService 323 passed before any change
- [ ] Red recorded in the matrix for AC1-X3, X5, X6, X7, N10, N12 before each fix
- [ ] venueService `pytest -q` and `ruff check .` clean; new count recorded
- [ ] equipmentService `pytest -q` (including `test_venue_contract.py`) and `ruff check .` clean; new count recorded
- [ ] `0028` applied to shared dev; both verify scripts pass there; grants checked
- [ ] AC3-N2 re-run after `0028` on a disposable PostgreSQL database and labelled exactly so (no "shared" wording)
- [ ] Live workflow L1-1 to L1-12 and AC3-X1 recorded with environment "Live stack on shared Supabase"; `MANUAL-13` rows cleaned up
- [ ] F4 corrections made; every execution row names the commit actually tested and who ran it
- [ ] PR CI green on the head commit; PR body lists the evidence path and the venueService change
- [ ] Hand-off messages in §9 sent
