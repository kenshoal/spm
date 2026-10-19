# SCRUM-13 Implementation Plan: Reserve Equipment for an Event

Drafted 14 October 2026 by Claude (Cowork) for Yang Xue (story owner). **Status: approved by Yang Xue on 14 October 2026** (P1 to P3 resolved, see §8).

**Goal:** Technical Support reserves units of one catalogue row against a recorded equipment requirement, so the same units are never committed to two overlapping holds; Technical Support can list an event's reservations.

**Source of truth:** `docs/testcases/scrum_13_testcases.md` (AC1 to AC5, D1 to D10, approved 12 Oct). This plan only says *how* to make those tests pass; it adds no behaviour. J6/J7 (flag for review) are SCRUM-64 (Heng Rui).

**Branch:** `feat/scrum-13-reserve-equipment` from `origin/dev` (local `dev` is at `dd0036b`; `git pull` first). PR into `dev`.

**Red baseline (12 Oct):** `pytest -q` → 71 failed (13 `NotImplementedError`, 58 route 404s), 252 passed. Target: 323 passed, `ruff check .` clean.

---

## 0. Commit sequence (tests first)

The Red tests go in before any production code, one commit per test layer, so the PR history shows Red → Green (testing.md §2). Commits 1 to 4 are all on the branch before commit 5.

| # | Commit | Files | State after |
| --- | --- | --- | --- |
| 1 | `docs(scrum-13): add reservation test catalogue` | `docs/testcases/scrum_13_testcases.md` | — |
| 2 | `test(scrum-13): add Red unit tests for the per-row availability rule` | `tests/test_reservation_rules.py`, `app/availability.py` (the `row_available` stub only) | 13 unit runs Red (`NotImplementedError`) |
| 3 | `test(scrum-13): add Red API tests for reserving and listing reservations` | `tests/reservations_support.py`, `tests/test_reservations_api.py` | 58 API runs Red (route 404) |
| 4 | `test(scrum-13): add DB verification for reserve_equipment` | `database/verify_equipment_reservation_writes.sql` | Red until `0025` (function/column missing) |
| 5 | `feat(db): link reservations to requirements and add reserve_equipment (SCRUM-13)` | `0025`, `verify_equipment_reservations.sql`, `database/README.md` | DB scripts Green |
| 6 | `feat(equipment): per-row availability rule for reservations (SCRUM-13)` | `app/availability.py` | 13 unit runs Green |
| 7 | `feat(equipment): reserve and list equipment reservations (SCRUM-13)` | `app/routers/reservations.py`, `app/rpc_errors.py`, `app/main.py` | 323 passed |
| 8 | `docs(scrum-13): document endpoints and record Green run and DB evidence` | both READMEs, test catalogue | — |

Run `pytest -q` after commits 2 and 3 and paste the Red counts into the commit body (`13 failed` for the unit file, then `71 failed, 252 passed` for the whole service). Every commit message ends with the team's agent attribution lines.

---

## 1. Files touched

| File | Change |
| --- | --- |
| `database/migrations/0025_equipment_reservation_requirements.sql` | **New.** `requirement_id` column, two indexes, `reserve_equipment` RPC, grants |
| `database/verify_equipment_reservations.sql` | SCRUM-10 script: insert a requirement and pass `requirement_id` in its 6 inserts (regression called out in the test catalogue) |
| `database/README.md` | Row for `0025`; mention the new verify script |
| `backend/equipmentService/app/availability.py` | Replace the `row_available` stub; add `row_hold`; make `check_availability` call `row_available` |
| `backend/equipmentService/app/rpc_errors.py` | Add `reservation_rpc_error_to_http` |
| `backend/equipmentService/app/routers/reservations.py` | **New.** `POST /equipment-reservations`, `GET /equipment-reservations/by-event/{id}` |
| `backend/equipmentService/app/main.py` | `include_router(reservations.router)`; add SCRUM-13 to the description |
| `backend/equipmentService/README.md` | Two endpoint rows; note migration `0025` |
| `docs/testcases/scrum_13_testcases.md` | Green execution record, reviewer row |

Already written and **not to be edited** (unless a test is wrong, which needs your sign-off): `tests/test_reservation_rules.py`, `tests/test_reservations_api.py`, `tests/reservations_support.py`, `database/verify_equipment_reservation_writes.sql`.

---

## 2. Step 1: branch and commit the Red tests (commits 1 to 4)

```
# Already on dev with the test files uncommitted; they carry over to the new branch.
git pull && git switch -c feat/scrum-13-reserve-equipment
cd backend/equipmentService

git add ../../docs/testcases/scrum_13_testcases.md
git commit -m "docs(scrum-13): add reservation test catalogue"

git add tests/test_reservation_rules.py app/availability.py
pytest -q tests/test_reservation_rules.py    # expect 13 failed
git commit -m "test(scrum-13): add Red unit tests for the per-row availability rule"

git add tests/reservations_support.py tests/test_reservations_api.py
pytest -q                                    # expect 71 failed, 252 passed
git commit -m "test(scrum-13): add Red API tests for reserving and listing reservations"

git add ../../database/verify_equipment_reservation_writes.sql
git commit -m "test(scrum-13): add DB verification for reserve_equipment"
```

Do not add `.claude/` or `__pycache__/`. Before numbering the migration, run `ls database/migrations` on the pulled `dev` and confirm `0025` is still free (my remote refs are from 9 Oct). If taken, renumber and update every `0025` mention in the test catalogue and verify script.

---

## 3. Step 2: migration `0025` (AC1-N9, AC2-N2, AC3-N1, AC3-N2, AC4-H2)

```sql
-- Equipment reservations against requirements (SCRUM-13). Safe to re-run.
-- D7: every reservation names the requirement it fulfils; the event is copied
-- from the requirement by reserve_equipment, never supplied by the caller.

ALTER TABLE public.equipment_reservations
    ADD COLUMN IF NOT EXISTS requirement_id uuid
        REFERENCES public.equipment_requirements (id);

-- Guard only: the table should already be empty (P2). If not, stop rather
-- than delete someone's rows.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM public.equipment_reservations WHERE requirement_id IS NULL) THEN
        RAISE EXCEPTION '0025: equipment_reservations has rows with no requirement_id; remove them first';
    END IF;
END $$;

ALTER TABLE public.equipment_reservations ALTER COLUMN requirement_id SET NOT NULL;

-- Outstanding quantity per requirement (D3) and the per-event list (D9).
CREATE INDEX IF NOT EXISTS equipment_reservations_requirement_idx
    ON public.equipment_reservations (requirement_id);
CREATE INDEX IF NOT EXISTS equipment_reservations_event_idx
    ON public.equipment_reservations (event_request_id, created_at, id);

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
    -- P1: lock the requirement too, so two reservations against the same
    -- requirement from different rows cannot both pass the D3 check.
    -- Lock order: requirement, then equipment. No other function locks
    -- equipment then requirement, so this cannot deadlock.
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

    -- AC2 under the lock.
    IF v_equipment.operational_status <> 'AVAILABLE' THEN
        RAISE EXCEPTION 'equipment is %', v_equipment.operational_status USING ERRCODE = 'P0004';
    END IF;

    -- D3 under the lock: never over-reserve a requirement.
    SELECT coalesce(sum(quantity), 0) INTO v_held
    FROM public.equipment_reservations WHERE requirement_id = p_requirement_id;
    IF v_held + p_quantity > v_requirement.quantity THEN
        RAISE EXCEPTION 'exceeds requirement' USING ERRCODE = 'P0004';
    END IF;

    -- AC3 under the lock: units held on the row's busiest day in the window.
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

-- Same pattern as 0006/0013: server role only.
REVOKE ALL ON FUNCTION public.reserve_equipment(uuid, uuid, integer, date, date, uuid)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.reserve_equipment(uuid, uuid, integer, date, date, uuid)
    TO service_role;
```

Notes:
- Date maths (D-1, transfer day) stays in Python; the RPC trusts `p_collection_date`/`p_return_date` (0020's rule). Table CHECKs already cover `quantity > 0` and `return_date >= collection_date`.
- Type matching is **not** re-checked in SQL: Python does it with `norm()`, and a mismatch is a 422, not a lock conflict.

**Then:** update `verify_equipment_reservations.sql` (insert one `equipment_requirements` row for its event and add `requirement_id` to all 6 inserts), apply `0025` to the shared dev project, run both verify scripts (expect the `PASSED` notices), and do AC3-N2 with two `psql` sessions as the script's footer describes. Screenshot each for evidence.

Commit 5: `feat(db): link reservations to requirements and add reserve_equipment (SCRUM-13)`.

---

## 4. Step 3: the row rule in `app/availability.py` (13 unit runs)

Add one helper and replace the stub. Both reuse SCRUM-10's functions unchanged (D4).

```python
def row_hold(
    row: EquipmentRow, start_date: date, end_date: date,
    event_venue: Venue, venues: Sequence[Venue],
    transfer_days: int = TRANSFER_DAYS,
) -> tuple[date, date]:
    """Inclusive hold window for one row: D-1, plus the transfer day if the
    row is based in another building (D5). hold[0] is the collection_date."""
    transfer = needs_transfer(row.home_location, event_venue, venues)
    return hold_window(start_date, end_date, transfer, transfer_days)


def row_available(*, row, reservations, start_date, end_date,
                  event_venue, venues, transfer_days=TRANSFER_DAYS) -> int:
    if row.operational_status != "AVAILABLE":
        return 0
    hold_start, hold_end = row_hold(row, start_date, end_date, event_venue, venues, transfer_days)
    peak = committed_peak(row.id, reservations, hold_start, hold_end)
    return max(0, row.total_owned_quantity - peak)
```

Then make `check_availability`'s inner loop `available += row_available(...)` for each row whose `norm(row.type) == key`. That makes AC5-X1 true by construction, so SCRUM-10 and SCRUM-13 cannot drift. The 252 existing tests guard the refactor.

Run `pytest -q tests/test_reservation_rules.py tests/test_availability.py tests/test_availability_check.py` → all green.

Commit 6: `feat(equipment): per-row availability rule for reservations (SCRUM-13)`.

---

## 5. Step 4: the router `app/routers/reservations.py` (58 API runs)

### 5.1 Models

```python
class ReservationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")          # AC4-X1, AC4-X2
    requirement_id: UUID
    equipment_id: UUID
    quantity: int = Field(gt=0, le=2_147_483_647)      # AC1-B4, AC1-N1
    start_date: date
    end_date: date
    venue_id: str = Field(min_length=1)

    @model_validator(mode="after")                     # AC1-N2 end-before-start
    def _dates_ordered(self): ...

class ReservationOut(BaseModel):                        # exactly the 9 stored columns
    id: UUID; requirement_id: UUID; event_request_id: UUID; equipment_id: UUID
    quantity: int; collection_date: date; return_date: date
    created_by: UUID; created_at: str                  # str, as RequirementOut does
```

`created_at: str` matters: AC4-H1 and AC4-H3 compare the response to the stored dict with `==`, so the timestamp must round-trip byte for byte.

Router: `APIRouter(prefix="/equipment-reservations", tags=["equipment reservations"])`, `StaffDep = require_role(TECHNICAL_SUPPORT_ROLE)` for both endpoints. 401/403/422 then happen before any query or venue call (AC1-X1, AC1-X2, AC1-B4, AC1-N1, AC1-N2, AC4-N1, AC4-X3).

### 5.2 `POST ""` → 201, check order

Wrap every Supabase call in `try / except APIError` → 500 "Database operation failed" (AC1-N8 read). The RPC gets its own mapper (5.4).

| # | Step | Refusal | Cases |
| --- | --- | --- | --- |
| 1 | Read requirement: `table("equipment_requirements").select("id, event_request_id, equipment_type, quantity").eq("id", str(req_id)).limit(1)` | 404 "Equipment requirement not found" | AC1-N3, AC1-N8 |
| 2 | Read equipment row: `table("equipment").select(<5 cols>).eq("id", str(eq_id)).limit(1)` | 404 "Equipment not found" | AC1-N4 |
| 3 | `norm(row.type) != norm(req.equipment_type)` | 422 "Equipment type does not match the requirement" | AC1-N5, AC1-P3 |
| 4 | `operational_status != "AVAILABLE"` | 409 "Equipment not available" | AC2-P1–P4, AC2-X1 |
| 5 | Sum `quantity` of `equipment_reservations` with `.eq("requirement_id", str(req_id))`; refuse if `held + quantity > req.quantity` | 409 "Exceeds the equipment requirement" | AC1-B1–B3, AC1-P2 |
| 6 | `fetch_venues(authorization)`; find `venue_id` | 404 "Venue not found"; 502 from `fetch_venues` | AC1-N6, AC1-N7 |
| 7 | `hold_start, hold_end = row_hold(...)`; read the row's reservations: `.eq("equipment_id", str(eq_id)).lte("collection_date", hold_end.isoformat()).gte("return_date", hold_start.isoformat())` | — | AC3-H2 |
| 8 | `available = row_available(...)` on those rows; if `available < quantity` | 409 `{"message": "Insufficient equipment available", "requested", "available", "shortfall"}` | AC3-P3, AC5-H1, B1–B3, P1–P3, N1 |
| 9 | `client.rpc("reserve_equipment", {...})` with `p_collection_date = hold_start.isoformat()`, `p_return_date = end_date.isoformat()`, `p_created_by = user.id` | 5.4 | AC1-H1, AC2-N1, AC4-P1–P3 |
| 10 | Return `ReservationOut.model_validate(data)` (accept a dict or a one-item list) | — | AC4-H1 |

**Three traps the tests will catch:**
1. **Strings, not objects, in filters and RPC params.** AC3-H2 checks `("equipment_id", "eq", P10)` and `("collection_date", "lte", "2026-10-14")` by tuple equality, and AC1-H1 compares the RPC params dict exactly. Pass `str(uuid)` and `date.isoformat()`, never `UUID`/`date` objects.
2. **Window filter must be this row's hold**, not SCRUM-10's "widest" window, and use `.eq` on `equipment_id`, not `.in_`.
3. **Use `.limit(1)` rather than `.maybe_single()`** for single reads: the fake supports both, but real supabase-py returns `None` (not a response) from `maybe_single().execute()` on no rows in some versions, which would turn a 404 into a 500.

Why this order: cheap DB 404s and rule refusals come before the venueService call, and the requirement check (D3) runs before the shortfall so a request that breaks both reports the requirement first (no test pins this; it matches D10's listing order).

Note `Header` for `authorization`: declare `authorization: Annotated[str | None, Header()] = None` (the role dependency already rejected a missing header).

### 5.3 `GET /by-event/{event_request_id}` → 200

`event_request_id: UUID` path param (AC4-N1 422 before any query). Query `table("equipment_reservations").select("*").eq("event_request_id", str(id)).order("created_at").order("id")`; return `[ReservationOut.model_validate(r) for r in data]`. Empty list is fine (AC4-P4). `APIError` → 500.

### 5.4 `rpc_errors.reservation_rpc_error_to_http`

| Code | HTTP | Detail | Case |
| --- | --- | --- | --- |
| `P0004` | 409 | "Equipment no longer available" | AC2-N1 (D6) |
| `P0002` | 404 | "Equipment or requirement not found" (only reachable in a race; untested) | — |
| anything else | 500 | "Database operation failed" | AC1-N8 rpc |

### 5.5 Wire up

`main.py`: `from app.routers import availability, equipment, requirements, reservations, status` and `app.include_router(reservations.router)`.

Run `pytest -q` from `backend/equipmentService/` → 323 passed; `ruff check .` clean.

Commit 7: `feat(equipment): reserve and list equipment reservations (SCRUM-13)`.

---

## 6. Step 5: docs and evidence

- `backend/equipmentService/README.md`: rows for both endpoints (body, 201/200, every error code from D10), needs migration `0025`.
- `database/README.md`: `0025` row, applied date, verify script.
- `docs/testcases/scrum_13_testcases.md`: replace the Red record with the Green run (commit hash, counts, environment), mark the DB rows executed with the date, add AC3-X1 result.
- **AC3-X1 (manual integration)** on the full stack: reserve 5 of a 10-unit `MANUAL-` row for Wed 14; `POST /equipment/availability-check` for an overlapping event → 5 available; `GET /equipment/{id}/status` on a day inside the hold → `available_quantity` 5. Delete the `MANUAL-` rows after.
- Commit 8: `docs(scrum-13): document endpoints and record Green run and DB evidence`.

---

## 7. Definition of done

- [ ] 323 passed, 0 failed; `ruff check .` clean; CI green on the PR
- [ ] `0025` applied to shared dev; both verify scripts pass; AC3-N2 two-session run recorded
- [ ] AC3-X1 manual integration recorded
- [ ] Team-member review of the AI-drafted test cases recorded under "Review" (testing.md §10)
- [ ] PR into `dev` reviewed; SCRUM-13 → Done; comment on SCRUM-39 that its AC7 is closed by `GET /equipment-reservations/by-event/{id}`; tell SCRUM-64 (Heng Rui) and SCRUM-58/60 owners the table now has `requirement_id`

---

## 8. Decisions confirmed by Yang (14 October 2026)

| ID | Point | Decision |
| --- | --- | --- |
| P1 | D6 locked only the equipment row, so two reservations against the same requirement from different rows could both pass D3. | **Lock the requirement row as well**, before the equipment row (drafted in §3). Record as D6a in the test catalogue in commit 8. |
| P2 | `0025` makes `requirement_id` NOT NULL; existing rows without one would block it. | **Table expected empty** (old test rows were deleted). Keep the guard; run `SELECT count(*) FROM equipment_reservations;` before applying to confirm 0. |
| P3 | Can a requirement already marked `arranged` still take reservations? | **Yes.** Arrangement status is not a lock on reservations (D8); no status check in the API or the RPC. |
