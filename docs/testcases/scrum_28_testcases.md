# SCRUM-28: Track Event Status

Covers status tracking for organisers and coordinators, coordinator discovery,
and the coordinator transitions SCRUM-28 owns (start review, cancel, complete).
Transitions owned by other stories are listed under remaining coverage.

| Criterion / risk | Purpose (one line) | Setup and action | Expected evidence | Status |
| --- | --- | --- | --- | --- |
| Submitted → Under Review | A verified assigned Coordinator must be able to begin review. | Submit a request, assign a coordinator, authenticate with that coordinator role, then POST `/event-requests/{id}/review`. | 200 and status `Under Review`; assignment alone leaves `Submitted`. | Automated service and role tests pass; live API unverified. |
| Review actor | An Organiser or Operations Manager must not impersonate the assigned Coordinator. | Give the same user ID an assignment but authenticate with either other role; POST review. | 403 and status remains `Submitted`. | Automated tests pass. |
| Review ownership | A different Coordinator must not change a request assigned to someone else. | Authenticate as an unassigned Coordinator; POST review. | 403 and no status change. | Automated service test passes. |
| Assignment visibility | An unrelated Event Organiser or Event Coordinator must not read assignment details by guessing a request ID. | Authenticate with single-role and multi-role identities and GET `/event-requests/{id}/coordinator`. | 404 for unrelated eligible roles; 403 for other roles; owner, Event Operations Manager and current Coordinator get 200. | Automated tests cover the merged multi-role model. |
| Stored status | The database must accept the agreed status set. | Inspect the live `event_requests_status_check`, update one Submitted row to Under Review inside a transaction, then roll back. | All ten statuses are present; the update succeeds; existing rows retain their original status. | Live schema query and rollback smoke check passed; live API path unverified. |
| Assignment table isolation | Direct browser keys must not bypass the API's role and ownership checks. | Inspect RLS and table grants for `event_coordinator_assignments`. | RLS enabled; `anon` and `authenticated` have no table SELECT; server role retains SELECT/INSERT. | Live grants query passed. |
| Coordinator discovery | A Coordinator must find their assigned requests without knowing the UUID. | GET `/event-requests/assigned-to-me` as the assigned, reassigned-away, unrelated and multi-role coordinator; as Organiser / Ops Manager; with no session; with a repository failure. | Only latest-assigned requests; reassigned-away excluded; empty → 200 `[]`; multi-role accepted; other roles 403; no session 401; failure 502. | Automated controller, service and repository tests pass. |
| Coordinator request detail | Only the owner or assigned Coordinator may open a request. | GET `/event-requests/{id}` across the role/relationship matrix. | Owner 200, other organiser 404; assigned coordinator 200, unrelated coordinator 404; Ops Manager 403; multi-role 200. | Automated tests pass. |
| Cancellation (AC 4) | Only the coordinator in charge may cancel, from any non-terminal status. | POST `/{id}/cancellation` from Submitted, Under Review and Confirmed; as unassigned, reassigned-away, Organiser and Ops Manager; on Draft and terminal statuses. | 200 `Cancelled` for the assigned coordinator; 403 for other actors and Drafts; 409 from Completed/Cancelled/Rejected with no mutation; 401 without a session. | Automated tests pass. |
| Completion (AC 5) | The coordinator marks a confirmed event complete, once. | POST `/{id}/completion` from Confirmed and every other status; repeat; as a non-assigned caller. | 200 `Completed` from Confirmed; 409 elsewhere and on repeat with no mutation; 403 for non-assigned. | Automated tests pass. |
| Stale or repeated review | A double click or stale page must not mutate twice. | POST review twice; POST review after the status moved on. | Second call 409; status unchanged. | Automated tests pass. |
| Atomic transition function | Authorisation and status write must commit together in the database. | Run `database/verify_event_request_status_transitions.sql` after migration `0012`. | Every allowed transition succeeds; `P0002`/`P0003`/`P0004` raised on each failure path; refused calls leave the status unchanged; `EXECUTE` granted to `service_role` only. | Passed on a local Postgres 16 replay of migrations 0007–0012 (23 Sep 2026). **Passed on the shared Supabase project (23 Sep 2026)** after 0012 and 0013 were applied. The first run failed check 13 because Supabase's default privileges gave `anon` a direct `EXECUTE` grant; `0013` closed it. |
| RPC error mapping | The service must map database errcodes, not message text. | Repository test feeds PostgREST 4xx bodies with `P0002`/`P0003`/`P0004` and another error. | 404 / 403 / 409 respectively; other errors → 502. | Automated repository tests pass. |
| Frontend status model | Every backend status must be representable and appear in exactly one tab. | Vitest over `EVENT_REQUEST_STATUSES` and `groupRequests`. | All ten statuses covered; Completed under Completed; in-progress statuses stay visible after Submitted; Cancelled/Rejected only under All. | Automated (`event-request-status.test.tsx`). |
| Status progress display | Organisers must see the current stage without implying later stages happened. | Render `StatusProgress` for each status. | Correct `aria-current` step; Draft description only; Changes Requested stops at Under Review with a notice; Rejected/Cancelled show a notice and no stepper; Completed is the final reached stage. | Automated (`event-request-status.test.tsx`). |
| Coordinator workspace | Coordinators get status-appropriate actions and actionable failure states. | Vitest over the list, detail actions and server actions. | Empty state; links to detail; actions offered only in their status window; cancel/complete need confirmation; 403, 409, network and expired-session responses mapped to messages or sign-in redirect. | Automated (`coordination.test.tsx`, `coordination-actions.test.ts`). |
| Critical journey (Playwright) | End-to-end handoff from organiser to coordinator and back. | Organiser submits → assignment made **through the mock API** as Ops Manager (no Ops Manager frontend on this branch) → assigned coordinator sees it and starts review → organiser sees Under Review → unrelated coordinator sees an empty queue and not-found on the direct URL. | Each step visible in the browser; assignment alone leaves Submitted. | Spec written (`e2e/track-event-status.spec.ts`); **not yet run**. |
| Transition journey (Playwright) | Cancel and complete are reflected in the organiser's tabs. | Coordinator cancels the under-review request; a seeded Confirmed request is marked complete. | Organiser sees Cancelled under All and the completed request under Completed. | Spec written; **not yet run**. Confirmed is seeded because its owning story is not on this branch. |

Remaining coverage owned by other stories: approval and rejection (SCRUM-17),
changes-requested resubmission (SCRUM-35), Planning and Confirmed transitions
(venue/operations stories), and automatic completion (SCRUM-40), which must be
reconciled with the manual completion command above. Notifications for these
transitions belong to SCRUM-36/37.

Still unverified for this story: a live signed-in coordinator performing each transition through
the running API. Known residual risk: a reassignment committed concurrently
with a transition is not blocked by the row lock (documented in `0012`).

Runtime smoke check on 22 September 2026: the standard rebuilt event-request
container and authService were healthy; missing and invalid sessions received
401; the backend's secret-key reads of requests and assignments succeeded.
After correcting the local publishable-key configuration, direct assignment
reads and writes with that key received 401. A successful coordinator review
through the running API still needs a signed-in coordinator account assigned to
a Submitted request; the automated role and assignment checks above cover that
path without a live user session.

Merge verification on 23 September 2026: `dev` PR #25's multi-role auth model
was merged before reapplying this increment. AuthService passed 38 tests,
eventRequestService passed 84 tests, and the frontend passed 24 tests plus
TypeScript checking. Fresh authService and eventRequestService images started
healthy; the event-request container loaded a multi-role caller and an
unauthenticated assignment read returned 401. A real assigned-coordinator
session remains required for the live successful transition check.
