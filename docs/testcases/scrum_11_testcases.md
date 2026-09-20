# SCRUM-11 Test Cases: Submit an Event Request

Last reviewed: 20 September 2026

This catalogue traces the submission increment from its acceptance behavior to
automated evidence. It covers direct submission of a new form and submission of
an existing Draft. Coordinator assignment and later operational transitions
remain outside SCRUM-11.

## How to run the suites

| Area | Command | Current automated cases |
| --- | --- | ---: |
| Event-request service | `cd backend/eventRequestService && .venv/bin/pytest` | 44 |
| Frontend components and actions | `cd frontend && npm test` | 24 |
| Frontend browser journeys | `cd frontend && npm run test:e2e` | 4 |

## Acceptance-criterion coverage

These local criterion IDs reflect the agreed submission scope and should be
reconciled with the final Jira wording before SCRUM-11 is closed.

| ID | Acceptance criterion | Automated evidence | Status and limitation |
| --- | --- | --- | --- |
| AC1 | An authenticated organiser can submit a complete new form directly. | `test_submit_complete_new_event_request_directly`; `submits a complete new event request directly`; Playwright submission journey | Covered. |
| AC2 | An authenticated organiser can submit their completed saved Draft without creating a duplicate. | `test_submit_completed_draft`; `submits a completed existing draft` | Covered. |
| AC3 | Submission requires all nine event-request fields, including explicit requirement text where a category does not apply. | `test_direct_submission_requires_every_form_field`; `test_incomplete_draft_remains_draft_after_rejected_submission`; `requires all submission fields before calling the API` | Covered. |
| AC4 | Submission changes the persisted state from `Draft` to `Submitted` in one owner-scoped update. | `test_submit_completed_draft`; `test_submit_atomically_scopes_and_changes_status` | Covered at service and Supabase contract layers. |
| AC5 | A different organiser cannot submit the owner's Draft. | `test_other_organiser_cannot_submit_draft` | Covered. |
| AC6 | A submitted request cannot be resubmitted, edited or deleted. | `test_submitted_request_is_read_only`; `renders a submitted request as read-only in the list`; Playwright submission journey | Covered. |
| AC7 | Organisers can see request counts and filter All, Draft, Submitted and Completed. | `shows all request tracking tabs with counts`; Playwright submission journey verifies Submitted | Completed remains empty until the downstream event service exposes completion state. |
| AC8 | Failed or invalid submission does not move a saved Draft into coordination. | `test_incomplete_draft_remains_draft_after_rejected_submission`; `requires all submission fields before calling the API`; `returns an actionable error when submission cannot reach the API` | Validation and frontend network failure are covered. A live Supabase outage is not exercised by the browser suite. |
| AC9 | Only a user assigned the Event Organiser role can access event-request operations. | `test_event_request_operations_require_organiser_role`; `allows an authenticated Event Organiser into the event-request workspace`; `redirects a signed-in user without the organiser role`; Playwright role-gate journey | Covered at the backend API and frontend route boundaries. The trusted role is read from Supabase `app_metadata`, not user-editable metadata. |

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
