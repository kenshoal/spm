# SCRUM-45 Test Cases: Maintain the Equipment Catalogue

Last reviewed: 2 October 2026

Catalogue for the equipment-catalogue story. The acceptance criteria below are
taken verbatim from Jira SCRUM-45 (story marked Done 20 September 2026); the
matrix retro-fits the existing `equipmentService` suite to them and adds the
cases that were missing. Companion catalogue: [scrum_16_testcases.md](scrum_16_testcases.md).

## Story contract

- **Jira key:** SCRUM-45 — "Maintain the Equipment Catalogue".
- **User story:** As a Technical Support staff, I want to maintain each equipment's information in the catalogue, so that I can review requested equipment and update the catalogue.
- **Actors:** Technical Support Staff (create, quantity update), any authenticated user (view/list). The event coordinator is the denied partition; an Operations Manager who also holds `technical_support` is allowed through the roles list.
- **Persistence:** create and quantity update are atomic database RPCs (`create_equipment`, `update_equipment_quantity`) with errcode-based 404 mapping.
- **Excluded:** how reservations consume quantity is SCRUM-10 (named, not claimed).

## How to run the suite

| Area | Command (run from `backend/equipmentService/`) | Current automated cases |
| --- | --- | ---: |
| Whole service suite | `.venv/bin/python -m pytest -q` | 63 |
| This story's endpoints | `.venv/bin/python -m pytest tests/test_equipment.py -q` | 33 |

## Acceptance-criterion test matrix

| ID | AC | Test scenario | Technique | Pre-conditions | Test steps | Test data | Expected result and forbidden side effects | Layer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AC1-H1 | AC1 | Create a record with every attribute | Happy | Caller is technical support; RPC returns the created row | `POST /equipment` | type Speaker, description, quantity 4, location "Store Room B" | `201`; row echoed; RPC called once with exactly the six expected parameters incl. caller id and default status `AVAILABLE` | API component |
| AC1-P1 | AC1 | A matching role inside the roles list is enough | Partition | Caller holds manager + technical support | `POST` | minimal payload | `201` | API component |
| AC1-P2 | AC1 | Explicit non-default operational status | Partition | As AC1-H1 | `POST` | `operational_status=DAMAGED` | `201`; response and RPC payload carry `DAMAGED` | API component |
| AC1-P3 | AC1 | Description is optional | Partition | As AC1-H1 | `POST` without description | — | `201`; response and RPC payload carry `description=null` | API component |
| AC1-B1 | AC1 | Type of exactly 120 characters is accepted | Boundary | As AC1-H1 | `POST` | type = "S" × 120 | `201`; RPC payload carries the full type | API component |
| AC1-B2 | AC1 | Type of 121 characters is refused | Boundary | As AC1-H1 | `POST` | type = "S" × 121 | `422`; no RPC call | API component |
| AC1-B3 | AC1 | Home location of exactly 120 characters is accepted | Boundary | As AC1-H1 | `POST` | home_location = "S" × 120 | `201`; RPC payload carries the full location | API component |
| AC1-B4 | AC1 | Home location of 121 characters is refused | Boundary | As AC1-H1 | `POST` | home_location = "S" × 121 | `422` | API component |
| AC1-N1 | AC1 | Negative quantity is refused | Negative | As AC1-H1 | `POST` | `total_owned_quantity=-1` | `422` | API component |
| AC1-N2 | AC1 | Missing required fields are refused | Negative | As AC1-H1 | `POST` | only `type` | `422` | API component |
| AC1-X1 | AC1 | Create requires a session | Cross-cutting | No Authorization header | `POST` | minimal payload | `401` | API component |
| AC1-X2 | AC1 | Event coordinator may not create | Cross-cutting | Caller holds only `event_coordinator` | `POST` | minimal payload | `403` | API component |
| AC2-H1 | AC2 | Quantity update reaches the atomic RPC | Happy | Caller is technical support; RPC returns updated row | `PATCH /equipment/{id}/quantity` | quantity 4 → 6 | `200`; response carries 6; RPC called with id, new quantity and caller | API component |
| AC2-B1 | AC2 | Zero is the accepted floor | Boundary | As AC2-H1 | `PATCH` | `total_owned_quantity=0` | `200`; response carries 0 | API component |
| AC2-N1 | AC2 | Negative quantity is refused | Negative | As AC2-H1 | `PATCH` | `total_owned_quantity=-3` | `422`; no RPC call (state unchanged) | API component |
| AC2-N2 | AC2 | Unknown equipment is 404 | Negative | RPC raises `P0002` | `PATCH` | quantity 6 | `404` "Equipment not found" | API component |
| AC2-N3 | AC2 | RPC failure is a 500, not a crash | Negative | RPC raises `P0001` | `PATCH` | quantity 6 | `500` "Database operation failed" | API component |
| AC2-X1 | AC2 | Quantity update requires a session | Cross-cutting | No Authorization header | `PATCH` | quantity 6 | `401` | API component |
| AC2-X2 | AC2 | Event coordinator may not update quantity | Cross-cutting | Caller holds only `event_coordinator` | `PATCH` | quantity 6 | `403` | API component |
| AC3-H1 | AC3 | The catalogue lists records with current attributes | Happy | One row seeded | `GET /equipment` | — | `200`; row with id and operational status | API component |
| AC3-H2 | AC3 | A single record shows its current attributes | Happy | Row seeded | `GET /equipment/{id}` | — | `200`; row with id | API component |
| AC3-P1 | AC3 | List filters by type and operational status | Partition | Row seeded | `GET /equipment` with filters | `type=Speaker`, `operational_status=AVAILABLE` | `200`; both eq-filters requested on the query | API component |
| AC3-N1 | AC3 | Empty catalogue lists as `200 []`, not an error | Negative | Catalogue is empty | `GET /equipment` | — | `200` with `[]` | API component |
| AC3-N2 | AC3 | Invalid status filter value is refused | Negative | — | `GET /equipment` | `operational_status=BOGUS` | `422` | API component |
| AC3-N3 | AC3 | Unknown equipment id is 404 | Negative | No row for the id | `GET /equipment/{id}` | — | `404` | API component |
| AC3-N4 | AC3 | Malformed equipment id is refused | Negative | — | `GET /equipment/{id}` | id = `not-a-uuid` | `422` | API component |
| AC3-X1 | AC3 | Listing requires a session | Cross-cutting | No Authorization header | `GET /equipment` | — | `401` | API component |
| AC3-X2 | AC3 | Malformed Authorization headers are refused | Cross-cutting | Header variants: `Basic abc`, `Bearer `, `Bearer a b`, `Bearer` | `GET /equipment` | — | `401` for every variant | API component |
| AC4 | AC4 | Catalogue updates are visible to availability checks | Cross-cutting | Quantity change applied (AC2-H1/AC2-B1) | `GET /equipment/{id}/status` after the update | quantity 0 | `available_quantity` reflects the updated total (proved by SCRUM-16 AC2-H1/AC2-B1 against the same row) | API component |

## Latest execution record

| Check | Command (run from `backend/equipmentService/`) | Result |
| --- | --- | --- |
| Whole suite | `.venv/bin/python -m pytest -q` | 63 passed, 1 warning, 0.10s |
| Lint | `.venv/bin/ruff check .` | All checks passed |

Run 2 October 2026 on the working tree of `docs/agent-guide-and-standards`.
Environment: local, **fully mocked** — `FakeSupabase` replaces the database and
`httpx.get` to authService's `/auth/me` is stubbed. These results prove the API
layer only.

## Assumptions and open questions

- **AC4's reservation half is not claimable here.** Updates flowing into
  reservations depends on SCRUM-10's booking logic; the matrix records only the
  availability half, which this service owns. Per the standards the dependency
  is named, not claimed.
- **Filter semantics are only checked as "requested", not applied.** The fake
  query builder records `eq()` calls but does not filter the seeded rows, so
  AC3-P1 proves the filters are requested, not that the database would apply
  them. The real filtering behaviour needs the live verification check
  (`database/verify_equipment_functions.sql` pattern) to stay trustworthy.
- **No DB-layer tests exist yet** for the `create_equipment` /
  `update_equipment_quantity` RPCs' constraints (audit trail, quantity floor at
  the database). Same outstanding item as SCRUM-16 AC3.

## Release 1 hotfix test cases (added 6 November 2026)

These cases belong to this story and are labelled in the automated tests, but until now they were specified only in summary on the hotfix page (`release_1_hotfixes_testcases.md`). They are recorded here so the story document, the code labels and `TestCaseLookup.xlsx` agree; the IDs are the lookup sheet's, with the hotfix number prefixed to the case ID. They were executed as part of the hotfix verification runs recorded on that page (1 and 3 November 2026); per-case results are not restated in this document.

Hotfix H1 — A quantity could be cut below the units already reserved.

| ID | AC | Test scenario | Technique | Expected result | Layer | Automated test |
| --- | --- | --- | --- | --- | --- | --- |
| H1 AC2-B1 | AC2 (Jira, 1 Nov) | Exactly the peak is allowed | Boundary | Exactly the peak is allowed | Database | database/verify_release_1_hotfixes_2.sql:233 |
| H1 AC2-B2 | AC2 (Jira, 1 Nov) | One below the peak is refused | Boundary | One below the peak is refused | Database | database/verify_release_1_hotfixes_2.sql:238 |
| H1 AC2-B3 | AC2 (Jira, 1 Nov) | Two reservations that start the same day are each counted once | Boundary | Two reservations that start the same day are each counted once | Database | database/verify_release_1_hotfixes_2.sql:252 |
| H1 AC2-N1 | AC2 (Jira, 1 Nov) | Below the peak (7) is refused and nothing changes | Negative | Below the peak (7) is refused and nothing changes | Database | database/verify_release_1_hotfixes_2.sql:224 |
| H1 AC2-N4 | AC2 (Jira, 1 Nov) | A total below the units already reserved is refused as a conflict (409) with a reason the member can act on | Negative | A total below the units already reserved is refused as a conflict (409) with a reason the member can act on | API | backend/equipmentService/tests/test_equipment.py::test_update_quantity_below_reserved_is_a_conflict |
| H1 AC2-P1 | AC2 (Jira, 1 Nov) | An increase is never refused | Partition | An increase is never refused | Database | database/verify_release_1_hotfixes_2.sql:243 |
| H1 AC2-P2 | AC2 (Jira, 1 Nov) | Reservations that have already been returned do not hold the total up | Partition | Reservations that have already been returned do not hold the total up | Database | database/verify_release_1_hotfixes_2.sql:246 |
| H1 AC2-P3 | AC2 (Jira, 1 Nov) | Zero stays allowed when nothing is reserved ahead | Partition | Zero stays allowed when nothing is reserved ahead | Database | database/verify_release_1_hotfixes_2.sql:263 |
