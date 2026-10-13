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

**Not yet done:** applying `0026` to shared development and a live API check; frontend control; PR CI; human review of these test cases (`testing.md` §10).
