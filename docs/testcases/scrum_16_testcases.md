# SCRUM-16 Test Cases: Maintain Equipment Status

Last reviewed: 2 October 2026

Catalogue for the equipment-status story (Jira status: Done, 20 September 2026). The matrix retro-fits the existing `equipmentService` and frontend suites to the acceptance criteria and adds the cases that were missing. Companion catalogue: [scrum_45_testcases.md](scrum_45_testcases.md).

## Story contract

- **Jira key:** [SCRUM-16](https://is212g9t4.atlassian.net/browse/SCRUM-16), "Maintain Equipment Status". Related: SCRUM-27 (Authorise Access by Role).
- **User story:** As a Technical Support Staff member, I want to update the operational status of equipment, so that damaged or unavailable equipment is never treated as available.

### Acceptance criteria

Verbatim from Jira (checklist form):

1. Technical Support Staff can mark an equipment item/type as unavailable (e.g., due to damage, repair, or maintenance).
2. Given equipment set to damaged/repair/maintenance, when availability is checked, then that equipment is excluded from available quantity.
3. Each status change records who made it and when.

Scenario form used by the matrix (same scope; **proposed wording, pending story-owner approval**):

- **AC1:** Given an equipment item exists and the caller is Technical Support Staff, when they change its status to `DAMAGED`, `UNDER_REPAIR` or `UNDER_MAINTENANCE` (optionally with a reason of up to 255 characters), then the new status is saved and returned.
- **AC2:** Given an equipment item whose status is not `AVAILABLE`, when anyone checks its availability, then it reports `available=false` and an available quantity of 0.
- **AC3:** Given an equipment item's status has changed, when its status history is read, then each change lists the old and new status, the reason, who made it and when, newest first.

### Scope and rules

- **Actors:** Technical Support Staff (status changes); any authenticated user (availability and history reads). The event coordinator is the denied role; an Operations Manager who also holds `technical_support` is allowed through the roles list.
- **Allowed transitions:** the API accepts any `OperationalStatus` value. Whether some transitions are illegal (for example `RETIRED → AVAILABLE`) is an open question; see below.
- **Persistence:** the status write and the history insert happen atomically inside the `transition_equipment_status` database RPC (`database/migrations/0002_transition_equipment_status.sql`).
- **Excluded:** reservations reducing available quantity belong to SCRUM-10 (named, not claimed).

## How to run the suites

| Area | Command | Automated cases |
| --- | --- | ---: |
| Backend, whole service | `pytest -q` from `backend/equipmentService/` | 64 |
| Backend, this story | `pytest tests/test_status.py -q` from `backend/equipmentService/` | 31 |
| Frontend unit, this story | `npx vitest run __tests__/equipment-status.test.tsx __tests__/equipment-actions.test.ts` from `frontend/` | 13 (7 for SCRUM-16) |
| End-to-end, this story | `npx playwright test e2e/equipment-status.spec.ts` from `frontend/` | 1 |

Every automated test carries a label comment with its ID, e.g. `# AC1-N1 (negative): …`.

## Acceptance-criterion test matrix

| ID | AC | Test scenario | Technique | Pre-conditions | Test steps | Test data | Expected result and forbidden side effects | Layer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AC1-H1 | AC1 | A damaged item is marked `DAMAGED` with a reason | Happy | Equipment exists; caller is technical support | `PATCH /equipment/{id}/status` | `new_status=DAMAGED`, reason "Dropped during setup" | `200`; body echoes id, new status, caller and reason; RPC called once with exactly those parameters | API component |
| AC1-H2 | AC1 | The status form sends the new status and the trimmed reason | Happy | Signed in as technical support; equipment is `AVAILABLE` | Submit the status form action | `new_status=DAMAGED`, reason "  Cracked lens " | `PATCH` to the equipment service with reason "Cracked lens"; confirmation "Status changed to Damaged." | Frontend unit |
| AC1-H3 | AC1, AC2, AC3 | Marking equipment damaged removes it from availability and records the change | Happy | Mock services running; signed in as `playwright-tech` | Create equipment (quantity 5), change status to Damaged with a reason | reason "Blown driver" | Confirmation shown; equipment shown as not available; newest history entry shows "Available → Damaged", the reason and `playwright-tech`; Damaged no longer offered | E2E |
| AC1-P1 | AC1 | Reason is optional | Partition | As AC1-H1 | `PATCH` without `reason` | `new_status=UNDER_REPAIR` | `200`; `reason` is `null` in body and RPC payload | API component |
| AC1-P2 | AC1 | `UNDER_MAINTENANCE` is an accepted target | Partition | As AC1-H1 | `PATCH` | `new_status=UNDER_MAINTENANCE` | `200`; RPC payload carries the new status | API component |
| AC1-P3 | AC1 | `RETIRED` is an accepted target | Partition | As AC1-H1 | `PATCH` | `new_status=RETIRED` | `200`; RPC payload carries the new status (see the transition-legality question) | API component |
| AC1-P4 | AC1 (clarify) | Repaired equipment can be returned to `AVAILABLE` | Partition | As AC1-H1 | `PATCH` | `new_status=AVAILABLE`, reason "Repair completed" | `200`; RPC called once with `AVAILABLE` and the reason. AC1 as written covers only marking unavailable; see open questions | API component |
| AC1-P5 | AC1 | The status picker offers every status except the current one | Partition | Equipment is `AVAILABLE` | Render the status form | — | Options are Damaged, Under repair, Under maintenance, Retired | Frontend unit |
| AC1-B1 | AC1 | Reason of exactly 255 characters is accepted | Boundary | As AC1-H1 | `PATCH` | reason = "x" × 255 | `200`; RPC payload carries the full reason | API component |
| AC1-B2 | AC1 | Reason of 256 characters is refused | Boundary | As AC1-H1 | `PATCH` | reason = "x" × 256 | `422`; no RPC call | API component |
| AC1-B3 | AC1 | The form refuses a 256-character reason before sending | Boundary | As AC1-H2 | Submit the status form action | reason = "x" × 256 | "Keep the reason to 255 characters or fewer."; input echoed back; no request sent | Frontend unit |
| AC1-N1 | AC1 | Unknown status value is refused | Negative | As AC1-H1 | `PATCH` | `new_status=ON_FIRE` | `422`; no RPC call | API component |
| AC1-N2 | AC1 | Malformed equipment id is refused | Negative | As AC1-H1 | `PATCH` | id = `not-a-uuid` | `422`; no RPC call | API component |
| AC1-N3 | AC1 | Unknown equipment returns 404, keyed on errcode | Negative | RPC raises `P0002` | `PATCH` | `new_status=RETIRED` | `404` with detail "Equipment not found" | API component |
| AC1-N4 | AC1 | 404 keys off errcode `P0002`, not message text | Negative | RPC raises `P0001` with message "equipment not found" | `PATCH` | `new_status=RETIRED` | `500` (regression: message text must not decide the mapping) | API component |
| AC1-N5 | AC1 | RPC failure is a 500, not a crash | Negative | RPC raises a generic `APIError` | `PATCH` | `new_status=DAMAGED` | `500` "Database operation failed" | API component |
| AC1-N6 | AC1 | The form refuses an unchanged or unknown status | Negative | Equipment is `DAMAGED` | Submit the status form action twice | `new_status=DAMAGED`; `new_status=LOST` | "Choose a different status." both times; no request sent | Frontend unit |
| AC1-N7 | AC1 | An overlong reason is echoed back trimmed | Negative | As AC1-H2 | Submit the status form action | reason = 2 spaces + "y" × 260 + 2 spaces | Error message; the trimmed reason is returned for correction; no request sent | Frontend unit |
| AC1-X1 | AC1 | Status change requires a session | Cross-cutting | No Authorization header | `PATCH` | `new_status=DAMAGED` | `401`; no RPC call | API component |
| AC1-X2 | AC1 | Event coordinator may not change status | Cross-cutting | Caller holds only `event_coordinator` | `PATCH` | `new_status=DAMAGED` | `403`; no RPC call | API component |
| AC2-H1 | AC2 | Available equipment reports its quantity | Happy | Row is `AVAILABLE`, quantity 4 | `GET /equipment/{id}/status` | — | `200`; `available=true`, `available_quantity=4` | API component |
| AC2-P1 | AC2 | `DAMAGED` is excluded from availability | Partition | Row is `DAMAGED` | `GET` status | — | `200`; `available=false`, `available_quantity=0` | API component |
| AC2-P2 | AC2 | `UNDER_REPAIR` is excluded from availability | Partition | Row is `UNDER_REPAIR` | `GET` status | — | `200`; `available=false`, `available_quantity=0` | API component |
| AC2-P3 | AC2 | `UNDER_MAINTENANCE` is excluded from availability | Partition | Row is `UNDER_MAINTENANCE` | `GET` status | — | `200`; `available=false`, `available_quantity=0` | API component |
| AC2-P4 | AC2 | `RETIRED` is excluded from availability | Partition | Row is `RETIRED` | `GET` status | — | `200`; `available=false`, `available_quantity=0` | API component |
| AC2-B1 | AC2 | Zero owned quantity is the availability floor | Boundary | Row is `AVAILABLE`, quantity 0 | `GET` status | — | `200`; `available=true`, `available_quantity=0` | API component |
| AC2-N1 | AC2 | Unknown equipment is 404 | Negative | No row for the id | `GET` status | — | `404` "Equipment not found" | API component |
| AC2-N2 | AC2 | Malformed equipment id is refused | Negative | — | `GET` status | id = `not-a-uuid` | `422` | API component |
| AC2-X1 | AC2 | Availability lookup requires a session | Cross-cutting | No Authorization header | `GET` status | — | `401` | API component |
| AC2-X2 | AC2 | Malformed Authorization headers are refused | Cross-cutting | Header variants: `Basic abc`, `Bearer `, `Bearer a b`, `Bearer` | `GET` status | — | `401` for every variant | API component |
| AC3-H1 | AC3 | History lists each change with who and when, newest first | Happy | Equipment exists; two history rows seeded | `GET /equipment/{id}/status/history` | rows with id 1, 2 | `200`; both rows with old/new status, reason, `changed_by`, `changed_at`; newest first; query ordered by `changed_at` | API component |
| AC3-H2 | AC3 | Each history entry shows the change, reason, who and when | Happy | One history entry | Render the history list | `AVAILABLE → DAMAGED`, reason "Dropped", `tech-1`, 20 Sep 2026 | The entry shows "Available → Damaged", "Dropped", `tech-1` and the date | Frontend unit |
| AC3-P1 | AC3 | Equipment with no changes returns an empty history | Partition | Equipment exists, no history rows | `GET` history | — | `200` with `[]` (a valid result, not an error) | API component |
| AC3-P2 | AC3 | An empty history shows an explanatory message | Partition | No history entries | Render the history list | — | "No status changes recorded yet." | Frontend unit |
| AC3-N1 | AC3 | History of unknown equipment is 404 | Negative | No row for the id | `GET` history | — | `404` | API component |
| AC3-X1 | AC3 | History requires a session | Cross-cutting | No Authorization header | `GET` history | — | `401` | API component |

## Latest execution record

Run 2 October 2026 on branch `test/equipment-test-traceability`, base commit `1ce75d6` plus uncommitted changes. Environment: Linux verification environment, Python 3.11.15 (CI uses 3.12), Node 22.22.2. Dependencies **fully mocked**: `FakeSupabase` replaces the database, the authService `/auth/me` call is stubbed, and the frontend tests stub `fetch`.

| ID | Automation status | Actual result | Execution status | Remarks and evidence |
| --- | --- | --- | --- | --- |
| AC1-H1, AC1-P1–P4, AC1-B1, AC1-B2, AC1-N1–N5, AC1-X1, AC1-X2 | Green | As expected | Pass | `tests/test_status.py` |
| AC2-H1, AC2-P1–P4, AC2-B1, AC2-N1, AC2-N2, AC2-X1, AC2-X2 | Green | As expected | Pass | `tests/test_status.py` (AC2-P2–P4 parametrized; AC2-X2 four header variants) |
| AC3-H1, AC3-P1, AC3-N1, AC3-X1 | Green | As expected | Pass | `tests/test_status.py` |
| AC1-H2, AC1-B3, AC1-N6, AC1-N7 | Green | As expected | Pass | `frontend/__tests__/equipment-actions.test.ts` |
| AC1-P5, AC3-H2, AC3-P2 | Green | As expected | Pass | `frontend/__tests__/equipment-status.test.tsx` |
| AC1-H3 | Green (last CI run) | — | Blocked | `frontend/e2e/equipment-status.spec.ts`. The production build could not fetch Google Fonts in the verification environment, so the web server did not start. Re-run locally or rely on pull-request CI. |

Totals: backend `pytest -v` 64 passed, 0 failed, 0 skipped; `ruff check .` all checks passed; frontend Vitest 13 passed (2 files); Playwright not executed. These results prove the API and component layers only; see the database limitation below.

**Definition of Done status:** Partially verified. The database-layer check of AC3 is outstanding, and the end-to-end journey was not executed on the current code.

## Assumptions and open questions

- **Clarify AC1 (returning to `AVAILABLE`).** AC1 as written only covers marking equipment unavailable, but the user story says "update the operational status" and the API accepts `AVAILABLE`. AC1-P4 tests the current behaviour. Ask the story owner to confirm AC1 includes returning repaired equipment to `AVAILABLE`, or to move it to its own story.
- **Transition legality.** The database RPC (`migrations/0002`) accepts any status with no transition table, so `RETIRED → AVAILABLE` succeeds silently, and any RPC refusal other than errcode `P0002` surfaces as `500`. Whether illegal transitions are a business rule is a team decision; if agreed, the new cases and the RPC change go back through the AC review gate.
- **AC3's core assertion lives in the database.** The API tests prove the RPC is called with the right `p_changed_by` and `p_reason`, but the "records who and when" write is the history insert inside the RPC. No database-layer test exists yet; `database/verify_equipment_functions.sql` is the current manual check. A transaction-rollback database test remains outstanding.
- **`AVAILABLE` with quantity 0** reports `available: true, quantity: 0` (AC2-B1). This reflects the code's row-level semantics; confirm with the Product Owner that zero-owned equipment should still count as available.
- **Frontend reason limit.** The form tests the refused side (256, AC1-B3) but not the accepted side (255); the backend covers both (AC1-B1, AC1-B2).
