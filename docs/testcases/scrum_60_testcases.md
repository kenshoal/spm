# SCRUM-60 — Operational Safety Check

Source: [Jira SCRUM-60](https://is212g9t4.atlassian.net/browse/SCRUM-60), read 15 October 2026. Branch: `feat/scrum-60-safety-check`, base `bf4aed5`.

## Approved contract

As the Safety Officer, I want to review an event's safety once its venues and equipment are confirmed, so that no event goes ahead without my approval.

Jaren (story owner) reviewed the six Jira ACs and approved the scope below on 15 October 2026. Jira wording is kept; the rewording is recorded here.

| Jira AC | Outcome | Approved wording |
| --- | --- | --- |
| There is a Safety Officer role, and only Safety Officers can record a safety decision. | **Clarify** | **AC1:** Given a user holds `safety_officer`, when they record a safety decision, then it is accepted; any other role gets `403` and nothing changes. An admin grants the role like any other role. |
| The Safety Officer sees the events waiting for a check, with expected attendance, venue size and layout, accessibility needs, equipment and any venue restrictions. | **Clarify, narrow** | **AC2:** Given events are in `Safety Review`, when the Safety Officer opens the safety queue, then they are listed oldest first, each with expected attendance and accessibility needs; each venue booking with the venue's capacity, supported layouts, accessibility features, dates and slots; venue blocks overlapping those dates ("restrictions"); and the equipment requirements and reservations. Read-only. Other roles get `403`. |
| Approve: the event is confirmed. | **Clarify** | **AC3:** Given an event in `Safety Review`, when the Safety Officer approves it, then it becomes `Confirmed`, and the decision, officer and time are recorded and appear in the status history (SCRUM-48). |
| Ask for changes: the event goes back to planning with the reasons, the affected bookings are marked for review, and the coordinator is told. | **Split** | **AC4a:** Given an event in `Safety Review`, when the Safety Officer asks for changes with a reason, then it returns to `Planning` and the assigned coordinator can read the reason. A blank reason is refused. **AC4b:** the assigned coordinator is notified through the existing notification service. **AC4c (deferred):** affected arrangements are marked for review once SCRUM-64 builds the flag. |
| Reject: outcome to be confirmed with the customer. | **Move (parked)** | Not built until the customer answers. No reject action is offered. |
| An event can't be confirmed without the Safety Officer's approval. | **Keep** | **AC6:** `Confirmed` is reachable only through AC3. Coordinators cannot confirm. A decision on an event that is not in `Safety Review` (repeated, stale or already decided) gets `409` and nothing changes. |

## Scope

- **Increment 1 (this change):** the `Safety Review` status and the `safety_officer` role across database, services and UI; a coordinator may cancel during `Safety Review`; no coordinator path reaches `Confirmed`. This unblocks SCRUM-58 AC2.
- **Increment 2:** the decision endpoint (AC1, AC3, AC4a, AC4b, AC6).
- **Increment 3:** the safety queue and page (AC2), including Safety Officer read access in venueService and equipmentService.
- **Excluded:** moving `Planning → Safety Review` (SCRUM-58 AC2/AC3, Tate); the review flag (SCRUM-64, AC4c); the "event confirmed" notice to the organiser (SCRUM-36); Reject (parked).

## Actors and permissions

| Actor | Can |
| --- | --- |
| `safety_officer` | Read the safety queue; approve or ask for changes on events in `Safety Review` (increments 2–3). Role-wide: there is no per-event assignment of officers. |
| Assigned `event_coordinator` | Send for review (SCRUM-58); cancel during `Safety Review`; read the officer's reasons. Never confirm. |
| `admin` | Grant `safety_officer` through `PATCH /auth/users/{id}/role`. |
| Everyone else | `403` on safety endpoints; the event's other access rules are unchanged (SCRUM-39). |

## Allowed transitions

| From | To | Who | Story |
| --- | --- | --- | --- |
| Planning | Safety Review | Assigned coordinator | SCRUM-58 AC2 |
| Safety Review | Confirmed | Safety Officer (approve) | SCRUM-60 AC3 |
| Safety Review | Planning | Safety Officer (ask for changes) | SCRUM-60 AC4a |
| Safety Review | Cancelled | Assigned coordinator | SCRUM-60 increment 1 (approved 15 Oct) |

## Persistence and atomicity

Migration `0029_safety_review_status.sql` widens the `event_requests` status and `staff_roles` role checks and replaces `advance_event_request_by_coordinator` so `Safety Review` is cancellable. The function body is otherwise identical to `0026`, keeping the row lock, the latest-assignment check and the SCRUM-48 history actor. Decisions in increment 2 use one database function that locks the event row, checks it is still in `Safety Review` and writes status and decision together.

## Assumptions and open questions

1. Status name `Safety Review` agreed by Jaren on 15 Oct; Tate (SCRUM-58 AC2) to be told.
2. Reject outcome: waiting on the customer.
3. The officer's view is role-wide, like the Venue Staff and Technical Support queues.

## Test case specification (increment 1)

| ID | AC | Test scenario | Technique | Pre-conditions | Test steps | Test data | Expected result | Forbidden side effects | Layer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AC1-H1 | AC1 | An admin can grant the Safety Officer role | Happy | Caller is `admin`; Supabase admin faked | `PATCH /auth/users/user-id/role` | role `safety_officer` | 200, body role `safety_officer` | — | API (authService) |
| AC1-X1 | AC1 | The database accepts the role | Cross-cutting | `0029` applied | Insert a `staff_roles` row in a rolled-back transaction | role `safety_officer` | Insert succeeds; an unknown role is still refused (`23514`) | Nothing persists | DB |
| AC6-P1 | AC6 | `Safety Review` is a cancellable, non-terminal status in the API | Partition | Request in `Safety Review` assigned to `coord-1` | `POST /event-requests/{id}/cancellation` as `coord-1` | status `Safety Review` | 200, status `Cancelled` | — | API (eventRequestService) |
| AC6-P2 | AC6 | The coordinator UI offers only cancellation during `Safety Review` and describes the status | Partition | — | `coordinatorActions("Safety Review")`, status description | — | `["cancellation"]`; description present | No confirm or completion action | Unit (frontend) |
| AC6-N1 | AC6 | The coordinator function cannot confirm from `Safety Review` or `Planning` | Negative | `0029` applied; event in the given status assigned to the test coordinator | Call `advance_event_request_by_coordinator(..., 'Confirmed')` | `Safety Review`, `Planning` | `P0004` both times | Status unchanged; no history row | DB |
| AC6-X1 | AC6 | The real function cancels from `Safety Review` and records the coordinator in history | Cross-cutting | As AC6-N1 | Call with `Cancelled` | `Safety Review` | Status `Cancelled`; one history row `Safety Review → Cancelled`, role `event_coordinator` | — | DB |
| AC6-X2 | AC6 | Browser roles still cannot call the replaced function | Negative | `0029` applied | `has_function_privilege` for `anon`, `authenticated` | — | false for both | — | DB |

## Test case specification (increment 2: decision core)

Agreed with Heng Rui (SCRUM-64, messages 2137, 2151, 2168, 2175, 2194) and Tate (SCRUM-58, 2143). Migration `0034_safety_review_decisions.sql` adds the insert-only `safety_reviews` table (decision, reason, targets as saved) and `decide_safety_review(p_event_request_id, p_officer_id, p_decision, p_reason, p_targets)`. Order in one transaction: lock the event `FOR UPDATE` first; `P0002` missing; `P0003` unless `p_officer_id` currently holds `safety_officer`; `P0004` unless the event is in `Safety Review`; `22023` for an unknown decision, a blank reason on `changes_requested`, or targets that are not a JSON array; then insert the review, record the status-history actor (`safety_officer`, `safety.approval` / `safety.changes_requested`) and move to `Confirmed` or `Planning`. No row locks on bookings or reservations. API: `POST /event-requests/{id}/safety-decision` (Safety Officer) and `GET /event-requests/{id}/safety-reviews` (Safety Officer or the assigned coordinator). The coordinator notice (`safety_changes_requested`) is sent after the decision commits, as in SCRUM-17; it is not part of the transaction.

**Deferred to increment 2b, once SCRUM-64 (PR #63) and SCRUM-58's shared readiness function are on `dev`:** calling `private.raise_safety_arrangement_reviews` for `changes_requested` (AC4c), and refusing approval while `get_outstanding_arrangement_reviews` or the readiness check returns items.

| ID | AC | Test scenario | Technique | Pre-conditions | Test steps | Test data | Expected result | Forbidden side effects | Layer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AC3-H1 | AC3 | The Safety Officer approves an event in Safety Review | Happy | Event in `Safety Review`, coordinator `coord-1`, officer `safety-1` | `POST /safety-decision` as `safety-1` | `approved` | 200, status `Confirmed`; one review row (`approved`, `decided_by` = `safety-1`) | No coordinator notice | API |
| AC4a-H1 | AC4a | The Safety Officer asks for changes with a reason and targets | Happy | As AC3-H1 | `POST /safety-decision` | `changes_requested`, reason, one venue booking and one equipment reservation target | 200, status `Planning`; review row keeps the reason and targets exactly as sent | — | API |
| AC4a-H2 | AC4a | The assigned coordinator reads the reason | Happy | AC4a-H1 done | `GET /safety-reviews` as `coord-1` | — | 200, newest first, reason and targets shown | — | API |
| AC4a-P1 | AC4a | Asking for changes with no targets is allowed | Partition | As AC3-H1 | `POST /safety-decision` | `changes_requested`, reason, `targets: []` | 200, `Planning`, targets `[]` | — | API |
| AC4a-N1 | AC4a | Asking for changes without a reason is refused | Negative | As AC3-H1 | `POST /safety-decision` | no reason; reason `"   "` | 422 | Status stays `Safety Review`; no review row | API |
| AC4a-B1…B3 | AC4a | Reason length boundary | Boundary | As AC3-H1 | `POST /safety-decision` | 1, 2000, 2001 characters | 200, 200, 422 | 2001: nothing changes | API |
| AC4a-N2 | AC4a | An unknown target kind is refused | Negative | As AC3-H1 | `POST /safety-decision` | arrangement `room` | 422 | Nothing changes | API |
| AC4a-N3 | AC4a | Someone else cannot read the reasons | Negative | AC4a-H1 done | `GET /safety-reviews` | unassigned coordinator; organiser | 404; 403 | — | API |
| AC4b-H1 | AC4b | Asking for changes notifies the assigned coordinator | Happy | As AC4a-H1 | `POST /safety-decision` | `changes_requested` | One `safety_changes_requested` notice to `coord-1` with the event id and reason | — | API |
| AC4b-P1 | AC4b | Approval sends no coordinator notice | Partition | As AC3-H1 | `POST /safety-decision` | `approved` | No notice (the organiser's "confirmed" notice is SCRUM-36) | — | API |
| AC1-N1…N3 | AC1 | Other roles cannot decide | Negative | As AC3-H1 | `POST /safety-decision` | `event_coordinator`; `event_organiser`; no token | 403; 403; 401 | Status unchanged; no review row | API |
| AC1-N4 | AC1 | A token that still says Safety Officer after the role was removed is refused by the database | Negative | Fake RPC: `safety-1` no longer an officer | `POST /safety-decision` | `approved` | 403 (`P0003`) | Status unchanged; no review row | API |
| AC6-P1 | AC6 | A decision outside Safety Review is refused | Partition | Event in each other status | `POST /safety-decision` | `approved` | 409 | Status unchanged; no review row | API |
| AC6-N1 | AC6 | A repeated decision is refused | Negative | AC3-H1 done (event `Confirmed`) | Approve again | `approved` | 409 | One review row only | API |
| AC6-N2 | AC6 | Reject is not offered | Negative | As AC3-H1 | `POST /safety-decision` | `rejected` | 422 | Nothing changes | API |
| AC6-N3 | AC6 | A missing event is reported | Negative | None | `POST /safety-decision` | random id | 404 | — | API |
| AC3-X1 | AC3 | The real function approves, records history and the review | Cross-cutting | `0034` applied; event in `Safety Review`; officer role row | Call `decide_safety_review` | `approved` | `Confirmed`; history row `Safety Review → Confirmed`, `safety_officer`, `safety.approval`; one review row | — | DB |
| AC4a-X1 | AC4a | The real function returns the event to Planning and keeps reason and targets | Cross-cutting | As AC3-X1 | Call with `changes_requested` | reason, targets | `Planning`; review row reason and targets equal the input | — | DB |
| AC1-X2 | AC1 | The real function refuses a caller without the role | Negative | As AC3-X1, caller has no `safety_officer` row | Call | `approved` | `P0003` | Status, history and reviews unchanged | DB |
| AC6-X3 | AC6 | The real function refuses outside Safety Review and on bad input | Negative | Event in `Planning`; or bad input | Call | `approved`; `rejected`; blank reason; targets `{}` | `P0004`; `22023` ×3 | Nothing written | DB |
| AC6-X5 | AC6 | NULL inputs from a direct SQL caller are refused before any write | Negative | As AC6-X3 | Call | NULL decision; NULL targets; target without `arrangement`; target without `id`; `[null]` | `22023` each | Nothing written | DB |
| AC6-X4 | AC6 | Reviews are insert-only and browser roles have no access | Negative | `0034` applied | Privilege checks | — | `service_role` lacks UPDATE/DELETE on `safety_reviews`; `anon`/`authenticated` cannot execute the function or read the table | — | DB |

Cases for AC2 are designed with increment 3.

## Latest execution record

| ID | Automation status | Actual result | Execution status | Build or commit | Executed by and date | Remarks and evidence |
| --- | --- | --- | --- | --- | --- | --- |
| AC1-H1 | Green | 200, role `safety_officer` | Pass | branch on `bf4aed5`, local, Supabase faked | Claude for Jaren, 15 Oct 2026 | `authService/tests/test_registration.py::test_admin_assigns_safety_officer_role`; Red was `422` (role not in `Role`) |
| AC6-P1 | Green | 200, `Cancelled` | Pass | as above, repositories faked | Claude for Jaren, 15 Oct 2026 | Parametrized cancel test via `CANCEL_SOURCE_STATUSES`; passes before and after, because the cancel response is already `Cancelled`. The meaningful Red is AC6-X3 |
| AC6-P3 | Green | Event in `Safety Review` listed in the Lead's assignments | Pass | as above | Claude for Jaren, 15 Oct 2026 | Added during build: `Safety Review` is in flight, so the coordinator can be reassigned. Red: empty list |
| AC6-X3 | Green | Owner reads the event, status `Safety Review` | Pass | as above | Claude for Jaren, 15 Oct 2026 | Added during build. Red: `ValidationError`, status not in `EventRequestStatus` |
| AC6-P2 | Green | Status list has eleven entries; `Safety Review` in the in-progress tab and progress bar (8 steps); coordinator gets cancellation only | Pass | as above | Claude for Jaren, 15 Oct 2026 | Red: status-list test. Five existing progress-bar and tab tests updated for the eighth step |
| AC1-X1, AC6-N1, AC6-X1, AC6-X2 | Green | Role accepted, unknown role refused; coordinator `Confirmed` refused `P0004` from Safety Review and Planning with no status or history change; cancel from Safety Review recorded `coordinator.cancellation`; anon/authenticated cannot execute | Pass | shared development after `0029` | Claude for Jaren, 15 Oct 2026 | `database/verify_safety_review.sql`, rolled back. Red before `0029`: `23514 staff_roles_role_check` |

**Local evidence, 15 October 2026:**

- `backend/authService`: `ruff check .` clean; `pytest` 46 passed.
- `backend/eventRequestService`: `ruff check .` clean; `pytest` 343 passed.
- `frontend`: `npm run typecheck` and `npm run lint` clean; `npx vitest run` 308 passed.

**Shared development, 15 October 2026:** before applying, the live constraints were `event_requests_status_check` and `staff_roles_role_check` and the live coordinator function was `0026` (last migration `20261013134214`), so `0029` replaced nothing newer. `0029` applied via MCP as `20261015155038 safety_review_status`. `verify_safety_review.sql` then passed; afterwards no `verify SCRUM-60` rows and no `safety_officer` role rows remained.

**Not yet done:** PR CI; human review of these test cases; seeding `safety_officer@example.com` (register it, then re-run `seed_test_accounts.sql`).

### Increment 2 execution record

| ID | Automation status | Actual result | Execution status | Build or commit | Executed by and date | Remarks and evidence |
| --- | --- | --- | --- | --- | --- | --- |
| AC3-H1, AC4b-P1 | Green | 200 `Confirmed`; one `approved` review by `safety-1`; no coordinator notice | Pass | branch after `c117e6a` (dev `754f34c` merged), local, repositories faked | Claude for Jaren, 18 Oct 2026 | `tests/test_safety_review.py` |
| AC4a-H1, AC4b-H1 | Green | 200 `Planning`; reason and targets kept as sent; one `safety_changes_requested` notice to `coord-1` | Pass | as above | Claude for Jaren, 18 Oct 2026 | as above |
| AC4a-H2, AC4a-P1, AC4a-N1…N3, AC4a-B1…B3 | Green | Coordinator reads reasons; `[]` targets accepted; missing/blank reason, 2001 characters and unknown target kind 422 with nothing written; unassigned coordinator 404, organiser 403 | Pass | as above | Claude for Jaren, 18 Oct 2026 | as above |
| AC1-N1…N4 | Green | Coordinator and organiser 403, no token 401, removed officer 403 (`P0003`); status unchanged, no review | Pass | as above | Claude for Jaren, 18 Oct 2026 | as above |
| AC6-P1, AC6-N1…N3 | Green | 409 from seven other statuses and on a repeated approval (one review kept); `rejected` 422; missing event 404 from the service | Pass | as above | Claude for Jaren, 18 Oct 2026 | as above |
| AC4a-X2, AC4a-X3, AC4b-X1 | Green | RPC body, review query and latest-assignment query exactly as specified | Pass | as above | Claude for Jaren, 18 Oct 2026 | `tests/test_supabase_repository.py`; written after the code, then confirmed Red (3 failed) with the repository changes removed |
| AC3-X1, AC4a-X1, AC1-X2, AC6-X3, AC6-X4 | Written | — | Not run | — | — | `database/verify_safety_review_decisions.sql`; needs `0034` on a database. The Supabase connection was unavailable on 18 Oct |

**Local evidence, 18 October 2026:** Red first: 24 of 26 API tests failed on the missing route; the two route-404 cases were then tightened to assert the service's 404 and failed until the code existed. Green: `backend/eventRequestService` `pytest` 384 passed, `ruff check .` clean; `backend/authService` 46 passed; `frontend` `vitest` 350 passed, typecheck and lint clean, after merging `dev` (`754f34c`).

**Defect found in review (Heng Rui, message 2196):** in `0034`, `NULL NOT IN (...)` evaluates to NULL, so a NULL decision passed the check and failed later with `23502`, and a target without `arrangement` was saved. Fixed by `0044_safety_review_null_inputs.sql`; AC6-X5 added.

**Known limitation:** the coordinator notice is best-effort: sent once after the decision commits, outside the transaction, with no durable retry. Durable delivery is planned under SCRUM-57.

**Deviation from message 2168:** the coordinator notice is sent after the decision commits (SCRUM-17 pattern), not through the outbox. `event_request_outbox` only accepts submission events for organisers; widening it is out of scope.

**Not yet done:** apply `0034` and run its verify script; increment 2b (SCRUM-64 flags, approval re-checks); increment 3 (queue and page); PR CI; human review.

