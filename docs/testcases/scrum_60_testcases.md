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
| AC4b-N1 | AC4b | The coordinator lookup fails after the decision is saved | Negative (unavailable system) | As AC4a-H1; the assignment read fails | `POST /safety-decision` | `changes_requested` | 200 `Planning`; the review is kept; no notice; a warning is logged (not 502, which the officer would retry into 409) | Decision not undone | API |
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

## Test case specification (increment 3: safety queue and page)

`GET /event-requests/safety-queue` (Safety Officer) lists events in `Safety Review`, ordered by `updated_at` ascending (the status change bumps it, so it stands for "entered Safety Review"). The page `/safety` gathers, per event, its venue bookings, each venue's capacity, layouts and accessibility features, the active blocks overlapping each booking ("restrictions"), and its equipment requirements and reservations. The Safety Officer may read those, role-wide and read-only, in venueService and equipmentService. The coordinator's event page shows the officer's decisions.

| ID | AC | Test scenario | Technique | Pre-conditions | Test steps | Test data | Expected result | Forbidden side effects | Layer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AC2-H1 | AC2 | The queue lists waiting events, longest-waiting first, with attendance and accessibility | Happy | Two events in `Safety Review` (different `updated_at`), one in `Planning` | `GET /safety-queue` as officer | — | 200, the two in order, fields present; `Planning` absent | — | API |
| AC2-P1 | AC2 | Nothing waiting is an empty queue | Partition | Event in `Planning` only | `GET /safety-queue` | — | 200 `[]` | — | API |
| AC2-N1 | AC2 | Others cannot see the queue | Negative | — | `GET /safety-queue` | coordinator; organiser | 403 | — | API |
| AC2-H2…H4 | AC2 | The officer reads an event's bookings, a venue and its blocks | Happy | Seeded venue, booking, block | venueService reads as `safety_officer` | — | 200 each; bookings read without an assignment check | — | API (venueService) |
| AC2-N2 | AC2 | The officer cannot change venues or blocks | Negative | Seeded venue | `PATCH /venues/{id}`; `POST /venues/{id}/blocks` | — | 403 | Nothing changes | API (venueService) |
| AC2-H5, AC2-H6 | AC2 | The officer reads an event's equipment requirements and reservations | Happy | Seeded rows | equipmentService by-event reads | — | 200; requirements read without an assignment check | — | API (equipmentService) |
| AC2-N3 | AC2 | The officer cannot reserve equipment | Negative | — | `POST /equipment-reservations` | — | 403 | Nothing stored | API (equipmentService) |
| AC2-X1 | AC2 | Only active blocks overlapping the booking's dates and slots are restrictions | Cross-cutting | Blocks: overlapping, lifted, other day, other slot | `overlappingBlocks` | — | Only the overlapping one | — | Unit |
| AC1-X3 | AC1 | The officer lands on, and is offered, the safety queue | Cross-cutting | — | `workspaceForRoles`, `workspaceLinks` | `safety_officer`; `event_coordinator` | `/safety` offered only to the officer | — | Unit |
| AC3-H2, AC4a-H3, AC4a-N4 | AC3, AC4a | The decision form sends the right payload and refuses bad input locally | Happy, Negative | — | `parseSafetyDecisionForm` | approve; changes with reason and targets; blank or 2001-character reason; `rejected` | Payloads as specified; errors for the bad inputs | — | Unit |
| AC4a-X2 | AC4a | The form offers each arrangement and both decisions, no Reject | Cross-cutting | One booking, one reservation | Render | — | Two checkboxes, Approve, Ask for changes, no Reject | — | Component |
| AC3-H3, AC6-N5, AC6-N6, AC4a-N5 | AC3, AC6 | The server action posts, explains a refused approval, reports a stale event and skips the API on bad input | Happy, Negative | Fetch mocked | `decideSafety` | approve 200; 409 with `outstanding`; 409 without; blank reason | Redirect with notice; "Approval refused. …"; "no longer waiting"; no fetch | — | Unit |
| AC4a-H4, AC4a-P2 | AC4a | The coordinator sees the officer's decisions, or that there are none | Happy, Partition | — | Render `SafetyReviewsPanel` | one review; none | Decision and reason shown; "No safety decision yet." | — | Component |
| AC2-H5 (E2E), AC4a-H5, AC4b-X1 | AC2, AC4a | Browser: the officer sees attendance, venue capacity below attendance, a restriction and equipment; asks for changes on the booking; the coordinator reads the reason | Happy | Mock APIs seeded | Drive `/safety`, then the coordinator's event page | — | As stated; event leaves the queue | — | E2E (mock APIs) |
| AC3-H4 | AC3 | Browser: the officer approves; the event leaves the queue | Happy | As above | Approve | — | Notice "Confirmed"; event gone | — | E2E (mock APIs) |

**Local evidence, 18 October 2026 (increment 3, branch `feat/scrum-60-safety-check`):** Red first for every new API and unit case (missing route: 422/403; missing modules). Green: `backend/eventRequestService` 388 passed; `backend/venueService` 453 passed (`tzdata` installed into the local venv for Windows); `backend/equipmentService` 333 passed; `ruff check .` clean in all three. `frontend`: `vitest` 364 passed, typecheck, lint and `npm run build` clean; `npx playwright test` 41 passed (2 new), against the mock APIs in `frontend/e2e/support`, not the real services.

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
| AC4b-N1 | Green | 200 `Planning`; one review; no notice; warning logged | Pass | `fix/scrum-60-safety-notice-502` from dev `d3acb09`, local, repositories faked. Red first: 502 | Claude for Jaren, 20 Oct 2026 | `tests/test_safety_review.py` (reported by Tate, Agent Discussions #2405) |
| AC4a-H2, AC4a-P1, AC4a-N1…N3, AC4a-B1…B3 | Green | Coordinator reads reasons; `[]` targets accepted; missing/blank reason, 2001 characters and unknown target kind 422 with nothing written; unassigned coordinator 404, organiser 403 | Pass | as above | Claude for Jaren, 18 Oct 2026 | as above |
| AC1-N1…N4 | Green | Coordinator and organiser 403, no token 401, removed officer 403 (`P0003`); status unchanged, no review | Pass | as above | Claude for Jaren, 18 Oct 2026 | as above |
| AC6-P1, AC6-N1…N3 | Green | 409 from seven other statuses and on a repeated approval (one review kept); `rejected` 422; missing event 404 from the service | Pass | as above | Claude for Jaren, 18 Oct 2026 | as above |
| AC4a-X2, AC4a-X3, AC4b-X1 | Green | RPC body, review query and latest-assignment query exactly as specified | Pass | as above | Claude for Jaren, 18 Oct 2026 | `tests/test_supabase_repository.py`; written after the code, then confirmed Red (3 failed) with the repository changes removed |
| AC3-X1, AC4a-X1, AC1-X2, AC6-X3, AC6-X4, AC6-X5 | Green | Approve → `Confirmed` with review and history (`safety_officer`, `safety.approval`); repeat and `Planning` refused `P0004`; changes → `Planning` with reason and targets kept; non-officer `P0003`; every bad or NULL input `22023` with nothing written; `service_role` SELECT only on `safety_reviews`, no browser access | Pass | shared development after `0034` (`20261018031650`) and `0044` (`20261018045424`) | Claude for Jaren, 18 Oct 2026 | `database/verify_safety_review_decisions.sql`, rolled back; no `verify SCRUM-60` rows, reviews or officer roles left. Red before `0034`: `42883` (function missing). Red before `0044`: `AC6-X5 null decision: expected 22023, got 23502` |

**Local evidence, 18 October 2026:** Red first: 24 of 26 API tests failed on the missing route; the two route-404 cases were then tightened to assert the service's 404 and failed until the code existed. Green: `backend/eventRequestService` `pytest` 384 passed, `ruff check .` clean; `backend/authService` 46 passed; `frontend` `vitest` 350 passed, typecheck and lint clean, after merging `dev` (`754f34c`).

**Shared development evidence, 20 October 2026 (Claude for Jaren):** Heng Rui applied the SCRUM-64 bundle first (`20261020093041`, Agent Discussions #2440). The live `decide_safety_review` body matched `0044` exactly (md5). Red: AC4c-X1 failed before `0045` ("expected one linked flag, got 0"). `0045` was applied via MCP as `20261020093706`, with bytes matching the README's SHA-256 pin. Green: `verify_safety_review_arrangement_reviews.sql` (AC4c-X1, AC4c-X2, AC6-X6, AC6-X7, AC6-X8) and `verify_safety_review_decisions.sql` (AC1-X2, AC3-X1, AC4a-X1, AC6-X3 to AC6-X5) both passed in rolled-back transactions. Afterwards: `service_role` alone can execute the function; no test events, review rows or temporary triggers remained. Not yet run: an authenticated API or browser journey on the shared stack.

**`0047` on shared development, 20 October 2026 (Claude for Jaren):** after PR #79 merged and Tate applied `0039`/`0046` (`20261020113354`, `20261020113427`), the live `decide_safety_review` matched `0045` exactly (md5). `0047` was applied via MCP as `20261020132807`, with bytes matching the SHA-256 pin and the live body matching the merged file. `verify_safety_review_approval_readiness.sql` (AC6-X9 to AC6-X13) passed in a rolled-back transaction; `service_role` alone can execute; no test events remained. An earlier rolled-back dry run of the same SQL also passed. Still to do: the authenticated coordinator to Safety Officer journey on the shared stack, which needs the `safety_officer@example.com` account.

**Defect found in review (Heng Rui, message 2196):** in `0034`, `NULL NOT IN (...)` evaluates to NULL, so a NULL decision passed the check and failed later with `23502`, and a target without `arrangement` was saved. Fixed by `0044_safety_review_null_inputs.sql`; AC6-X5 added.

**Known limitation:** the coordinator notice is best-effort: sent once after the decision commits, outside the transaction, with no durable retry. Durable delivery is planned under SCRUM-57.

**Deviation from message 2168:** the coordinator notice is sent after the decision commits (SCRUM-17 pattern), not through the outbox. `event_request_outbox` only accepts submission events for organisers; widening it is out of scope.

**Not yet done:** increment 2b (SCRUM-64 flags, approval re-checks); increment 3 (queue and page); PR CI; human review.

## Test case specification (increment 2b: SCRUM-64 connection)

Branch `feat/scrum-60-safety-review-flags`, built on `feat/scrum-60-safety-check` with SCRUM-64's `feat/scrum-64-arrangement-review` (`a7ea77d`) merged in; it can only merge after PR #63. Agreed with Heng Rui in messages 2198 and 2206. Migration `0045` replaces `decide_safety_review`. Approval also needs SCRUM-58's ordinary readiness check; that part stays open until Tate publishes it.

| ID | AC | Test scenario | Technique | Pre-conditions | Test steps | Test data | Expected result | Forbidden side effects | Layer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AC4c-H1 | AC4c | Asking for changes flags each chosen arrangement, linked to the saved decision and its reason | Happy | Event in `Safety Review` with two arrangements | `POST /safety-decision` | `changes_requested`, reason, both targets | 200; one flag per target, `safety_recheck`, `trigger_id` = the review id, reason as saved | — | API (fake) |
| AC4c-N1 | AC4c | A target from another event is refused | Negative | As AC4c-H1, plus another event's booking | `POST /safety-decision` | one own target, one foreign | 422 | No review, no flags, no notice, status unchanged | API (fake) |
| AC6-N4 | AC6 | Approval is refused while a review is outstanding, listing it | Negative | Event with an uncleared flag | `POST /safety-decision` | `approved` | 409 with `outstanding` item `arrangement_needs_review` (review id, arrangement, message) | Status unchanged, no review | API |
| AC6-P2 | AC6 | A cleared review does not block approval | Partition | Event with a cleared flag | `POST /safety-decision` | `approved` | 200 `Confirmed` | — | API (fake) |
| AC4c-X1 | AC4c | The real function flags the target with the saved decision id and reason and enqueues its notice | Cross-cutting | `0030`–`0045`; event with one booking | Call `decide_safety_review` | `changes_requested` | `Planning`; one `safety_recheck` flag with `trigger_id` = `safety_reviews.id`; one notification outbox row | — | DB |
| AC4c-X2 | AC4c | The real function refuses another event's booking | Negative | Another event's booking | Call | that booking as target | `22023` | No review, no flag, status unchanged | DB |
| AC6-X6 | AC6 | The real function refuses approval with an outstanding review on a cancelled booking | Negative | Uncleared flag on a cancelled booking | Call | `approved` | `P0005`; DETAIL lists the review | No review, status unchanged | DB |
| AC6-X7 | AC6 | A failed flag write rolls back the decision and status | Negative | Fault trigger on the flag insert | Call | `changes_requested` | Error raised | No review, status unchanged | DB |
| AC6-X8 | AC6 | A cleared review does not block approval | Partition | Cleared flag | Call | `approved` | `Confirmed` | — | DB |

The fake-backed API cases (AC4c-H1, AC4c-N1, AC6-P2) check the API contract only; the fake mirrors `0045`. The behaviour itself is proved by the DB cases.

**Local evidence, 18 October 2026:** `backend/eventRequestService` `pytest` 419 passed, 1 skipped (SCRUM-64's tests included), `ruff check .` clean. Red: AC6-N4 failed (no `P0005` mapping) before `SafetyApprovalBlockedError`. DB cases written in `database/verify_safety_review_arrangement_reviews.sql`, not yet run: they need a database with SCRUM-64's migrations, which shared development does not have.

## Test case specification (increment 2c: readiness on approval)

Branch `feat/scrum-60-approval-readiness`, from Tate's `feat/scrum-58-safety-review` (`2c9dd67`, which includes this story's `0045` branch). Agreed in messages 2233, 2237 and 2238; merge order PR #62 → PR #63 → `0045` branch → Tate's `0039`/`0046` branch → this. Migration `0047` makes approval also call SCRUM-58's `private.event_readiness_issues`.

| ID | AC | Test scenario | Technique | Pre-conditions | Test steps | Test data | Expected result | Forbidden side effects | Layer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AC6-N7 | AC6 | Approval is refused until the event is ready; readiness items come before review flags | Negative | Equipment shortfall (2 of 4) and an outstanding flag | `POST /safety-decision` | `approved` | 409; `outstanding` = `equipment_not_reserved` ("Wireless microphone: 2 of 4 reserved"), then `arrangement_needs_review` | Status unchanged, no review | API (fake) |
| AC6-P3 | AC6 | Readiness does not block asking for changes | Partition | `no_venue_booking` | `POST /safety-decision` | `changes_requested`, reason | 200 `Planning` | — | API (fake) |
| AC6-X9 | AC6 | The real function refuses approval with no booking | Negative | `0030`–`0047`; event without bookings | Call | `approved` | `P0005`, DETAIL `[{"kind": "no_venue_booking"}]` | No review, status unchanged | DB |
| AC6-X10 | AC6 | The real function lists readiness items first, then flags | Negative | Approved booking, 2 of 4 reserved, outstanding flag | Call | `approved` | `P0005`; DETAIL = `equipment_not_reserved` (2/4), then the flag | No review | DB |
| AC6-X11 | AC6 | The real function still allows asking for changes on an unready event | Partition | As AC6-X10 | Call | `changes_requested` | `Planning` | — | DB |
| AC6-X12 | AC6 | The real function approves a ready event with nothing outstanding | Happy | Approved booking, requirement fully reserved | Call | `approved` | `Confirmed` | — | DB |

The earlier verifiers were updated so their approval cases use a ready event (one approved booking) and so the outstanding-flag case looks for the review item anywhere in the list. `verify_safety_review_decisions.sql` was re-run on shared development (`0044`) after that change and still passes, so it holds before and after `0047`.

**Local evidence, 19 October 2026:** Red: AC6-N7 and AC6-P3 failed before the fake modelled readiness. Green: `backend/eventRequestService` `pytest` 448 passed, 1 skipped, `ruff check .` clean. DB cases written in `database/verify_safety_review_approval_readiness.sql`, not yet run: they need SCRUM-58's `0046` and SCRUM-64's schema, which shared development does not have; Tate's `database/tests/bootstrap_safety_review.py` builds that schema.

**Independent DB evidence, 19 October 2026 (Heng Rui, SCRUM-64; Telegram Agent Discussions 2240 and 2241):** commit `4a5bc93` on a fresh owned PostgreSQL 16 schema built with Tate's `database/tests/bootstrap_safety_review.py` through `0046`, then `0047` applied. All four workflow verifiers passed with ROLLBACK: `verify_safety_review_decisions.sql`, `verify_safety_review_arrangement_reviews.sql`, `verify_shared_event_readiness.sql` (SCRUM-58) and `verify_safety_review_approval_readiness.sql`. SCRUM-64's ten review scripts, three lock tests and five handover race tests also passed, and SCRUM-64's combined integration runner passed 9 of 9 after its cross-event case was aligned to the agreed `22023`. Covered: AC4c-X1/X2, AC6-X6 to AC6-X12. Limits: local disposable database, not shared development; no real authentication, API or browser run. This is his reported result; it was not rerun here.

**Still to do:** merge in the agreed order (PR #62 → PR #63 → `0045` branch → SCRUM-58's `0039`/`0046` → this branch), apply `0045` and `0047` to shared development in that order, then an authenticated coordinator → Safety Officer journey on the integrated stack.

## Review of PR #62 (Yang Xue, 19 October 2026)

| Finding | Outcome | Cases |
| --- | --- | --- |
| Targets from another event are accepted | Valid for PR #62 alone. Membership is enforced in `0045` (SCRUM-64's helper; cross-event target → `22023`, AC4c-N1/AC4c-X2, verified by Heng Rui). It is not repeated in a PR #62 migration, because any number above `0045` would override `0045`/`0047` on a fresh build. PR #62 only stores targets; nothing is flagged from them until `0045`. | AC4c-N1, AC4c-X2 |
| Duplicate targets accepted | Fixed: the API refuses the same arrangement twice (422); `0047` refuses it in the database too. | AC4a-N6, AC6-X13 |
| "No restrictions" shown when the venue lookup fails | Fixed: the card says the venue details or restrictions could not be loaded, and Approve is disabled for that event. | AC2-N4 |
| Approve silently drops a typed reason or ticked arrangements | Fixed: approving with either filled in is refused with a message. | AC3-N2 |
| Coordinator cannot see which arrangements were flagged | Fixed: the coordinator's Safety check panel lists them (booking venue and dates; equipment reservations by kind, as the coordinator cannot read reservations). | AC4a-H6 |
| Queue order uses `updated_at` | Kept, with a comment on the trade-off and the upgrade path (latest status-history row). | — |
| Route order for `/safety-queue` | Comment added in `main.py`. | — |
| 409 `outstanding` list unused on PR #62 alone | Comment added: it is filled by `0045`/`0047`. | — |

**Evidence, 19 October 2026:** each new case failed first (AC4a-N6: 200; AC3-N2, AC2-N4, AC4a-H6: assertion failures), then passed. `backend/eventRequestService` `pytest` 389 passed, `ruff check .` clean; `frontend` `vitest` 368 passed, typecheck and lint clean; `npx playwright test` 41 passed (mock APIs).

