# SCRUM-28: Track Event Status

This story provides the shared event-request status model, authorised transitions, atomic database updates and frontend status visibility. Business transitions owned by later stories remain outside this story.

## Acceptance-criteria test matrix

| ID | Acceptance criterion | Test purpose | Scenario and action | Expected result | Evidence |
| --- | --- | --- | --- | --- | --- |
| AC1 | Each request has exactly one valid status. | Verifies that stored and displayed statuses use the agreed vocabulary. | Create a request and exercise all supported status values. | The request starts as `Draft`; all ten approved statuses are accepted; unknown values are rejected. | Supabase schema verification and `event-request-status.test.tsx`. |
| AC2 | Only valid status transitions are allowed. | Prevents requests from skipping or reversing workflow stages. | Exercise submission, review, cancellation and completion from valid and invalid starting states. | Valid transitions succeed; invalid transitions return a conflict and do not change the request. | Backend transition tests, SQL verification and Postman cases. |
| AC3 | Status changes are atomic. | Ensures authorisation, status validation and persistence cannot become inconsistent. | Run the status-transition verification script against the deployed database functions. | The request row is locked before validation; failed transitions leave the stored status unchanged; only the server role can execute the RPC. | `verify_event_request_status_transitions.sql` passed on shared Supabase. |
| AC4 | Coordinator assignment and status changes use the same request-row lock. | Prevents a reassignment race from authorising the wrong coordinator. | Assign or reassign a coordinator while attempting a status transition. | Both operations serialize on the same request row; invalid targets are rejected without creating an assignment. | `verify_atomic_coordinator_assignment.sql` and live TC-04A verification passed. |
| AC5 | Role and ownership rules are enforced. | Ensures only authorised users can view or change requests. | Test the owning organiser, assigned coordinator, reassigned coordinator, unrelated coordinator, operations manager and unsupported roles. | Valid users succeed; unauthorised users receive the expected `401`, `403` or `404`; rejected actions do not mutate data. | Backend controller/service tests and live Postman cases. |
| AC6 | Users with access can see the current status. | Ensures the current stage is understandable in the organiser and coordinator workspaces. | Render all statuses, request tabs and the coordinator detail page. | The correct tab, progress stage, available action and assignment message are displayed without implying future stages. | Frontend unit tests and the SCRUM-28 Playwright journey. |
| AC7 | Repeated or stale actions are rejected safely. | Prevents double clicks and stale pages from applying a transition twice. | Repeat review, cancellation or completion, or retry after reassignment or another status change. | The API returns a conflict and the stored status remains unchanged. | Backend tests and Postman negative cases. |

## Supported transitions

SCRUM-28 currently provides these transitions:

| Transition | Authorised actor |
| --- | --- |
| `Draft → Submitted` | Owning Event Organiser |
| `Submitted → Under Review` | Assigned Event Coordinator |
| Any non-terminal status → `Cancelled` | Assigned Event Coordinator |
| `Confirmed → Completed` | Assigned Event Coordinator |

The database stores the complete status vocabulary so later stories can add their own authorised transitions without changing the core status model.

## Out of scope

The following transitions and behaviours belong to other stories:

- Approval and rejection — SCRUM-17
- Changes requested and resubmission — SCRUM-35
- Planning and confirmation — venue and operations stories
- Automatic completion of overdue confirmed events — SCRUM-40
- Immutable status history and timeline display — SCRUM-48
- Notifications — SCRUM-36 and SCRUM-37

Those stories must reuse the SCRUM-28 status model and atomic transition boundary.

## Security and data isolation

- Draft operations are scoped to the authenticated organiser.
- Coordinator details are visible only to the owning organiser, the current coordinator and authorised operations managers.
- The coordinator assignment table is protected from direct browser access.
- Assignment and status-transition RPCs are available only through the server role.
- Reassigned coordinators cannot continue acting on a request.

## Verification evidence

- `eventRequestService`: 157 tests passed and Ruff passed.
- `authService`: 38 tests passed.
- Frontend: 55 unit tests passed.
- Frontend lint passed.
- Frontend TypeScript checking passed.
- Frontend production build passed with Next.js Turbopack.
- Database status-transition verification passed on the shared Supabase project.
- Atomic coordinator-assignment verification passed on the shared Supabase project.
- The complete seven-test Playwright suite passed after the coordinator-assignment
  message fix, including the organiser-to-coordinator status journey.
- PR #29 frontend unit, lint, typecheck, build, end-to-end and conventional-commit
  checks passed after commit `4c1b743`.

## Definition of done

SCRUM-28 is ready to close when:

- The Jira acceptance criteria match this document.
- The latest frontend status-message changes are committed and pushed.
- The pull request includes the updated implementation and tests.
- CI passes the backend, frontend, database-related and Playwright checks.
- The linked stories and their ownership boundaries are recorded in Jira.
- The pull request is reviewed and merged into `dev`.
