# SCRUM-28 — Track Event Status

Source: [Jira SCRUM-28](https://is212g9t4.atlassian.net/browse/SCRUM-28) (the shared event-request status model, authorised transitions, atomic database updates and status visibility). Later stories add their own transitions on top of this boundary and are named, not claimed, throughout.

Status (1 November 2026): **AI-drafted conversion of the previous catalogue to the standard format; teammate review pending (`testing.md` §10).** The AC wording below is as recorded in the converted catalogue (seven ACs, AC1–AC7, numbered as the previous document recorded them); Jira remains the source of truth. The plan brief for this sweep described six ACs — the seventh (`AC7`, repeated and stale actions) is recorded separately here because the converted catalogue lists it as its own criterion; flag for the story owner if Jira should merge it into AC2.

## Story contract

### Acceptance criteria

- **AC1:** Given a request, whenever its status is stored or displayed, then it is exactly one value of the agreed vocabulary, every request starts as `Draft`, and unknown values are rejected. *The catalogue records ten approved statuses; the vocabulary has since grown to eleven with `Safety Review` (SCRUM-60, `0029_safety_review_status.sql`) — see open questions.*
- **AC2:** Given a request, when a status transition is attempted, then only the agreed transitions succeed and any disallowed source/target pair is refused with a conflict, leaving the stored status unchanged. SCRUM-28 owns: `Draft → Submitted` (owning Event Organiser), `Submitted → Under Review` (assigned Event Coordinator), any non-terminal status → `Cancelled` (assigned Event Coordinator), `Confirmed → Completed` (assigned Event Coordinator).
- **AC3:** Given a transition, when the database function runs, then the request row is locked before validation, authorisation, status validation and persistence are one statement, a refused call leaves the stored status unchanged, and only the server role can execute the RPC.
- **AC4:** Given concurrent assignment and status activity, when both operate on one request, then they serialize on the same `event_requests` row lock (`0014_atomic_coordinator_assignment.sql`); invalid targets are rejected without creating an assignment; and a database-side refusal raised after the API's pre-check still surfaces as a conflict.
- **AC5:** Given any caller, when they view or change a request, then only authorised users and the latest-assigned Coordinator succeed; unauthorised callers receive `401` / `403` / `404` as appropriate, and refused actions mutate nothing. Coordinator details are visible only to the owning organiser, the current Coordinator and authorised operations managers; a reassigned-away Coordinator cannot continue acting.
- **AC6:** Given a user with access, when they view a request, then the current stage is shown as a progress display with the correct tab, available action and assignment message — without implying future stages.
- **AC7:** Given a repeated or stale action (double click, status moved since the page loaded), when it is retried, then the API returns a conflict and the stored status remains unchanged.

### Scope

- **Included:** the status vocabulary and its database constraint; the four SCRUM-28-owned transitions through the atomic RPC; the shared request-row lock; role and ownership enforcement on those endpoints; the status progress display in the organiser and coordinator workspaces; the SCRUM-28 Playwright journey.
- **Excluded (reusing the same status model and atomic boundary):** approval and rejection (SCRUM-17); changes requested and resubmission (SCRUM-35); `Approved → Planning` and `Planning → Safety Review` (SCRUM-58); the Safety Officer's decision (SCRUM-60); automatic completion of overdue confirmed events (SCRUM-40); immutable status history and timeline display (SCRUM-48); notifications (SCRUM-36/37/57); Draft CRUD and submission (SCRUM-11/21).

### Actors and relationship permissions

- **Owning Event Organiser:** submits the Draft (`Draft → Submitted`, SCRUM-21); reads own request.
- **Event Coordinator** (`event_coordinator`): only the **latest-assigned** coordinator may transition (`Submitted → Under Review`, → `Cancelled`, `Confirmed → Completed`); a reassigned-away coordinator is refused.
- **Operations Manager:** assigns/reassigns (SCRUM-14); may read coordinator details on any request.
- Unrelated organiser/coordinator: `404` on the coordinator detail lookup, `403` on transitions; other roles `403`; no session `401`.

### Allowed state transitions

| From | To | Authorised actor | Owner |
| --- | --- | --- | --- |
| `Draft` | `Submitted` | Owning Event Organiser | SCRUM-21 |
| `Submitted` | `Under Review` | Assigned Event Coordinator | SCRUM-28 |
| Any non-terminal status (`Submitted`, `Under Review`, `Changes Requested`, `Approved`, `Planning`, `Confirmed`) | `Cancelled` | Assigned Event Coordinator | SCRUM-28 |
| `Confirmed` | `Completed` | Assigned Event Coordinator | SCRUM-28 |
| `Under Review` / `Changes Requested` | decision transitions | Coordinator (SCRUM-17/35) | named, not claimed |
| `Approved` | `Planning` | Coordinator (SCRUM-58) | named, not claimed |
| `Planning` | `Safety Review` | Coordinator (SCRUM-58) | named, not claimed |

`Completed`, `Cancelled` and `Rejected` are terminal. `Draft` carries no assignment, so it is unreachable by coordinator transitions (a cancel attempt from `Draft` refuses as *not assigned*, `P0003`, not as an invalid transition).

### Persistence and atomicity

- Both RPCs (`advance_event_request_by_coordinator`, `assign_event_request_coordinator`) `SELECT … FOR UPDATE` the same `event_requests` row first; the latest assignment is re-read inside the transaction and the update is scoped to the status seen under the lock (`0012`, `0014`, `0015`).
- Errcode contract, mapped by the service on codes never message text: `P0002` not found → `404`; `P0003` not the latest-assigned coordinator → `403`; `P0004` transition not allowed from the current status → `409`; `P0005` target holds no coordinator role / requirements unmet → `409`.
- `EXECUTE` is revoked from `PUBLIC` and granted to `service_role` only (`0013`, the `0006` defence-in-depth pattern).
- Status history is SCRUM-48's; this story's RPCs changed before its trigger existed, and SCRUM-48's concurrency tests ride the same lock.

### Assumptions and open questions

1. **Vocabulary drift (Jira decision needed).** AC1's recorded wording says ten approved statuses; the code now stores eleven (`Safety Review` inserted between `Planning` and `Confirmed` by SCRUM-60, migration `0029`). The frontend asserts eleven. Ask the story owner whether Jira AC1 should be updated or `Safety Review` recorded as an approved later addition.
2. **Transition set drift.** The `advance_event_request_by_coordinator` function now also accepts SCRUM-58's `Approved → Planning` and `Planning → Safety Review`. The SCRUM-28-owned transition table above stays as recorded; those moves are SCRUM-58's, tested there.
3. **AC4's real-Postgres race coverage.** SCRUM-48's `database/tests/test_event_status_history_concurrency.py` races transition-vs-transition on the same row lock (one wins, one `P0004`, one history row) — referenced, not relabelled. No test races **assignment**-vs-**transition** specifically; that remains a gap (`AC4-X3`).
4. **Historical evidence.** The previous catalogue's runs (157 backend tests, 38 authService, 55 frontend unit, database verifications on shared Supabase, PR #29 checks at commit `4c1b743`) are historical, not current evidence.

## Test case specification

Layers: A = API/controller (backend pytest), R = repository contract, D = database (SQL verifiers, real PostgreSQL functions), DBT = real-Postgres concurrency test (`database/tests/`), UI = frontend unit (Vitest), E = Playwright e2e (mock services).

| ID | AC | Test scenario | Technique | Pre-conditions | Test steps | Test data | Expected result | Forbidden side effects | Layer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AC1-H1 | AC1 | Every stored status is representable in the UI | Happy | The frontend vocabulary constant | Compare `EVENT_REQUEST_STATUSES` with the full list | — | All eleven values, `Safety Review` between `Planning` and `Confirmed` | The UI never drops a workflow state | UI |
| AC1-P1 | AC1 | Exactly `Completed`, `Cancelled`, `Rejected` are terminal | Partition | The vocabulary constant | `isTerminalStatus` over every status | — | Only the three terminal values | Coordinator action window excludes exactly these | UI |
| AC1-N1 | AC1 | An unknown status value is rejected | Negative | A request at any status | Attempt to store a value outside the vocabulary | e.g. `"Archived"` | Refused (`422` from the `EventRequestStatus` enum / CHECK constraint violation) | Nothing stored | A / D |
| AC1-B1 | AC1 | Every request starts as `Draft` | Boundary | New request | Create a request (SCRUM-11's creation suite) | `event_name` only | `201`; status `Draft` | — | A |
| AC2-P1 | AC2 | `Submitted → Under Review` by the assigned Coordinator | Partition | `Submitted`, assigned to `coord-1` | POST `/review` as `coord-1` | `coord-1` | `200`; `Under Review` | Nothing else changed | A |
| AC2-P2 | AC2 | Any non-terminal status → `Cancelled` | Partition | Assigned request seeded in each cancel source | POST `/cancellation` for each source | `coord-1` | `200`; `Cancelled` from every source | — | A |
| AC2-P3 | AC2 | `Confirmed → Completed` | Partition | Assigned request in `Confirmed` | POST `/completion` as `coord-1` | `coord-1` | `200`; `Completed` | — | A |
| AC2-P4 | AC2 | `Draft → Submitted` by the owning organiser | Partition | `Draft` with a complete payload | POST `/submit` (SCRUM-11/21 suite) | `organiser-1` | `200`; `Submitted` | No duplicate record | A |
| AC2-N1 | AC2 | Terminal statuses refuse cancellation (also AC7) | Negative | Request in `Completed`, `Cancelled` or `Rejected` | POST `/cancellation` for each | `coord-1` | `409` each time | Status stays at its terminal value | A |
| AC2-N2 | AC2 | Completion refuses every non-`Confirmed` source | Negative | Request in `Draft`, `Submitted`, `Under Review`, `Cancelled` | POST `/completion` for each | `coord-1` | `403` for `Draft` (no assignment), `409` for the rest | Status stays at its source value | A |
| AC2-N3 | AC2 | An unknown request 404s on any transition | Negative | Random uuid | POST `/cancellation` and `/completion` | — | `404` both | Nothing written | A |
| AC2-N4 | AC2, AC3 | `Submitted → Approved` is not this boundary's move | Negative | `Submitted`, assigned | `advance_event_request_by_coordinator(…, 'Approved')` | `verify-coordinator-a` | `P0004` (approval belongs to SCRUM-17) | Status stays `Submitted` | D |
| AC2-N5 | AC2, AC3 | Completion before `Confirmed` is refused | Negative | `Submitted`, assigned | `advance_event_request_by_coordinator(…, 'Completed')` | `verify-coordinator-a` | `P0004` | Status stays `Submitted` | D |
| AC3-H1 | AC3, AC2 | The locked function performs an allowed move in one statement | Happy | `Submitted`, assigned, row unlocked | `advance_event_request_by_coordinator(…, 'Under Review')` | `verify-coordinator-a` | Returned row has `Under Review` | Row locked `FOR UPDATE` for the whole decision | D |
| AC3-N1 | AC3 | An unknown request id is refused | Negative | Random uuid | Call the transition RPC | `1111…` id | `P0002` | Nothing written | D |
| AC3-N2 | AC3 | An unassigned request is refused | Negative | `Submitted`, never assigned; also a `Draft` | Call the transition RPC | `verify-coordinator-a` | `P0003` both (Drafts never carry an assignment) | Nothing written | D |
| AC3-N3 | AC3, AC5 | A coordinator who is not the assignee is refused | Negative | Assigned to coordinator A | Call as coordinator B | `verify-coordinator-b` | `P0003` | Status unchanged (asserted after the refusal block) | D |
| AC3-N4 | AC3 | An unknown target status is refused as not allowed | Negative | Any assigned request | Call with a target outside this boundary's pairs | — | `P0004` | Nothing written | D |
| AC3-N5 | AC3, AC2 | Refused calls leave the stored status untouched | Negative | After AC3-N1…N5 refusals | Read the request row | — | Status still `Submitted` | No partial write | D |
| AC3-N6 | AC3, AC7 | A repeated review is refused | Negative | Already `Under Review` | Repeat the same call | `verify-coordinator-a` | `P0004` | Status unchanged | D |
| AC3-N7 | AC3, AC5 | A reassigned-away coordinator is refused | Negative | Reassigned from A to B | Call as A | `verify-coordinator-a` | `P0003` | Nothing written | D |
| AC3-P1 | AC3, AC2 | Non-terminal → `Cancelled` through the RPC | Partition | `Under Review`, assigned to B after reassignment | `advance_event_request_by_coordinator(…, 'Cancelled')` | `verify-coordinator-b` | Returned row `Cancelled` | — | D |
| AC3-N8 | AC3, AC7 | `Cancelled` is terminal | Negative | Request `Cancelled` | Call again (cancel) | `verify-coordinator-b` | `P0004` | Nothing written | D |
| AC3-P2 | AC3, AC2 | `Confirmed → Completed` through the RPC | Partition | `Confirmed` seeded directly (venue/ops stories own that write) | `advance_event_request_by_coordinator(…, 'Completed')` | `verify-coordinator-a` | Returned row `Completed` | — | D |
| AC3-N9 | AC3, AC7 | `Completed` is terminal for cancel and complete | Negative | Request `Completed` | Cancel, then complete again | `verify-coordinator-a` | `P0004` both | Nothing written | D |
| AC3-X1 | AC3 | Only the server role executes the transition RPC | Cross-cutting | Migrations applied | `has_function_privilege` for `anon`, `authenticated`, `service_role` | — | `false`, `false`, `true` | Browser roles cannot reach the RPC | D |
| AC4-H1 | AC4 | The assignment function locks the same request row | Happy | Migrations applied | `pg_get_functiondef` of `assign_event_request_coordinator` | — | Definition contains `FOR UPDATE` on `event_requests` | Assignment can never run unlocked | D |
| AC4-H2 | AC4 | Assignment and reassignment run through the locked RPC and keep history | Happy | `Submitted` request | Assign, then reassign; count rows | `8888…` coordinator | Both succeed; two rows (history preserved) | No overwrite | D |
| AC4-H3 | AC4 | Assignment writes through the row-locking RPC, never a direct insert | Happy | Repository configured against Supabase | `repository.create(...)` and capture the request | `coord-1`, `ops-1` | POST `/rest/v1/rpc/assign_event_request_coordinator` with the three params | No race-prone direct insert | R |
| AC4-N1 | AC4 | A database-side state conflict still maps to a conflict | Negative | Fake raises `CoordinatorAssignmentRpcError("P0004")` after the API pre-check | POST assignment | `ops-1`, `coord-1` | `409` (never `500`) | No assignment row | A |
| AC4-N2 | AC4, AC5 | An invalid target is refused after the pre-check | Negative | Fake raises `CoordinatorAssignmentRpcError("P0005")` | POST assignment targeting an attendee | `attendee-1` | `409` "The selected user is not an Event Coordinator" | No assignment row | A |
| AC4-N3 | AC4 | A missing request is refused and inserts nothing | Negative | Random uuid | Call the assignment RPC | `7777…` id | `P0002` | Assignment count stays 0 | D |
| AC4-N4 | AC4 | Draft and terminal requests cannot acquire an assignment | Negative | Requests in `Draft` and `Completed` | Call the assignment RPC for each | `8888…` coordinator | `P0004` both | Assignment count stays 0 | D |
| AC4-N5 | AC4, AC5 | A non-coordinator identity is refused | Negative | Arbitrary authenticated user id, no coordinator role | Call the assignment RPC | `9999…` id | `P0005` | Assignment count stays 0 | D |
| AC4-X1 | AC4 | Concurrent transitions serialize on the row lock | Cross-cutting | Disposable local Postgres, SCRUM-48's fixtures | Two psql sessions transition the same request; one holds the lock via `pg_sleep` | `race-coordinator` | First commits; second gets `P0004`; exactly one new history row | Never two successes on one row | DBT |
| AC4-X2 | AC4 | Only the server role executes the assignment RPC | Cross-cutting | Migrations applied | `has_function_privilege` for `anon`, `authenticated`, `service_role` | — | `false`, `false`, `true` | — | D |
| AC4-X3 | AC4 | Assignment and transition raced in real Postgres | Cross-cutting | Disposable local Postgres | Reassign while a transition holds the row lock | — | Exactly one wins; the other waits then sees the fresh assignment | Never an authorised stale write | DBT |
| AC5-P1 | AC5 | Coordinator details are visible only with a relationship | Partition | Assigned request; caller varies over roles and relationships | GET `/event-requests/{id}/coordinator` as each of seven role/relationship pairs | owner, other, ops manager, assigned, unrelated coordinator, staff, staff+assigned | `200` for owner, ops manager, assigned (incl. staff holding the role); `404` for unrelated organiser/coordinator; `403` for unrelated staff | No disclosure to unrelated callers | A |
| AC5-N1 | AC5 | Transitions require a session | Negative | No Authorization header | POST `/cancellation`, `/completion`, `/review` | — | `401` each | Nothing written | A |
| AC5-N2 | AC5 | Cancelling a `Draft` is forbidden, not conflicted | Negative | `Draft` (carries no assignment) | POST `/cancellation` | `coord-1` | `403`; status stays `Draft` | No status write | A |
| AC5-N3 | AC5 | A reassigned-away coordinator cannot cancel | Negative | Assigned to `coord-1`, then reassigned to `coord-2` | POST `/cancellation` as `coord-1` | `coord-1` | `403`; status stays `Submitted` | No status write | A |
| AC5-N4 | AC5 | Cancelling without any assignment is refused | Negative | No assignment exists | POST `/cancellation` | `coord-1` | `403` | No status write | A |
| AC5-N5 | AC5 | Only coordinators call the transition endpoints | Negative | Organiser and operations manager, assigned | POST `/cancellation` and `/completion` with a real role lookup | `event_organiser` / `event_operations_manager` caller | `403` each | No status write | A |
| AC5-N6 | AC5 | Completion refuses a coordinator other than the assignee | Negative | Assigned to `coord-2`, request `Confirmed` | POST `/completion` as `coord-1` | `coord-1` | `403`; status stays `Confirmed` | No status write | A |
| AC5-N7 | AC5 | Completion without any assignment is refused | Negative | No assignment exists; request `Confirmed` | POST `/completion` | `coord-1` | `403`; status stays `Confirmed` | No status write | A |
| AC6-H1 | AC6 | The progress display marks the current stage | Happy | Request `Under Review` | Render `StatusProgress` | — | The `Under Review` list item carries `aria-current="step"` | Future stages not implied as done | UI |
| AC6-H2 | AC6 | A known assignment is announced without changing the workflow stage | Happy | Request `Submitted`, coordinator assigned | Render `StatusProgress` with `coordinatorAssigned` | — | "…coordinator has been assigned" copy; current stage still `Submitted` | Status not advanced | UI |
| AC6-P1 | AC6 | Closed statuses stay reachable through All only | Partition | Requests `Cancelled` and `Rejected` | `groupRequests` | — | Only under `all`; no draft/submitted/in-progress/completed entries | No Closed tab invented | UI |
| AC6-P3 | AC6 | A later-stage status shows earlier stages done | Partition | Request `Confirmed` | Render `StatusProgress` | — | `Confirmed` current; Draft, Submitted, Under Review announced done | — | UI |
| AC6-P4 | AC6 | `Completed` reads as the final reached stage | Partition | Request `Completed` | Render `StatusProgress` | — | `Completed` current; "reached the final stage" | No stage implied beyond it | UI |
| AC6-P5 | AC6 | A completed event files under the Completed tab | Partition | Request `Completed` | `groupRequests` | — | Under `completed`; in-progress empty | — | UI |
| AC6-N1 | AC6 | Terminal outcomes keep context without implying success | Negative | Requests `Rejected` and `Cancelled` | Render `StatusProgress` for each | — | Full journey shown with explicit "not reached" / "ended as cancelled" notices | Later stages not implied as done | UI |
| AC6-B1 | AC6 | A draft previews the entire journey | Boundary | Request `Draft` | Render `StatusProgress` | — | All eight stages listed; nothing marked done; "Not submitted yet" | — | UI |
| AC6-X1 | AC6, AC2, AC5 | The submitted-to-review journey is visible to each role | Cross-cutting | Mock services; one organiser, one coordinator, one unrelated coordinator | Playwright: organiser submits, manager assigns via API, coordinator starts review, organiser sees `Under Review`, unrelated coordinator sees nothing (and 404s on the direct URL) | "Anniversary Fun Run" | Status visible with the right tab, stage and action per role; assignment alone never moves the status out of `Submitted` | Unrelated coordinator sees no data | E |
| AC6-X2 | AC6, AC2 | Cancellation closes the event everywhere; completion files it | Cross-cutting | Mock services; in-flight assigned request; one `Confirmed` seed | Playwright: coordinator cancels, organiser sees it only under All; coordinator completes the confirmed gala, organiser sees it under Completed | "Anniversary Fun Run", "Confirmed Charity Gala" | `Cancelled`/`Completed` shown with no further actions | — | E |
| AC7-N1 | AC7, AC3 | Repeated review is refused (API level) | Negative | Already `Under Review` | POST `/review` again by the same coordinator | `coord-1` | `409` | Status stays `Under Review` | A |
| AC7-N2 | AC7 | A stale action after cancellation is refused without a second mutation | Negative | Coordinator acted on a page since cancelled | Cancel, then POST `/review` from the stale view | `coord-1` | Cancel `200`; review `409`; status stays `Cancelled` | Exactly one mutation | A |
| AC7-N3 | AC7 | Repeated cancellation is refused | Negative | Request already `Cancelled` | POST `/cancellation` again | `coord-1` | `409` (the terminal-source case) | Status stays `Cancelled` | A |

## Latest execution record

> Not executed in this pass. This pass converted the catalogue and added label comments (including to the two SQL verifiers); every automated row names its test. The previous catalogue's runs (PR #29 era, commit `4c1b743`: database verifiers passed on shared Supabase, 157 backend / 38 authService / 55 frontend unit tests, Playwright suite and CI green) are historical and are not current evidence; re-run before the story is marked Done.

| ID | Automation status | Actual result | Execution status | Build or commit | Executed by and date | Remarks and evidence |
| --- | --- | --- | --- | --- | --- | --- |
| AC2-P3, AC2-N1, AC2-N2, AC2-N3, AC5-N1…N7, AC7-N2 | Automated (label added in this pass) | Not run | Not executed | Working tree, `docs/testcase-gap-sweep`, 1 Nov 2026 | Claude for Yang Xue, 1 Nov 2026 | `backend/eventRequestService/tests/test_event_transition_controller.py` (AC2-N3 labels both missing-request tests); repository faked |
| AC7-N1, AC7-N3 | Automated (labels name SCRUM-14 AC4-N5 / SCRUM-28 AC2-N1; untouched) | Not run | Not executed | Working tree, 1 Nov 2026 | Claude for Yang Xue, 1 Nov 2026 | Same file; `test_start_review_refused_once_already_under_review` (SCRUM-14's label) and `test_cancel_refused_from_terminal_status` (this catalogue's AC2-N1 label) |
| AC2-P1 | Automated (label names SCRUM-14 AC4-H1 on the same behaviour; untouched) | Not run | Not executed | Working tree, 1 Nov 2026 | Claude for Yang Xue, 1 Nov 2026 | `test_event_transition_controller.py::test_assigned_coordinator_can_start_review` |
| AC2-P2 | Automated (label predates this pass, `AC6-P1 (partition, SCRUM-60)`; untouched) | Not run | Not executed | Working tree, 1 Nov 2026 | Claude for Yang Xue, 1 Nov 2026 | `test_assigned_coordinator_can_cancel_from_every_non_terminal_status` — the parametrization is exactly this partition |
| AC2-P4, AC1-B1 | Automated (SCRUM-11/21 suite; untouched) | Not run | Not executed | Working tree, 1 Nov 2026 | Claude for Yang Xue, 1 Nov 2026 | `test_event_request_controller.py::test_submit_completed_draft`, `::test_create_and_get_incomplete_draft` |
| AC4-N1, AC4-N2, AC5-P1 | Automated (label added in this pass) | Not run | Not executed | Working tree, 1 Nov 2026 | Claude for Yang Xue, 1 Nov 2026 | `backend/eventRequestService/tests/test_coordinator_assignment_controller.py` |
| AC4-H3 | Automated (label added in this pass) | Not run | Not executed | Working tree, 1 Nov 2026 | Claude for Yang Xue, 1 Nov 2026 | `backend/eventRequestService/tests/test_coordinator_assignment_repository.py::test_create_sends_expected_supabase_request` |
| AC2-N4, AC2-N5, AC3-H1, AC3-P1, AC3-P2, AC3-N1…N9, AC3-X1 | Automated (label added in this pass) | Not run | Not executed | Working tree, 1 Nov 2026 | Claude for Yang Xue, 1 Nov 2026 | `database/verify_event_request_status_transitions.sql` — manual rollback-only verifier for the deployed functions; the previous catalogue recorded a pass on shared Supabase, re-run it before Done |
| AC4-H1, AC4-H2, AC4-N3…N5, AC4-X2 | Automated (label added in this pass) | Not run | Not executed | Working tree, 1 Nov 2026 | Claude for Yang Xue, 1 Nov 2026 | `database/verify_atomic_coordinator_assignment.sql` — same manual-verifier caveat |
| AC4-X1 | Automated (SCRUM-48's test; labels untouched) | Not run | Not executed | Working tree, 1 Nov 2026 | Claude for Yang Xue, 1 Nov 2026 | `database/tests/test_event_status_history_concurrency.py` (its own labels `AC1-X1`/`AC1-X2`, SCRUM-48): racing transitions serialize on the lock — one commits, one `P0004`, one history row |
| AC1-P1, AC6-H1, AC6-H2, AC6-P1, AC6-P3, AC6-P4, AC6-P5 | Automated (label added in this pass) | Not run | Not executed | Working tree, 1 Nov 2026 | Claude for Yang Xue, 1 Nov 2026 | `frontend/__tests__/event-request-status.test.tsx` |
| AC1-H1, AC6-N1, AC6-B1 | Automated (labels predate this pass — `AC5-X8` ×4 and `AC6-P2` for SCRUM-60; untouched) | Not run | Not executed | Working tree, 1 Nov 2026 | Claude for Yang Xue, 1 Nov 2026 | Same file: the eleven-status constant, the rejected/cancelled notices, the draft journey |
| AC6-X1, AC6-X2 | Automated (label added in this pass) | Not run | Not executed | Working tree, 1 Nov 2026 | Claude for Yang Xue, 1 Nov 2026 | `frontend/e2e/track-event-status.spec.ts`; runs against mock Node servers, not the real services |
| AC1-N1 | Automated (backfilled 6 Nov 2026 at the API/enum layer — the D-layer CHECK stays asserted only by the migrations) | `POST /event-requests/{id}/decision` with `"Archived"` → 422 (`enum` error at `body.decision`); stored status unchanged, no decision row | Pass | working tree, branch `test/backfill-planned-cases` | Claude for Yang Xue, 6 Nov 2026 | `backend/eventRequestService/tests/test_event_transition_controller.py::test_unknown_status_value_is_refused_without_storage` — the one route accepting a caller-supplied status; distinct from SCRUM-17 AC2-N3's in-vocabulary validator case (`"Completed"`) |
| AC4-X3 | Planned | Not run | Not executed | — | — | gap: no real-Postgres race between `assign_event_request_coordinator` and `advance_event_request_by_coordinator` — story owner to write; SCRUM-48's test (AC4-X1) covers the transition-vs-transition half |

## Release 1 hotfix test cases (added 6 November 2026)

These cases belong to this story and are labelled in the automated tests, but until now they were specified only in summary on the hotfix page (`release_1_hotfixes_testcases.md`). They are recorded here so the story document, the code labels and `TestCaseLookup.xlsx` agree; the IDs are the lookup sheet's, with the hotfix number prefixed to the case ID. They were executed as part of the hotfix verification runs recorded on that page (1 and 3 November 2026); per-case results are not restated in this document.

Hotfix H7 — Postponed was missing from the Lead's list; a reassignment from a stale screen won.

| ID | AC | Test scenario | Technique | Expected result | Layer | Automated test |
| --- | --- | --- | --- | --- | --- | --- |
| H7 AC4-N6 | AC4 (Jira, 1 Nov) | The P0002/P0004/P0005/P0006 errcode contract survives the transport, so the service maps conflicts on codes, not message text | Negative | The P0002/P0004/P0005/P0006 errcode contract survives the transport, so the service maps conflicts on codes, not message text | Repository | backend/eventRequestService/tests/test_coordinator_assignment_repository.py::test_create_preserves_assignment_rpc_error_code |
