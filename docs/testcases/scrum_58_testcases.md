# SCRUM-58 — Plan and Confirm an Event

Source: [Jira SCRUM-58](https://is212g9t4.atlassian.net/browse/SCRUM-58), read 13 October 2026. Branch: `feat/scrum-58-plan-and-confirm`, base `11dae05`.

## Approved contract

As the event's coordinator, I want to move an approved event into planning and then send it for its safety check once everything is booked, so that everyone can see which events are going ahead.

The story owner (Tate) reviewed the four Jira ACs and approved the scope below on 13 October 2026. Jira wording is kept; the rewording below is recorded here, not written back to Jira.

| Jira AC | Outcome | Approved wording |
| --- | --- | --- |
| The coordinator can move an approved event into planning. | **Keep, clarified** | **AC1:** Given an Approved event assigned to me, when I start planning, then its status becomes Planning and the status history records me (role `event_coordinator`, source `coordinator.planning`) as the actor. |
| Once all of the event's venue bookings are approved and its equipment is reserved, the coordinator can send it for the safety check. | **Parked** | **AC2:** not built yet. No status for "waiting for safety check" exists, and who moves the event to Confirmed is undecided. Asked Jaren (SCRUM-60) on 13 Oct. Also open: does an event with no venue bookings pass? |
| If anything is still waiting, missing or marked for review, the system says what and doesn't send it. | **Parked** | **AC3:** not built yet. Needs the "marked for review" flag from SCRUM-64 (Heng Rui) and equipment reservation from SCRUM-13 (Yang Xue). |
| Only the event's own coordinator can do this. Anyone else is stopped, and nothing changes. | **Keep, clarified** | **AC4:** Given an event assigned to coordinator A, when anyone else tries to start planning (another or a reassigned-away coordinator, an organiser, an operations manager, or a caller with no session), then they are refused (403, or 401 without a session) and the status and history do not change. |

The story title says "Confirm", but no Jira AC confirms an event. That gap is part of the AC2 question to SCRUM-60.

## Scope

- **Included (this increment):** AC1 and AC4 for the Approved → Planning move only. Endpoint `POST /event-requests/{id}/planning`.
- **Excluded:** AC2, AC3 (parked above); Safety Officer check and confirmation (SCRUM-60); registration for confirmed events (SCRUM-21); notifications about the move (SCRUM-57); frontend control (later increment of this story).

## Actors and permissions

Only the coordinator on the **latest** assignment row (ordered by `id`) may start planning. The database function rechecks this under a row lock at write time, so a coordinator reassigned away between page load and click is refused. Browser roles (`anon`, `authenticated`) cannot execute the function.

## Allowed transition

| From | To | Who | Otherwise |
| --- | --- | --- | --- |
| Approved | Planning | Latest assigned coordinator | 409 `P0004` from any other status; 403 `P0003` for anyone else; 404 `P0002` if missing |

## Persistence and atomicity

`advance_event_request_by_coordinator` (migration `0026_event_request_planning.sql`, which replaces the `0025` definition) locks the event row, checks assignment and status, sets the history actor and updates status in one transaction. The SCRUM-48 trigger writes exactly one history row per real status change; a refused call writes none.

## Assumptions and open questions

1. AC2 target status and confirmer — asked Jaren, 13 Oct.
2. Shape of the "marked for review" flag — asked Heng Rui, 13 Oct.
3. Planning may still be cancelled by the coordinator (already allowed since migration `0012`); unchanged here.

## Test case specification

| ID | AC | Test scenario | Technique | Pre-conditions | Test steps | Test data | Expected result | Forbidden side effects | Layer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AC1-H1 | AC1 | The assigned coordinator can start planning an approved event | Happy | Approved request assigned to `coord-1` (`make_assigned_client`) | POST `/event-requests/{id}/planning` as `coord-1` | status `Approved` | 200, body status `Planning`, stored status `Planning` | — | API |
| AC1-P1…P8 | AC1 | Planning applies only to Approved; every other assigned status is refused | Partition | Request in the given status assigned to `coord-1` | POST `/planning` as `coord-1` | Submitted, Under Review, Changes Requested, Rejected, Planning, Confirmed, Completed, Cancelled | 409 | Status unchanged | API |
| AC1-N1 | AC1 | A request that does not exist is reported, not guessed | Negative | Empty repository | POST `/planning` as `coord-1` | id `00000000-…-0001` | 404 | — | API |
| AC1-X1 | AC1 | The real database function moves Approved → Planning and records one history row naming the coordinator | Cross-cutting | Disposable local cluster bootstrapped with SCRUM-48 fixtures + `0025`, `0026` | Call the function as `service_role` inside a rolled-back transaction | Approved fixture event, its assigned coordinator | Status `Planning`; one new history row `Approved → Planning`, actor = coordinator, role `event_coordinator`, source `coordinator.planning` | Rolled back | DB |
| AC4-N1 | AC4 | A coordinator who is not assigned is refused | Negative | Approved request assigned to `coord-2` | POST `/planning` as `coord-1` | — | 403 | Status stays `Approved` | API |
| AC4-N2 | AC4 | A coordinator reassigned away is refused (latest assignment wins) | Negative | Approved request assigned to `coord-1`, then `coord-2` | POST `/planning` as `coord-1` | — | 403 | Status stays `Approved` | API |
| AC4-N3 | AC4 | No coordinator assigned at all | Negative | Approved request, no assignment | POST `/planning` as `coord-1` | — | 403 | Status stays `Approved` | API |
| AC4-N4 | AC4 | No session | Negative | Real auth dependency | POST `/planning` with no header | — | 401 | — | API |
| AC4-N5, N6 | AC4 | Organiser and operations manager roles are refused even if their ID matches the assignment | Negative | Auth stubbed to the given role | POST `/planning` | `event_organiser`; `event_operations_manager` | 403 | Status unchanged | API |
| AC4-N7 | AC4 | A refused database call writes no history and changes nothing | Negative | As AC1-X1 | Call the function as a different coordinator | — | `P0003`; status `Approved` | No new history row | DB |
| AC4-N8 | AC4 | Browser roles cannot call the function directly | Negative | As AC1-X1 | `has_function_privilege` for `anon`, `authenticated` | — | false for both | — | DB |

## Latest execution record

| ID | Automation status | Actual result | Execution status | Build or commit | Executed by and date | Remarks and evidence |
| --- | --- | --- | --- | --- | --- | --- |
| AC1-H1 | Green | 200, status Planning, stored Planning | Pass | branch on `11dae05`, local, repositories faked | Claude for Tate, 13 Oct 2026 | `tests/test_event_planning.py` |
| AC1-P1…P8 | Green | 409 for all eight; status unchanged | Pass | as above | Claude for Tate, 13 Oct 2026 | as above |
| AC1-N1 | Green | 404 with the service's "was not found" message | Pass | as above | Claude for Tate, 13 Oct 2026 | Red was FastAPI's route-level `Not Found`; the body assertion separates the two |
| AC4-N1…N6 | Green | 403 (N1–N3, N5, N6) and 401 (N4); status stays Approved | Pass | as above | Claude for Tate, 13 Oct 2026 | as above; N5/N6 stub the auth service over `httpx.get` |
| AC1-X1, AC4-N7, AC4-N8 | Green | Planning set; one history row `Approved → Planning`, actor `scrum58-coordinator`, `event_coordinator`, `coordinator.planning`; refused call left event and history unchanged; anon/authenticated cannot execute, service_role can | Pass | as above, **disposable local PostgreSQL 16** built by `database/tests/bootstrap_event_status_history.py` + `0026` | Claude for Tate, 13 Oct 2026 | `psql -f database/verify_event_request_planning.sql` printed `ALL EVENT PLANNING VERIFICATIONS PASSED` and left 0 fixture rows. Red before `0026`: `transition not allowed from status Approved`. Not run on shared Supabase (0026 not applied there) |

**Local evidence, 13 October 2026** (red runs seen first for every case):

- `pytest tests/test_event_planning.py` in `backend/eventRequestService`: Red 15 failed / 1 passed (all `404`: route missing; the one pass was AC1-N1, then strengthened to fail on the route-level 404), then Green 16 passed.
- Whole service: `pytest` 340 passed, 0 failed, 0 skipped; `ruff check .` clean. Supabase and the auth service are faked in these runs.
- `0026` applied twice to the same disposable DB without error (safe to re-run). `database/verify_event_request_status_history.sql` (SCRUM-48) still prints `ALL EVENT STATUS HISTORY VERIFICATIONS PASSED` after `0026`.

**Shared development, 13 October 2026:** before applying, the live `advance_event_request_by_coordinator` matched `0025` (no newer change to overwrite). `0026` applied via MCP as `20261013134214 event_request_planning`. Read-only checks afterwards: definition contains the Approved → Planning move and the `planning` source; `anon` and `authenticated` cannot execute; `service_role` can; not `SECURITY DEFINER`. The rolled-back verification script was **not** run on shared (the MCP SQL tool is used read-only), so AC1-X1/AC4-N7 are proven locally only.

**Not yet done:** a live API call against shared; frontend control; PR CI; human review of these test cases (`testing.md` §10).

## Increment: send for safety review (AC2, AC3a) — 16 October 2026

Branch `feat/scrum-58-safety-review`, based on Jaren's `feat/scrum-60-safety-check` (PR #62, `8897646`), which adds the `Safety Review` status (migration `0029`). This branch cannot merge before PR #62.

### Approved contract update

Jaren (SCRUM-60 owner) answered the AC2 question on 15–16 October: the status is **Safety Review**, and only the Safety Officer moves an event to `Confirmed` (SCRUM-60 AC3/AC6). The story owner (Tate) approved the wording and rules below on 16 October 2026.

| Jira AC | Outcome | Approved wording |
| --- | --- | --- |
| AC2 (send once booked and reserved) | **Clarified** (was Parked) | **AC2:** Given a Planning event assigned to me with at least one approved venue booking, no pending booking, and every equipment requirement's reservations adding up to its full quantity, when I send it for safety review, then it becomes `Safety Review` and the status history records me (role `event_coordinator`, source `coordinator.safety_review`). Rejected bookings are ignored. An event with no equipment requirements is ready. |
| AC3 (say what is missing, don't send) | **Split** | **AC3a:** Otherwise it is refused with `409` and a list of every outstanding item (no venue booked; each pending booking by venue; each under-reserved requirement with reserved and required counts), each with a plain-language message, and nothing changes. **AC3b (parked):** items marked for review also block, once SCRUM-64 builds the flag. |

Decisions behind the rules: a booking can only be `pending`, `approved` or `rejected` and cannot be withdrawn, so counting rejected bookings would block an event forever. "Reserved" uses SCRUM-13's reservations, not Technical Support's manual `arranged` status, which can be set independently.

### Design

A new function, `send_event_request_for_safety_review` (migration `0039_send_for_safety_review.sql`; first written as `0030`, renumbered on 16 Oct because SCRUM-64 holds `0030`–`0033` and `0035`–`0038` and SCRUM-60 holds `0034`), not another branch in `advance_event_request_by_coordinator`: only this move has readiness rules, and the shared function (`0025`/`0026`/`0029`) stays untouched. It locks the event row, checks assignment (`P0003`) before status (`P0004`) before readiness, so nobody else learns what an event is missing. It locks nothing else (see Lock protocol below). Not ready raises `P0005` with the outstanding items as JSON in `DETAIL`; the API returns them from that same refusal rather than a second read. Endpoint: `POST /event-requests/{id}/safety-review`.

### Allowed transition (added)

| From | To | Who | Otherwise |
| --- | --- | --- | --- |
| Planning | Safety Review | Latest assigned coordinator, when ready | `409` `P0005` with outstanding list if not ready; `409` `P0004` from any other status; `403` `P0003` for anyone else; `404` `P0002` if missing |

### Test case specification (added)

| ID | AC | Test scenario | Technique | Pre-conditions | Test steps | Test data | Expected result | Forbidden side effects | Layer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AC2-H1 | AC2 | Ready event moves to Safety Review; one history row names the coordinator | Happy | Disposable DB (see Evidence); Planning event, `scrum58-coordinator` assigned | Call the function | 1 approved booking; Projector requirement 3, reservations 2 + 1 | `Safety Review`; one history row `Planning → Safety Review`, actor, `event_coordinator`, `coordinator.safety_review` | Rolled back | DB |
| AC2-P1 | AC2 | No equipment needed is ready | Partition | As AC2-H1 | Call the function | 1 approved booking, no requirements | `Safety Review` | Rolled back | DB |
| AC2-P2 | AC2 | A rejected booking is ignored beside an approved one | Partition | As AC2-H1 | Call the function | 1 rejected + 1 approved booking | `Safety Review` | Rolled back | DB |
| AC3-N1 | AC3a | A pending booking blocks, even beside an approved one, and is named | Negative | As AC2-H1 | Call the function | approved Hall E + pending Hall F | `P0005`; outstanding = `[venue_booking_pending, booking id, "Hall F"]` | Event and history unchanged | DB |
| AC3-N2 | AC3a | No booking at all blocks | Negative | As AC2-H1 | Call the function | no bookings | `P0005`; `[no_venue_booking]` | Unchanged | DB |
| AC3-N3 | AC3a | Only rejected bookings means no venue | Negative | As AC2-H1 | Call the function | 1 rejected booking | `P0005`; `[no_venue_booking]` | Unchanged | DB |
| AC3-B1 | AC3a | One unit short blocks | Boundary | As AC2-H1 | Call the function | Microphone 3 required, 2 reserved | `P0005`; `equipment_not_reserved`, required 3, reserved 2 | Unchanged | DB |
| AC3-B2 | AC3a | Nothing reserved is reported as 0 | Boundary | As AC2-H1 | Call the function | Speaker 3 required, none reserved | `P0005`; reserved 0, required 3 | Unchanged | DB |
| AC3-N4 | AC3a | Every outstanding item is listed at once, venue first | Negative | As AC2-H1 | Call the function | pending booking + Stage light 1 of 4 | `P0005`; two items, venue then equipment | Unchanged | DB |
| AC2-N1 | AC2 | A ready event not in Planning is refused | Negative | As AC2-H1 | Call the function | Approved, approved booking | `P0004` | Unchanged | DB |
| AC2-N2 | AC2 | Sending twice is refused | Negative | As AC2-H1 | Call twice | ready event | second call `P0004` | No second history row | DB |
| AC4-N9 | AC4 | Another coordinator is refused before readiness is checked | Negative | As AC2-H1 | Call as `other-coordinator` | unready event | `P0003` | Unchanged | DB |
| AC4-N10 | AC4 | Missing event | Negative | As AC2-H1 | Call with a random id | — | `P0002` | — | DB |
| AC4-N11 | AC4 | Browser roles cannot call the function | Negative | As AC2-H1 | `has_function_privilege` | — | `anon`, `authenticated` false; `service_role` true | — | DB |
| AC2-H2 | AC2 | The endpoint moves a ready Planning event | Happy | `make_assigned_client(status="Planning")` | POST `/safety-review` as `coord-1` | — | 200, body and stored status `Safety Review` | — | API |
| AC3-N5 | AC3a | The refusal lists every item with a message | Negative | As AC2-H2, fake reports all three kinds | POST as `coord-1` | no venue; Hall F pending; Microphone 2 of 3 | 409, `detail` + `outstanding` with `message` per item | Status stays Planning | API |
| AC2-P3…P11 | AC2 | Every other status is refused without an outstanding list | Partition | As AC2-H2 with the given status | POST as `coord-1` | Submitted, Under Review, Changes Requested, Approved, Rejected, Safety Review, Confirmed, Completed, Cancelled | 409, no `outstanding` | Status unchanged | API |
| AC2-N3 | AC2 | Missing request is the service's 404 | Negative | Empty fake | POST | id `…0001` | 404 with "was not found" | — | API |
| AC4-N12 | AC4 | Non-assigned coordinator gets 403 and no outstanding list | Negative | Assigned to `coord-2`, unready | POST as `coord-1` | — | 403, no `outstanding` | Status unchanged | API |
| AC4-N13 | AC4 | Reassigned-away coordinator refused | Negative | `coord-1` then `coord-2` | POST as `coord-1` | — | 403 | Unchanged | API |
| AC4-N14 | AC4 | No coordinator assigned | Negative | No assignment | POST as `coord-1` | — | 403 | Unchanged | API |
| AC4-N15 | AC4 | No session | Negative | Real auth dependency | POST, no header | — | 401 | — | API |
| AC4-N16…N18 | AC4 | Organiser, operations manager and Safety Officer cannot send | Negative | Auth stubbed to the role | POST | the three roles | 403 | Unchanged | API |
| AC2-X1 | AC2 | Repository calls the new RPC with the caller's identity | Cross-cutting | `httpx.MockTransport` | `send_for_safety_review` | `request-1`, `coord-1` | POST `/rest/v1/rpc/send_event_request_for_safety_review`, single-object Accept | — | Unit |
| AC3-X1 | AC3a | Repository keeps `P0005` and PostgREST's `details` | Cross-cutting | Mock returns 400 with code and details | `send_for_safety_review` | details `[{"kind": "no_venue_booking"}]` | `EventRequestRpcError` with errcode and details | — | Unit |

### Evidence (local, 16 October 2026)

| ID | Automation status | Actual result | Execution status | Build or commit | Executed by and date | Remarks and evidence |
| --- | --- | --- | --- | --- | --- | --- |
| AC2-H1 … AC4-N11 (14 DB cases) | Green | As expected for all 14 | Pass | branch on `8897646`, **disposable local PostgreSQL 16** | Claude for Tate, 16 Oct 2026 | `psql -f database/verify_safety_review_readiness.sql` printed `ALL SAFETY REVIEW READINESS VERIFICATIONS PASSED`, 0 fixture rows left. Red before the migration: function does not exist |
| AC2-H2 … AC3-X1 (21 tests) | Green | As expected | Pass | as above, repositories and auth faked | Claude for Tate, 16 Oct 2026 | `tests/test_event_safety_review.py` (19), `tests/test_supabase_repository.py` (2). Red: 19 × `404` (route missing), 2 × `AttributeError` (method missing) |

- **Database setup:** fresh cluster, then `database/tests/bootstrap_event_status_history.py --disposable` (database named `scrum48_*`), then migrations `0001`, `0016_venues`, `0018_venue_booking_requests`, `0020_equipment_reservations`, `0021_equipment_requirements`, `0027`, `0028`, `0026`, `0029` and this migration (then numbered `0030`). It applied twice without error. Now scripted as `database/tests/bootstrap_safety_review.py --disposable`.
- **Planted-bug check:** counting rejected bookings as a venue → AC3-N3 failed; accepting one unit short → AC3-B1 failed. Real migration restored → passed.
- **Regression on the same DB:** `verify_event_request_planning.sql`, `verify_event_request_status_history.sql` (SCRUM-48) and `verify_safety_review.sql` (SCRUM-60) all still pass.
- **Whole service:** `pytest` 364 passed (343 on PR #62's branch + 21 new), 0 failed, 0 skipped; `ruff check .` clean.
- **Test-helper finding:** `P0004`, the team's "transition not allowed" code, is also PL/pgSQL's built-in `assert_failure`, which `EXCEPTION WHEN OTHERS` does not catch. Handlers that must catch it need `WHEN SQLSTATE 'P0004'`.

**Not yet done:** apply `0039` to shared development (needs PR #62's `0029`, already applied there per Jaren's doc; not rechecked — the Supabase connection needs signing in again); live API check; "Send for safety review" button in the frontend; AC3b; PR CI; human review of these test cases (`testing.md` §10). Not checked: that `service_role` has `SELECT` and row-lock rights on `venue_booking_requests`, `venues`, `equipment_requirements` and `equipment_reservations` on shared. The local run used a superuser.

### Lock protocol and concurrency — 16 October 2026

Heng Rui (SCRUM-64) pointed out that the first version could deadlock: it locked the event row and then requirement and booking rows `FOR SHARE`, while `reserve_equipment` locks requirement → equipment and only then reaches the event through the FK on its insert. Test AC2-X2 reproduced it against that version (`ERROR: 40P01: deadlock detected`).

Agreed protocol, sent to SCRUM-64/60 on 16 Oct:

- **Gates** (this handover; SCRUM-60's approval) lock **only the event row, `FOR UPDATE`, first**, then read children unlocked. A gate never waits on anything while holding the event, so it cannot be part of a deadlock cycle.
- **Writers that can make an event unready** (reservation inserts, new requirements, SCRUM-64 review flags) take their own locks first and reach the event **last**, through the FK `KEY SHARE` of inserting a row that references `event_requests`. That conflicts with `FOR UPDATE`, so a writer either commits before the gate reads (the gate sees its row) or waits until the gate commits (the row lands on a Safety Review event, where SCRUM-60's approval re-check catches it).
- **Depends on:** gates staying on `FOR UPDATE` (not `FOR NO KEY UPDATE`), and SCRUM-64's `arrangement_reviews.event_request_id` having a real FK to `event_requests` (asked Heng Rui).
- **Known gap:** `venue_booking_requests.event_request_id` has no FK, so a booking created mid-handover is not serialised. To raise with the venue owners; not fixed here.

| ID | AC | Test scenario | Technique | Pre-conditions | Test steps | Test data | Expected result | Forbidden side effects | Layer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AC2-X2 | AC2 | A reservation in flight does not deadlock with the gate | Cross-cutting | Disposable DB from `bootstrap_safety_review.py`; Planning event, approved booking, Projector requirement 3, matching equipment | Session A: `BEGIN`, lock the requirement `FOR UPDATE` (reserve_equipment's first lock), sleep, run the real `reserve_equipment` for 3, `COMMIT`. Session B, once A is sleeping: send for safety review | — | No `40P01`; A commits; B refuses with `P0005` `equipment_not_reserved` (reservation not yet committed); a later send succeeds | Event stays Planning until the later send | DB (two connections) |
| AC3-X2 | AC3a | A writer that reached the event first makes the gate wait, and the gate then sees its row | Cross-cutting | As AC2-X2, no requirement | A: `BEGIN`, insert a Projector requirement (3), sleep, `COMMIT`. B, once A is sleeping: send | — | B observed waiting on a lock; then `P0005` listing required 3, reserved 0 | Event stays Planning; no Safety Review history row | DB (two connections) |
| AC3-X3 | AC3a | When the gate goes first, a writer waits and then completes | Cross-cutting | As AC2-X2, no requirement (ready) | B: `BEGIN`, send, sleep, `COMMIT`. A, once B is sleeping: insert a requirement | — | A observed waiting on a lock; both succeed; event Safety Review; exactly one Safety Review history row | No deadlock | DB (two connections) |
| AC3-X4 | AC3b | A review flag raised during the handover is seen or waits, as in AC3-X2/X3 | Cross-cutting | SCRUM-64's `arrangement_reviews` and `get_outstanding_arrangement_reviews` | As AC3-X2 and AC3-X3 with a flag insert | — | As AC3-X2/X3 | — | DB (two connections) |

| ID | Automation status | Actual result | Execution status | Build or commit | Executed by and date | Remarks and evidence |
| --- | --- | --- | --- | --- | --- | --- |
| AC2-X2 | Green | Red on the first version: `40P01 deadlock detected`. After the fix: no deadlock, A committed, B `P0005`, later send → Safety Review | Pass | this branch, disposable local PostgreSQL 16 | Claude for Tate, 16 Oct 2026 | `python3 database/tests/test_safety_review_concurrency.py --dsn … --psql …`; 3 tests OK in each of 5 consecutive runs on a fresh cluster |
| AC3-X2, AC3-X3 | Green | As expected | Pass | as above | Claude for Tate, 16 Oct 2026 | Pass against both versions: they prove the protocol's waiting behaviour, not the bug |
| AC3-X4 | Planned | — | Blocked | — | — | Needs SCRUM-64's branch (local and unpushed as of 16 Oct) |

After the fix, on the same fresh cluster: `verify_safety_review_readiness.sql`, `verify_event_request_planning.sql`, `verify_event_request_status_history.sql` and `verify_safety_review.sql` all printed their PASSED lines.
