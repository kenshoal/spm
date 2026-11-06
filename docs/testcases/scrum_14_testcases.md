# SCRUM-14 — Assign an Event Coordinator

Source: issue tracker SCRUM-14 (Operations Manager assigns an Event Coordinator to a submitted request). Builds on SCRUM-11/21 (submission), SCRUM-10 (roles), SCRUM-28 (the status model and the shared row lock the assignment RPC takes), SCRUM-37 (notificationService, which receives this story's `coordinator_assigned` hook) and SCRUM-62 (the Event Coordinator Lead workspace that later reused these endpoints).

Status (1 November 2026): **AI-drafted conversion of the 24 September 2026 catalogue to the standard format; teammate review pending (`testing.md` §10).** The AC wording below is as recorded in the converted catalogue, derived from the previous document's criterion purposes; issue tracker remains the source of truth.

## Story contract

### Acceptance criteria

- **AC1:** Given requests in mixed statuses, when the Operations Manager opens the awaiting-assignment queue, then only `Submitted` requests without a Coordinator are listed newest first; Drafts and already-assigned requests are absent; an empty queue answers `200 []`, not `404`; and submission itself raises no notification to the manager (SCRUM-11's handed-over half of the criterion).
- **AC2:** Given any request and caller, when an assignment is attempted, then only an Operations Manager — including one holding the role among several — may assign, and only a non-Draft, non-terminal request accepts it: a Draft or terminal status returns `409`, an unknown request `404`, a wrong role `403`, a missing session `401`. The coordinator picker lists only Event Coordinators, and only for callers with assignment duties.
- **AC3:** Given a `Submitted` request, when the Operations Manager assigns a Coordinator, then the assignment is retrievable, the request's status stays `Submitted`, and a request with no assignment answers `404` — distinct from a missing request.
- **AC4:** Given an assigned request, when review starts, then only the latest-assigned Coordinator holding the `event_coordinator` role moves `Submitted` → `Under Review`; assignment alone never advances the status; another coordinator, an unassigned request, a Draft, a repeat and an unknown request are refused.
- **AC5:** Given a successful assignment, then one `coordinator_assigned` message naming the Coordinator, the request and the assigning manager is posted; an unreachable, failing or unconfigured endpoint is logged and swallowed; assignment succeeds in every case. Delivery is notificationService's duty — named, not claimed.
- **AC6:** Given an assigned request, when the Operations Manager reassigns it, then the current Coordinator is the new one, the previous row survives as history, the request stays out of the awaiting-assignment queue and in the current-assignments overview until it closes, and the overview is closed to non-managers. "Current" is the highest `id`, not the latest `assigned_at` (server-clock resolution cannot order two quick assignments).

### Scope

- **Included:** the awaiting-assignment queue, assignment and reassignment end to end (authService picker, API, service, repository, Operations workspace UI, e2e), the `coordinator_assigned` hook contract, and review start as the first coordinator transition.
- **Excluded:** review decisions beyond starting review (SCRUM-17); changes-requested and resubmission (SCRUM-35); planning, safety review and confirmation (SCRUM-58/60, venue stories); cancellation and completion (SCRUM-28/57); notification delivery (SCRUM-37/38); role administration beyond the picker.

### Actors and relationship permissions

- **Operations Manager** (`event_operations_manager`, possibly among several roles): the only assigner; owns the queue and the current-assignments overview; may list `event_coordinator` holders for the picker.
- **Event Coordinator** (`event_coordinator`): the assignee; only the latest-assigned may start review.
- The owning organiser, the assigned coordinator and the Operations Manager may read assignment details; unrelated organiser/coordinator get `404`, unrelated staff `403`; no session `401`.

### Allowed state transitions

| From | To | Trigger |
| --- | --- | --- |
| — | `Submitted` | Owning organiser submits (SCRUM-21; not this story) |
| `Submitted` | `Under Review` | Assigned Coordinator starts review (AC4) |

Assignment never changes the status (AC3). Decisions beyond starting review, cancellation and completion belong to SCRUM-17/35/28/57.

### Persistence and atomicity

- `event_coordinator_assignments` is append-only: reassignment inserts a row, nothing is overwritten, and "current" is the highest `id` (AC6).
- Assignment writes through the `assign_event_request_coordinator` RPC (`0011_event_coordinator_assignments.sql`, hardened by `0014_atomic_coordinator_assignment.sql`), which locks the `event_requests` row `FOR UPDATE`, re-checks the state and the coordinator role inside the transaction (SCRUM-28's shared lock), and refuses with `P0002` / `P0004` / `P0005` — mapped to `404` / `409` / `409`.
- The notification hook runs after the assignment commits; a failure is logged, never raised (AC5).

### Assumptions and open questions

1. **Delivery, named not claimed.** AC5 is met at the hook-contract level; end-to-end delivery depends on notificationService (SCRUM-37/38). The old catalogue's "no Notification System exists in this increment" limitation is historical — the consumer now exists, but delivery evidence belongs to those stories.
2. **The picker is scoped to `staff_roles`.** `/operations/assignments` builds its coordinator list from authService's `staff_roles` table; a coordinator whose role exists only in Supabase `app_metadata` will not appear. Reading of the code, not verified against live data.
3. **Schema note.** `migrations/0007_event_requests.sql` declares `CHECK (status IN ('Draft', 'Submitted'))`; the full vocabulary arrives through `0011_event_request_review_status.sql` and `0029_safety_review_status.sql`. A fresh environment must apply the whole chain, not `0007` alone. Two migration files both carry the number `0011` (assignments and review status) — a numbering collision flagged for the database owner.
4. **Review status vocabulary drift.** The criteria were written when `event_requests` held ten statuses; SCRUM-60 later added `Safety Review` (eleven). The ACs here do not depend on the count, but SCRUM-28 AC1's does — see that catalogue.

### Test data and environments

Backend tests run against the fakes in `tests/test_event_request_controller.py` (`FakeEventRequestRepository`, `FakeCoordinatorAssignmentRepository`): organiser `organiser-1`, Operations Manager `ops-1`, coordinators `coord-1`/`coord-2`, `Bearer <id>` session headers. authService tests mock the Supabase admin client. Frontend unit tests render the components directly; the e2e spec runs against mock Node servers (see `frontend/README.md`), not the real services.

## Test case specification

Layers: A = API/controller (backend pytest), S = domain service, R = repository contract, A2 = authService API, U = frontend unit (Vitest), F = frontend server action (Vitest), E = Playwright e2e (mock services), Client = notification client contract.

| ID | AC | Test scenario | Technique | Pre-conditions | Test steps | Test data | Expected result | Forbidden side effects | Layer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AC1-H1 | AC1 | The queue lists Submitted requests that still need a Coordinator | Happy | One `Submitted`, unassigned request | GET `/event-requests/awaiting-assignment` as `ops-1` | `ops-1` | `200`; exactly that request, newest first | Nothing written | A |
| AC1-H2 | AC1 | Each awaiting request renders with a way to assign | Happy | One awaiting request, two coordinators on file | Render `AwaitingList` | `r1` "Gala Dinner", `coord-1/2` | Card shows a Coordinator combobox and an Assign control | — | U |
| AC1-P1 | AC1 | Assigned requests drop out of the queue | Partition | One assigned, one unassigned `Submitted` request | Assign one, then GET the queue | `coord-1` | Only the unassigned id is listed | Assignment untouched | A |
| AC1-P2 | AC1 | Only `Submitted` requests belong in the queue | Partition | One `Draft` | GET the queue | — | `200 []`; Draft absent | Draft untouched | A |
| AC1-P3 | AC1 | The queue subtracts assigned request ids | Partition | Two `Submitted` requests, one with an assignment row | `assigned_event_request_ids(["request-1","request-2"])` | `request-1` assigned | Query filters `event_request_id in.(…)` and returns `{request-1}` | — | R |
| AC1-B1 | AC1 | An empty queue explains itself in the UI | Boundary | Nothing awaits | Render `AwaitingList` with no requests | — | "Nothing is waiting for a coordinator." | — | U |
| AC1-B2 | AC1 | Zero submitted requests skip the assignment lookup | Boundary | Nothing submitted | `list_awaiting_assignment()` | — | `[]` with no second round trip (repository would raise if called) | — | S |
| AC1-B3 | AC1 | An empty candidate list skips Supabase | Boundary | No requests to check | `assigned_event_request_ids([])` | — | Empty set; Supabase not called | — | R |
| AC1-N1 | AC1 | The queue is closed to non-managers | Negative | Caller holds only `event_coordinator` | GET `/event-requests/awaiting-assignment` | `event_coordinator` caller | `403` | Nothing written | A |
| AC1-N2 | AC1 | Submission raises no notification to the manager | Negative | An organiser submits | Inspect the submission notice the client posts | `organiser-1` | The only `event_request_submitted` recipient is the organiser | No manager notification exists to send | Client |
| AC2-H1 | AC2 | An Operations Manager assigns to a `Submitted` request | Happy | `Submitted`, unassigned request | POST `/event-requests/{id}/coordinator` | `ops-1`, `coord-1` | `201`; body names request, coordinator and assigner | Status stays `Submitted` | A |
| AC2-H2 | AC2 | The workspace action posts the chosen coordinator | Happy | Manager on the assignments page | Submit the assign server action | `coord-1`, request id | POST to `/event-requests/{id}/coordinator`; success state and revalidate | No write on failure | F |
| AC2-H3 | AC2 | The manager can list coordinators for the picker | Happy | Manager calls authService | GET `/auth/users?role=event_coordinator` | `event_operations_manager` caller | `200`; coordinator id/email pairs, emails resolved | — | A2 |
| AC2-P1 | AC2 | Operations Manager among several roles may assign | Partition | Caller roles `["venue_staff", "event_operations_manager"]` | POST assignment with a real role lookup | Multi-role caller | `201`; `assigned_by` is the caller | — | A |
| AC2-N1 | AC2 | A Draft refuses assignment | Negative | `Draft` request | POST assignment | `coord-1` | `409` | No assignment row | A |
| AC2-N2 | AC2 | Terminal statuses refuse assignment | Negative | Request in `Completed`, `Cancelled` or `Rejected` | POST assignment for each | `coord-1` | `409` each time | No assignment row; status unchanged | A |
| AC2-N3 | AC2 | An unknown request 404s | Negative | Random uuid | POST assignment | — | `404` | Nothing written | A |
| AC2-N4 | AC2 | Both endpoints require a session | Negative | No Authorization header | POST and GET without a bearer token | — | `401` both | Nothing written | A |
| AC2-N5 | AC2 | A non-manager caller is refused | Negative | Caller holds only `event_coordinator` | POST assignment | `event_coordinator` caller | `403` | No assignment row | A |
| AC2-N6 | AC2 | An empty choice is caught before any request is sent | Negative | Form with a blank coordinator | Submit the action | `"  "` | Validation message; fetch never called | No write | F |
| AC2-N7 | AC2 | A refusal shows the backend's reason | Negative | Backend answers `409` "not an Event Coordinator" | Submit the action | `coord-1` | Message shown verbatim; no revalidate | No write | F |
| AC2-N8 | AC2 | A request deleted since page load is explained | Negative | Backend answers `404` | Submit the action | `coord-1` | "This request no longer exists. Refresh the page." | No write | F |
| AC2-N9 | AC2 | An unreachable API leaves a retryable error | Negative | fetch rejects | Submit the action | `coord-1` | Retry message; manager stays on the page | No write | F |
| AC2-N10 | AC2 | An expired session sends the manager to sign in | Negative | Backend answers `401` | Submit the action | — | Redirect to sign-in | No write | F |
| AC2-N11 | AC2 | The manager may list coordinators only | Negative | Manager asks for `venue_staff` | GET `/auth/users?role=venue_staff` | Manager caller | `403` | — | A2 |
| AC2-N12 | AC2 | Roles without assignment duties cannot enumerate staff | Negative | Organiser asks for coordinators | GET `/auth/users?role=event_coordinator` | `event_organiser` caller | `403` | — | A2 |
| AC2-N13 | AC2 | Listing staff requires a session | Negative | No Authorization header | GET `/auth/users?role=event_coordinator` | — | `401` | — | A2 |
| AC2-N14 | AC2 | A role-store outage is a gateway failure, not an empty list | Negative | Supabase raises `APIError` | GET coordinators | Manager caller | `502` "Role store unavailable" | Not presented as `200 []` | A2 |
| AC2-B1 | AC2 | With nobody to choose, the form explains why | Boundary | Coordinator directory empty | Render `AssignCoordinatorForm` with no coordinators | — | No combobox; "No Event Coordinator is available to assign." | — | U |
| AC2-B2 | AC2 | A dangling role row does not break the picker | Boundary | One `staff_roles` row belongs to a deleted account | GET coordinators | Manager caller | `200`; deleted account skipped | — | A2 |
| AC2-X1 | AC2 | Only admins enumerate beyond the picker's role | Cross-cutting | Admin asks for any role | GET `/auth/users?role=venue_staff` as admin | `admin` caller | `200` (contrast with AC2-N11/N12) | — | A2 |
| AC3-H1 | AC3 | Assignment records the Coordinator without advancing the status | Happy | `Submitted` request | Assign, then read the request row | `ops-1`, `coord-1` | Assignment stored; status still `Submitted` | No status write | A |
| AC3-H2 | AC3 | An assigned request shows who is responsible | Happy | Assigned request in the overview | Render `AssignedList` | `coord-1` = alex@example.com | Card shows the coordinator email and a Reassign control | — | U |
| AC3-N1 | AC3 | No assignment yet is 404, distinct from a missing request | Negative | `Submitted` request, never assigned | GET `/event-requests/{id}/coordinator` | — | `404` | Nothing written | A |
| AC4-H1 | AC4 | The assigned Coordinator starting review moves `Submitted` → `Under Review` | Happy | `Submitted` request assigned to `coord-1` | POST `/event-requests/{id}/review` as `coord-1` | `coord-1` | `200`; status `Under Review` | Only the status changed | A |
| AC4-N1 | AC4 | Assignment alone must not start review | Negative | Assignment just created | Read the request row | `coord-1` | Status still `Submitted`, never `Planning` | No status write | A |
| AC4-N2 | AC4 | Review refuses a coordinator who is not assigned | Negative | Request assigned to `coord-1` | POST review as `coord-2` | `coord-2` | `403`; status stays `Submitted` | No status write | A |
| AC4-N3 | AC4 | Review refuses an unassigned request | Negative | No assignment exists | POST review as any coordinator | `coord-1` | `403` | No status write | A |
| AC4-N4 | AC4 | Review refuses a Draft | Negative | `Draft` with an assignment seeded | POST review by the assignee | `coord-1` | `409` | No status write | A |
| AC4-N5 | AC4 | Review refuses a repeat (also SCRUM-28 AC7) | Negative | Request already `Under Review` | POST review again by the same coordinator | `coord-1` | `409` | Status stays `Under Review` | A |
| AC4-N6 | AC4 | Review on a missing request 404s | Negative | Random uuid | POST review | — | `404` | Nothing written | A |
| AC4-N7 | AC4 | Role is checked even when the id matches the assignment | Negative | Caller id equals the assignee but holds `attendee` | POST review with a real role lookup | `attendee` caller | `403` | No status write | A |
| AC4-X1 | AC4 | Review requires a session like every transition | Cross-cutting | No Authorization header | POST `/review` (shared parametrized case with cancellation and completion) | — | `401` | Nothing written | A |
| AC5-H1 | AC5 | Assignment notifies the assigned Coordinator with the right details | Happy | `Submitted` request, spy notification client | `service.assign(...)` | `coord-1`, `ops-1` | One `coordinator_assigned` call naming request, coordinator, assigner | — | S |
| AC5-N1 | AC5 | Without a configured client, assignment still succeeds | Negative | No notification client | `service.assign(...)` | `coord-1` | Assignment returned; no error | No partial write | S |
| AC5-H2 | AC5 | The client posts the agreed payload | Happy | Endpoint configured | `notify_coordinator_assigned(...)` | `req-1`, `coord-1`, `ops-1` | POST with `event_type`, `recipient_id`, payload as designed | — | Client |
| AC5-N2 | AC5 | Unconfigured means no call is attempted | Negative | No URL configured | `notify_coordinator_assigned(...)` | — | `httpx.post` never called | Nothing sent | Client |
| AC5-N3 | AC5 | A connection failure is swallowed | Negative | `httpx.post` raises `ConnectError` | `notify_coordinator_assigned(...)` | — | Returns; nothing raised | Assignment not undone | Client |
| AC5-N4 | AC5 | A non-2xx response is swallowed too | Negative | Endpoint answers `500` | `notify_coordinator_assigned(...)` | — | Returns; nothing raised | Assignment not undone | Client |
| AC6-H1 | AC6, AC3 | Reassignment returns the latest Coordinator and preserves history | Happy | Request assigned to `coord-1` | Reassign to `coord-2`, then GET the coordinator | `coord-1`, `coord-2` | `200` with `coord-2`; two assignment rows | First row not overwritten; status unchanged | A |
| AC6-H2 | AC6 | A reassigned request stays out of the awaiting queue | Happy | Request assigned twice | `list_awaiting_assignment()` | `coord-1`, `coord-2` | Request absent | — | S |
| AC6-H3 | AC6 | Reassignment never offers the coordinator already responsible | Happy | Assigned to `coord-1`, two coordinators on file | Render `AssignCoordinatorForm` with `currentCoordinatorId` | `coord-1`, `coord-2` | Options are the placeholder and `coord-2` only | — | U |
| AC6-H4 | AC6 | The reassign form reports who is being replaced | Happy | Reassigning `coord-1` | Render the form, inspect hidden field | `coord-1` | `current_coordinator_id=coord-1` submitted | — | U |
| AC6-H5 | AC6 | Reassignment says "reassigned", not "assigned" | Happy | Request already has a coordinator | Submit the action with `current_coordinator_id` | `coord-2`, `coord-1` | Message "Coordinator reassigned." | — | F |
| AC6-H6 | AC6 | The overview lists each request once with the latest Coordinator | Happy | One assigned request, one never assigned; two assignments | GET `/event-requests/assignments` | `coord-1`, `coord-2` | Assigned request only; `coord-2` shown | Unassigned request absent | A |
| AC6-P1 | AC6 | Terminal requests are not offered for reassignment | Partition | Assigned request moved to `Cancelled` | GET `/event-requests/assignments` | — | `200 []` | — | A |
| AC6-P2 | AC6 | Requests stay reassignable once review has started | Partition | Assigned request in `Under Review` | GET `/event-requests/assignments` | — | Request listed | — | A |
| AC6-P3 | AC6 | Requests stay reassignable through later in-flight statuses | Partition | Assigned request in `Safety Review` | GET `/event-requests/assignments` | — | Request listed | — | A |
| AC6-P4 | AC6 | "Current" is the highest id, not the latest timestamp | Partition | Two assignment rows in quick succession | `latest_for_event_request(id)` | `coord-2` row, higher id | Query orders `id.desc`, limit 1 | Timestamp ordering never used | R |
| AC6-N1 | AC6 | The overview is closed to non-managers | Negative | Caller holds only `event_coordinator` | GET `/event-requests/assignments` | `event_coordinator` caller | `403` | Nothing written | A |
| AC6-B1 | AC6 | Never-assigned means "none", not an error | Boundary | No assignment rows | `latest_for_event_request(id)` | — | `None` | — | R |
| AC6-B2 | AC6 | No in-flight requests skip the assignment lookup | Boundary | Nothing in flight | `list_current_assignments()` | — | `[]` without a repository call | — | S |
| AC6-B3 | AC6 | Reassignment with no alternative explains itself | Boundary | Current coordinator is the only one on file | Render `AssignCoordinatorForm` | `coord-1` | No combobox; "No other Event Coordinator is available." | — | U |
| AC6-B4 | AC6 | A fresh assignment sends no hidden prior coordinator | Boundary | No current coordinator | Render `AssignCoordinatorForm` without `currentCoordinatorId` | — | No `current_coordinator_id` field | — | U |
| AC6-X1 | AC6 | The manager assigns and reassigns in the browser | Cross-cutting | Mock services running | Playwright journey `manager assigns and reassigns a submitted request` | — | Queue, assignment, reassignment visible end to end | — | E |

## Latest execution record

> Not executed in this pass. This pass converted the catalogue and added label comments; every row below names its automated test. The previous catalogue's runs (24 September 2026, commit `c24a269` on `feat/frontend-sprint1-gaps`: eventRequestService 162 passed, authService 45 passed, frontend 115 unit + 17 e2e passed, lint/typecheck clean) are historical and are not current evidence; re-run before the story is marked Done.

| ID | Automation status | Actual result | Execution status | Build or commit | Executed by and date | Remarks and evidence |
| --- | --- | --- | --- | --- | --- | --- |
| AC1-H1, AC1-P1…P3, AC1-B2…B3, AC1-N1, AC2-H1, AC2-P1, AC2-N1…N5, AC3-H1, AC3-N1, AC4-H1, AC4-N1…N7, AC6-H1, AC6-H2, AC6-H6, AC6-P1, AC6-P2, AC6-P4, AC6-N1, AC6-B1, AC6-B2 | Automated (label added in this pass) | Not run | Not executed | Working tree, `docs/testcase-gap-sweep`, 1 Nov 2026 | Claude for Yang Xue, 1 Nov 2026 | `backend/eventRequestService/tests/test_coordinator_assignment_controller.py` (A), `test_coordinator_assignment_service.py` (S), `test_coordinator_assignment_repository.py` (R), `test_event_transition_controller.py` (A); repository faked |
| AC2-H2, AC2-N6…N10, AC6-H5 | Automated (label added in this pass) | Not run | Not executed | Working tree, 1 Nov 2026 | Claude for Yang Xue, 1 Nov 2026 | `frontend/__tests__/operations-actions.test.ts` (F) |
| AC1-H2, AC1-B1, AC2-B1, AC3-H2, AC6-H3, AC6-H4, AC6-B3, AC6-B4 | Automated (label added in this pass) | Not run | Not executed | Working tree, 1 Nov 2026 | Claude for Yang Xue, 1 Nov 2026 | `frontend/__tests__/operations.test.tsx` (U) |
| AC2-H3, AC2-N11…N14, AC2-B2, AC2-X1 | Automated (label added in this pass) | Not run | Not executed | Working tree, 1 Nov 2026 | Claude for Yang Xue, 1 Nov 2026 | `backend/authService/tests/test_registration.py` (A2); Supabase admin client mocked |
| AC5-H1, AC5-N1, AC5-H2, AC5-N2…N4 | Automated (labels predate this pass and do not name SCRUM-14 — see notes) | Not run | Not executed | Working tree, 1 Nov 2026 | Claude for Yang Xue, 1 Nov 2026 | `test_coordinator_assignment_service.py` (AC5-H1/N1), `test_notification_client.py` (AC5-H2, AC5-N2…N4) |
| AC6-P3 | Automated (label predates this pass; reads `AC6-P3 (partition, SCRUM-60)`, left untouched) | Not run | Not executed | Working tree, 1 Nov 2026 | Claude for Yang Xue, 1 Nov 2026 | `test_coordinator_assignment_controller.py::test_current_assignments_include_requests_in_safety_review` |
| AC1-N2 | Automated (SCRUM-37's label, untouched) | Not run | Not executed | Working tree, 1 Nov 2026 | Claude for Yang Xue, 1 Nov 2026 | `test_notification_client.py::test_submission_posts_organiser_confirmation` proves the only submission notice names the Organiser |
| AC4-X1 | Automated (label added for SCRUM-28 AC5-N1 on the same test, left intact) | Not run | Not executed | Working tree, 1 Nov 2026 | Claude for Yang Xue, 1 Nov 2026 | `test_event_transition_controller.py::test_transitions_require_bearer_session` (the `/review` leg) |
| AC6-X1 | Automated (file outside this pass; not relabelled) | Not run | Not executed | Working tree, 1 Nov 2026 | Claude for Yang Xue, 1 Nov 2026 | `frontend/e2e/assign-coordinator.spec.ts`, scenario "manager assigns and reassigns a submitted request"; mock services, not the real backend |

## Notes carried from the previous catalogue

- **Existing labels left untouched.** `test_coordinator_assignment_service.py` carries `AC2-H1`/`AC2-N1` on the two assignment-notify tests and `AC4-*` on the four unassigned-notice tests; the former do not match this catalogue's numbering (the notify criterion is AC5) and name no story, and the latter evidence SCRUM-62 AC4 (see `notification_client.py`'s docstring). They are recorded here under AC5 with their existing labels intact.
- **Schema notes.** `event_coordinator_assignments` is captured in `migrations/0011_event_coordinator_assignments.sql` (`coordinator_id`/`assigned_by` are `varchar(64)`, not uuid); the live status constraint is the migration chain's, ending at `0029_safety_review_status.sql`. Two files share the number `0011`.
- **Mutation and live-database checks** recorded on 23 September 2026 (commit `9248a98`) — breaking the queue subtraction and querying `Draft` instead of `Submitted` each failed the intended tests, and `list_awaiting_assignment()` reconciled against the live Supabase data read-only — remain valid design evidence for why these cases exist.
