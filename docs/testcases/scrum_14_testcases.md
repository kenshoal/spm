# SCRUM-14 Test Cases: Assign an Event Coordinator

Last reviewed: 23 September 2026

This catalogue traces the live Jira acceptance criteria for SCRUM-14 to
implementation and test evidence. Coordinator assignment spans three services'
worth of concerns — who may assign (authService roles), what is assigned
(`event_coordinator_assignments`) and what assignment does to the request's
status (`event_requests`) — so the matrix below names the layer each criterion
is proved at.

SCRUM-11 originally carried an acceptance criterion for exposing unassigned
submissions to the Operations Manager and explicitly handed it to this story
(commit `b00797f`). AC1 below is that criterion.

## How to run the suites

| Area | Command | Current automated cases |
| --- | --- | ---: |
| Event-request service, whole suite | `cd backend/eventRequestService && uv run --extra dev --locked pytest` | 86 |
| — coordinator assignment API | `… pytest tests/test_coordinator_assignment_controller.py` | 16 |
| — coordinator review transition | `… pytest tests/test_event_review_controller.py` | 9 |
| — assignment persistence contract | `… pytest tests/test_coordinator_assignment_repository.py` | 6 |
| — assignment domain rules | `… pytest tests/test_coordinator_assignment_service.py` | 4 |
| — notification hook | `… pytest tests/test_notification_client.py` | 4 |

Forty of the 86 cases belong to this story.

## Acceptance-criterion test matrix

The criterion IDs follow the acceptance criteria recorded in Jira SCRUM-14,
reviewed on 23 September 2026.

| ID | Purpose | Preconditions and input | Action | Expected result and forbidden side effects | Layer and automated evidence | Status / limitation |
| --- | --- | --- | --- | --- | --- | --- |
| AC1 | Let the Operations Manager discover submissions that still need a Coordinator, without a notification per submission. | Two requests are `Submitted`; one already has a Coordinator, one does not. A Draft also exists. | The Operations Manager requests the awaiting-assignment queue. | Only Submitted, unassigned requests are listed, newest first; assigned requests and Drafts are absent; an empty queue is `200 []`, not `404`. Submission itself raises no manager notification. | API component: `test_awaiting_assignment_lists_submitted_requests_without_a_coordinator`, `test_awaiting_assignment_excludes_requests_that_have_a_coordinator`, `test_awaiting_assignment_excludes_drafts`. Domain: `test_awaiting_assignment_skips_the_assignment_lookup_when_nothing_submitted`. Persistence contract: `test_list_by_status_queries_across_organisers`, `test_assigned_event_request_ids_filters_to_the_given_requests`, `test_assigned_event_request_ids_skips_supabase_when_given_no_ids`. Verified against the live database on 23 September 2026. | **API covered; no user interface.** `GET /event-requests/awaiting-assignment` exists and is proved end to end, but no frontend surfaces it — an Operations Manager still has no screen. The no-notification half is satisfied by SCRUM-11's design: submission writes an outbox event, never a manager notification. |
| AC2 | Restrict assignment to the Operations Manager, and only once a request has been submitted. | Requests exist in Draft, Submitted and each terminal status; callers hold organiser, coordinator and operations-manager roles. | Attempt assignment for each combination. | Only an Operations Manager may assign, and only to a non-Draft, non-terminal request; a Draft returns `409`, a terminal status `409`, an unknown request `404`, a wrong role `403` and no session `401`. | API component: `test_assign_coordinator_to_submitted_request`, `test_assign_coordinator_refused_before_submission`, `test_assign_coordinator_refused_once_terminal[Completed\|Cancelled\|Rejected]`, `test_assign_coordinator_to_missing_request`, `test_assign_coordinator_requires_operations_manager_role`, `test_assign_coordinator_allows_event_operations_manager_role`, `test_requires_bearer_session`. | Covered, including the multi-role case where operations manager is one of several roles. |
| AC3 | Record the responsible Coordinator without advancing the request's status. | An Operations Manager assigns a Coordinator to a `Submitted` request. | Make the assignment, then read both the request and its coordinator. | The assigned Coordinator is retrievable and the request's status is still `Submitted`; assignment writes only to `event_coordinator_assignments`. | API component: `test_assign_coordinator_does_not_change_event_request_status`, `test_reassignment_preserves_history_and_get_returns_latest`; a request with no assignment returns `404`, distinct from a missing request: `test_get_coordinator_when_none_assigned`. | Covered. Status and assignment live in separate tables and separate services, so the separation is structural rather than merely tested. |
| AC4 | Move the request to `Under Review` only when the assigned Coordinator starts review, never on assignment alone. | A `Submitted` request is assigned to Coordinator A; callers include Coordinator A, a different coordinator and an unassigned caller. | Assign, then attempt to start review as each caller. | Assignment alone leaves the status `Submitted` and never reaches `Planning`; only Coordinator A can start review, moving `Submitted` → `Under Review`; another coordinator or an unassigned request returns `403`, a repeat `409`. | API component: `test_assigned_coordinator_can_start_review`, `test_assignment_alone_does_not_start_review`, `test_start_review_refused_for_non_assigned_caller`, `test_start_review_refused_when_unassigned`, `test_start_review_refused_once_already_under_review`, `test_start_review_refused_before_submission`, `test_start_review_requires_event_coordinator_role`, `test_start_review_requires_bearer_session`, `test_start_review_for_missing_request`. | Covered, and the live `event_requests` status CHECK constraint was confirmed on 23 September 2026 to accept all ten `EventRequestStatus` values, so the write succeeds in the deployed database. See the schema note below — `migrations/0007` does not reflect this. |
| AC5 | Notify the assigned Coordinator as a side effect that cannot fail the assignment. | A notification endpoint is configured, unreachable, or not configured at all. | Assign a Coordinator under each condition. | A configured endpoint receives one `coordinator_assigned` message naming the Coordinator, the request and the assigning manager; an unreachable or failing endpoint is logged and swallowed; an unconfigured one is a silent no-op. Assignment succeeds in every case. | Domain: `test_assign_notifies_the_assigned_coordinator`, `test_assign_succeeds_without_a_notification_client_configured`. Hook contract: `test_posts_expected_payload_when_configured`, `test_noop_when_unconfigured`, `test_connection_failure_is_swallowed`, `test_error_response_is_swallowed`. | **Integration point, not a delivered notification.** No Notification System exists in this increment, so nothing is actually delivered to a Coordinator. The criterion is met only in the sense that the outbound contract is defined and proved; end-to-end delivery depends on a future notification story. |
| AC6 | Allow reassignment to a different Coordinator while preserving who was responsible when. | A request is assigned to Coordinator A, then reassigned to Coordinator B. | Reassign, then read the current Coordinator and the queue. | The current Coordinator is B, A's row survives as history, and the request does not reappear in the awaiting-assignment queue. | API component: `test_reassignment_preserves_history_and_get_returns_latest`; domain: `test_reassigned_request_stays_out_of_the_awaiting_queue`; persistence contract: `test_latest_orders_by_id_descending`, `test_latest_returns_none_when_never_assigned`. | Covered. "Current" is the highest `id`, not the latest `assigned_at`, because server-clock resolution cannot reliably order two assignments made in quick succession. **Discovery gap:** the queue lists only unassigned requests, so a manager wanting to reassign an already-assigned request must already know its id. |

## Latest verification

Run on 23 September 2026, against commit `9248a98` on
`feat/awaiting-assignment-queue`:

| Check | Command | Result |
| --- | --- | --- |
| Lint (as CI runs it) | `ruff check .` | All checks passed |
| Event-request suite | `pytest` | 86 passed |

Two further checks were run because a faked database is this suite's central
blind spot:

- **Mutation check.** Three AC1 tests passed the moment they were written, which
  proves nothing on its own. Breaking the implementation two ways — dropping the
  assigned-request subtraction, and querying `Draft` instead of `Submitted` —
  confirmed the intended test failed in each case.
- **Live read-only verification.** The real repositories and service were run
  against the deployed Supabase project. `list_awaiting_assignment()` returned
  both of the live `Submitted` requests, and the count reconciled against a
  separate query of Submitted requests minus assigned ones. No writes were made.

## Schema notes

Two pieces of live schema are not reproducible from `database/migrations/`.
Both were created directly in the Supabase dashboard.

- `event_coordinator_assignments` had no migration at all. It is now captured in
  `migrations/0011_event_coordinator_assignments.sql` as a reference snapshot
  reconciled against live on 23 September 2026. Note `coordinator_id` and
  `assigned_by` are `varchar(64)`, not `uuid`.
- `migrations/0007_event_requests.sql` declares
  `CHECK (status IN ('Draft', 'Submitted'))`, but the live constraint accepts all
  ten `EventRequestStatus` values. **A fresh environment built from
  `migrations/` alone would reject `Under Review` and break AC4.** No migration
  reconciles this yet; per `database/README.md` the fix belongs in a new file,
  not an edit to `0007`.

## Explicitly deferred

- **No Operations Manager user interface.** AC1 is satisfied at the API only.
  The frontend has no coordinator-assignment screen of any kind, so no component
  or Playwright coverage exists for this story.
- **No notification is delivered.** AC5's hook has no consumer until a
  Notification System story lands.
- **No reassignment discovery.** AC6 works, but nothing lists already-assigned
  requests for a manager looking to reassign one.
- **Statuses beyond `Under Review`** — `Changes Requested`, `Approved`,
  `Planning`, `Confirmed`, `Completed` — are accepted by the database and
  present in `EventRequestStatus`, but no transition into them is implemented.
  `EventReviewService` deliberately implements one transition rather than a
  general state machine; the rest is backlog C-2.
