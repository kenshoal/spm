# SCRUM-11 Test Cases: Submit an Event Request

Last reviewed: 21 September 2026

This catalogue traces the live Jira acceptance criteria for SCRUM-11 to
implementation and test evidence. The branch also supports direct submission of
a complete new form, but Jira defines submission of an existing Draft as the
required story path. Coordinator assignment remains owned by SCRUM-14.

## How to run the suites

| Area | Command | Current automated cases |
| --- | --- | ---: |
| Event-request service | `cd backend/eventRequestService && uv run --extra dev --locked pytest` | 44 |
| Frontend components and actions | `cd frontend && npm test` | 24 |
| Frontend browser journeys | `cd frontend && npm run test:e2e` | 4 |

## Acceptance-criterion test matrix

The criterion IDs below follow the acceptance criteria currently recorded in
Jira SCRUM-11, reviewed on 21 September 2026.

| ID | Purpose | Preconditions and input | Action | Expected result and forbidden side effects | Layer and automated evidence | Status / limitation |
| --- | --- | --- | --- | --- | --- | --- |
| AC1 | Prevent unauthorised submission of another organiser's work or a non-Draft request. | Organiser A is authenticated; the target is either A's Draft, organiser B's Draft or already Submitted. | Attempt submission for each target. | Only A's Draft can move to `Submitted`; another owner's request returns `404`, and a non-Draft mutation returns `409` without changing stored data. | API component: `test_other_organiser_cannot_submit_draft`, `test_submitted_request_is_read_only`; repository contract: `test_submit_atomically_scopes_and_changes_status`. | Covered. |
| AC2 | Enforce Jira's nine-field submission minimum while allowing explicit requirement placeholders. | A Draft has event name, purpose, description, at least one aware date/time, positive attendance and all four requirement fields; missing-field variants omit each field. | Attempt submission of the complete and incomplete variants. | The complete request is accepted; every missing field is reported and no incomplete submission reaches persistence. Requirement text may record a real need or `Not required` / `Not known yet`. | API component: `test_direct_submission_requires_every_form_field`, `test_submission_requires_timezone_aware_dates`; frontend action: `requires all submission fields before calling the API`. | Covered for presence and data shape. The UI does not restrict placeholder wording because free-text requirements are valid. |
| AC3 | Keep expected attendance as one event-level value for later venue checks. | A valid request supplies one positive integer attendance value. | Save and submit the request. | `expected_attendance` round-trips as one top-level field and is not duplicated within `venue_requirements`. | Model and API coverage: `test_submit_completed_draft`, `test_rejects_invalid_expected_attendance`; browser submission journey. | Covered by the schema and request model. |
| AC4 | Keep an invalid submission editable and free of downstream side effects. | The organiser owns an incomplete Draft. | Attempt submission. | Submission is refused, all missing items are identified and the request remains an editable `Draft`; no assignment, notification or submission event is created. | API component: `test_incomplete_draft_remains_draft_after_rejected_submission`; frontend actions: `requires all submission fields before calling the API`, `returns an actionable error when submission cannot reach the API`; database verification proves a Draft creates no outbox event. | Covered across validation and persistence boundaries. |
| AC5 | Preserve saved values while moving one Draft to Submitted. | The authenticated organiser owns one complete Draft. | Submit the reopened Draft. | The same request ID and values are preserved, status becomes `Submitted`, and the row count remains one. | API component: `test_submit_completed_draft`; repository contract: `test_submit_atomically_scopes_and_changes_status`; frontend action: `submits a completed existing draft`. | Covered. |
| AC6 | Keep coordinator responsibility separate from submission. | A request is submitted without an assignment operation. | Complete either supported submission path. | The request becomes `Submitted` without creating or implying a Coordinator assignment; responsibility begins only through SCRUM-14. | Submission service and outbox migration modify only the request and submission event; coordinator-assignment tests verify assignment is a separate operation. | Covered; assignment behavior remains owned by SCRUM-14. |
| AC7 | Let the responsible organiser view status while preventing direct edits after submission. | The organiser owns a `Submitted` request. | View it, then attempt update, resubmission and deletion. | Viewing succeeds; all mutations return `409`, original values remain and the UI exposes view controls only. | API component: `test_submitted_request_is_read_only`; component: `renders a submitted request as read-only in the list`; browser submission journey. | Covered. |
| AC8 | Atomically record one durable submission event per successfully submitted request. | A complete Draft or complete new request has a stable request UUID; an incomplete Draft remains unsubmitted. | Submit through either supported path, including a repeated status write. | The request change and one `event_request.submitted` outbox row commit together, keyed by request UUID and event type; failed or repeated attempts add no event. A later notification consumer uses the outbox event UUID for idempotent delivery. | Database triggers and unique constraint in `0008_event_request_submission_outbox.sql`; rollback-only integration verification in `verify_event_request_submission_outbox.sql`. | Covered at the database transaction boundary; external notification delivery remains a separate workflow. |

## Latest verification

Run on 21 September 2026 after applying migrations 0008 and 0009:

- Event-request service after merging current `dev`: 76 passed; two dependency
  deprecation warnings.
- Authentication service after merging current `dev`: 33 passed; one dependency
  deprecation warning.
- Frontend lint: passed.
- Frontend type checking: passed.
- Frontend component and action tests: 24 passed.
- Playwright Chromium journeys and production build: 4 passed.
- Event-request outbox SQL: live rollback-only verification passed for zero
  Draft events, exactly one Draft-submission event, exactly one direct-submission
  event and no duplicate on a repeated status write.
- Outbox security: RLS enabled, no client policies, no `anon` or `authenticated`
  read access, and the private trigger function is not directly executable by
  application roles.
- Docker health check: not rerun in this audit because Docker Desktop was not
  running; the previous branch verification had all four containers healthy.

## Submission tests

### Event-request API

Source: `backend/eventRequestService/tests/test_event_request_controller.py`

| Test | Purpose |
| --- | --- |
| `test_submit_complete_new_event_request_directly` | Proves a complete new form can enter coordination without first creating a visible Draft. |
| `test_direct_submission_requires_every_form_field` | Prevents an incomplete new request from entering the coordination workflow. |
| `test_submit_completed_draft` | Preserves completed form values while moving the same Draft to Submitted. |
| `test_incomplete_draft_remains_draft_after_rejected_submission` | Keeps an incomplete saved request editable when validation fails. |
| `test_submission_requires_timezone_aware_dates` | Prevents a displayed Singapore time from being stored as an ambiguous database timestamp. |
| `test_other_organiser_cannot_submit_draft` | Prevents an organiser from submitting another organiser's work. |
| `test_submitted_request_is_read_only` | Prevents duplicate submission, editing and deletion after hand-off. |
| `test_event_request_operations_require_organiser_role` | Rejects authenticated users with a missing or non-organiser role before event-request data is accessed. |

### Supabase repository contract

Source: `backend/eventRequestService/tests/test_supabase_repository.py`

| Test | Purpose |
| --- | --- |
| `test_submit_atomically_scopes_and_changes_status` | Verifies one PATCH filters by request ID, verified owner and Draft status while writing Submitted. |

### Frontend actions and components

Sources: `frontend/__tests__/event-request-actions.test.ts` and
`frontend/__tests__/page.test.tsx`

| Test | Purpose |
| --- | --- |
| `submits a complete new event request directly` | Sends a completed new form to the authenticated direct-submission endpoint. |
| `submits a completed existing draft` | Targets the current Draft instead of creating a duplicate. |
| `reports that an already submitted request is read-only` | Explains the rejected repeated transition without redirecting away from the form. |
| `returns an actionable error when submission cannot reach the API` | Preserves a recoverable UI state when the event-request service is unavailable. |
| `requires all submission fields before calling the API` | Stops incomplete submission data at the frontend boundary. |
| `confirms submission of a complete request` | Requires explicit acknowledgement that submission makes the request read-only. |
| `renders a submitted request as read-only in the list` | Removes draft mutation controls after submission. |
| `shows all request tracking tabs with counts` | Exposes consistent status navigation and record counts. |
| `allows an authenticated Event Organiser into the event-request workspace` | Confirms the organiser role can access the protected frontend route. |
| `redirects a signed-in user without the organiser role` | Prevents a signed-in user with the wrong role from entering the organiser workspace. |

### Playwright journey

Source: `frontend/e2e/home.spec.ts`

| Test | Purpose |
| --- | --- |
| `organiser can submit a complete new event request` | Verifies login, complete form submission, Submitted visibility and the read-only detail view through the browser. |
| `event-request pages require the Event Organiser role` | Verifies a valid signed-in user with a non-organiser role is redirected to the access explanation page. |

## Explicitly deferred

- `Completed` data depends on an agreed integration with `eventService`.
- Coordinator assignment, review, approval, planning and completion are not
  implemented by this increment.
- Organisers cannot reverse `Submitted` back to `Draft`; a future
  Changes Requested or withdrawal story should define that behavior and its
  audit history.
