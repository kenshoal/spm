# SCRUM-28: Track Event Status

Covers status tracking for organisers and coordinators, coordinator discovery,
and the coordinator transitions SCRUM-28 owns (start review, cancel, complete).
Transitions owned by other stories are listed under remaining coverage.

| Criterion / risk | Purpose (one line) | Setup and action | Expected evidence | Status |
| --- | --- | --- | --- | --- |
| Submitted → Under Review | A verified assigned Coordinator must be able to begin review. | Submit a request, assign a coordinator, authenticate with that coordinator role, then POST `/event-requests/{id}/review`. | 200 and status `Under Review`; assignment alone leaves `Submitted`. | Automated service and role tests pass; included in the 24 Sep live Postman run. |
| Review actor | An Organiser or Operations Manager must not impersonate the assigned Coordinator. | Give the same user ID an assignment but authenticate with either other role; POST review. | 403 and status remains `Submitted`. | Automated tests pass. |
| Review ownership | A different Coordinator must not change a request assigned to someone else. | Authenticate as an unassigned Coordinator; POST review. | 403 and no status change. | Automated service test passes. |
| Assignment visibility | An unrelated Event Organiser or Event Coordinator must not read assignment details by guessing a request ID. | Authenticate with single-role and multi-role identities and GET `/event-requests/{id}/coordinator`. | 404 for unrelated eligible roles; 403 for other roles; owner, Event Operations Manager and current Coordinator get 200. | Automated tests cover the merged multi-role model. |
| Stored status | The database must accept the agreed status set. | Inspect the live `event_requests_status_check`, update one Submitted row to Under Review inside a transaction, then roll back. | All ten statuses are present; the update succeeds; existing rows retain their original status. | Shared Supabase schema query, rollback verification and live transition path passed. |
| Assignment table isolation | Direct browser keys must not bypass the API's role and ownership checks. | Inspect RLS and table grants for `event_coordinator_assignments`. | RLS enabled; `anon` and `authenticated` have no table SELECT; server role retains SELECT/INSERT. | Live grants query passed. |
| Coordinator discovery | A Coordinator must find their assigned requests without knowing the UUID. | GET `/event-requests/assigned-to-me` as the assigned, reassigned-away, unrelated and multi-role coordinator; as Organiser / Ops Manager; with no session; with a repository failure. | Only latest-assigned requests; reassigned-away excluded; empty → 200 `[]`; multi-role accepted; other roles 403; no session 401; failure 502. | Automated controller, service and repository tests pass. |
| Coordinator request detail | Only the owner or assigned Coordinator may open a request. | GET `/event-requests/{id}` across the role/relationship matrix. | Owner 200, other organiser 404; assigned coordinator 200, unrelated coordinator 404; Ops Manager 403; multi-role 200. | Automated tests pass. |
| Cancellation (AC 4) | Only the coordinator in charge may cancel, from any non-terminal status. | POST `/{id}/cancellation` from Submitted, Under Review and Confirmed; as unassigned, reassigned-away, Organiser and Ops Manager; on Draft and terminal statuses. | 200 `Cancelled` for the assigned coordinator; 403 for other actors and Drafts; 409 from Completed/Cancelled/Rejected with no mutation; 401 without a session. | Automated tests pass. |
| Completion (AC 5) | The coordinator marks a confirmed event complete, once. | POST `/{id}/completion` from Confirmed and every other status; repeat; as a non-assigned caller. | 200 `Completed` from Confirmed; 409 elsewhere and on repeat with no mutation; 403 for non-assigned. | Automated tests pass. |
| Stale or repeated review | A double click or stale page must not mutate twice. | POST review twice; POST review after the status moved on. | Second call 409; status unchanged. | Automated tests pass. |
| Atomic transition function | Authorisation and status write must commit together in the database. | Run `database/verify_event_request_status_transitions.sql` after migration `0012`. | Every allowed transition succeeds; `P0002`/`P0003`/`P0004` raised on each failure path; refused calls leave the status unchanged; `EXECUTE` granted to `service_role` only. | Passed on a local Postgres 16 replay of migrations 0007–0012 (23 Sep 2026). **Passed on the shared Supabase project (23 Sep 2026)** after 0012 and 0013 were applied. The first run failed check 13 because Supabase's default privileges gave `anon` a direct `EXECUTE` grant; `0013` closed it. |
| Atomic assignment integration | Assignment and status transitions must not authorize against different assignment snapshots. | Apply `0014`, then run `database/verify_atomic_coordinator_assignment.sql`. | Assignment locks the same request row, rejects Draft/terminal requests and non-coordinator targets, preserves reassignment history and exposes the RPC only to `service_role`. | Repository and HTTP mapping tests pass; rollback rehearsal and deployed verification completed on shared Supabase on 24 Sep 2026. |
| RPC error mapping | The service must map database errcodes, not message text. | Repository tests feed PostgREST 4xx bodies with `P0002`/`P0003`/`P0004`/`P0005` and another error. | Transition errors map to 404 / 403 / 409; assignment errors map to 404 / 409; other errors → 502. | Automated repository and controller tests pass. |
| Login workspace routing | A verified user must land in a workspace allowed by their roles. | Log in as organiser-only, coordinator-only, multi-role and unsupported-role users; simulate a failed role lookup. | Organiser and multi-role users reach `/event-requests`; coordinator-only reaches `/coordination/requests`; unsupported users reach `/unauthorised`; lookup failure creates no cookie. | Automated frontend tests pass (24 Sep 2026). |
| Frontend status model | Every backend status must be representable and appear in exactly one tab. | Vitest over `EVENT_REQUEST_STATUSES` and `groupRequests`. | All ten statuses covered; Completed under Completed; in-progress statuses stay visible after Submitted; Cancelled/Rejected only under All. | Automated (`event-request-status.test.tsx`). |
| Status progress display | Organisers must see the current stage without implying later stages happened. | Render `StatusProgress` for each status. | Correct `aria-current` step; Draft description only; Changes Requested stops at Under Review with a notice; Rejected/Cancelled show a notice and no stepper; Completed is the final reached stage. | Automated (`event-request-status.test.tsx`). |
| Coordinator workspace | Coordinators get status-appropriate actions and actionable failure states. | Vitest over the list, detail actions and server actions. | Empty state; links to detail; actions offered only in their status window; cancel/complete need confirmation; 403, 409, network and expired-session responses mapped to messages or sign-in redirect. | Automated (`coordination.test.tsx`, `coordination-actions.test.ts`). |
| Critical journey (Playwright) | End-to-end handoff from organiser to coordinator and back. | Organiser submits → assignment made **through the mock API** as Ops Manager (no Ops Manager frontend on this branch) → assigned coordinator sees it and starts review → organiser sees Under Review → unrelated coordinator sees an empty queue and not-found on the direct URL. | Each step visible in the browser; assignment alone leaves Submitted. | Passed locally on 24 Sep 2026 (`e2e/track-event-status.spec.ts`). |
| Transition journey (Playwright) | Cancel and complete are reflected in the organiser's tabs. | Coordinator cancels the under-review request; a seeded Confirmed request is marked complete. | Organiser sees Cancelled under All and the completed request under Completed. | Passed locally on 24 Sep 2026. Confirmed is seeded because its owning story is not on this branch. |
| Status-history dependency | Keep historical transition tracking separate from SCRUM-28's current-status scope. | See the acceptance criteria and future test evidence in SCRUM-48. | SCRUM-28 exposes the current status; SCRUM-48 owns immutable transition history and timeline visibility. | Out of scope for SCRUM-28; tracked in [SCRUM-48](https://is212g9t4.atlassian.net/browse/SCRUM-48). |

Remaining coverage owned by other stories: approval and rejection (SCRUM-17),
changes-requested resubmission (SCRUM-35), Planning and Confirmed transitions
(venue/operations stories), and automatic completion of Confirmed requests more
than seven days after their event (SCRUM-40). SCRUM-28 retains the coordinator's
manual Confirmed-to-Completed action. Notifications for these transitions belong
to SCRUM-36/37, while immutable status history belongs to SCRUM-48.

Live API verification on 24 September 2026: the original 39 cases in
`docs/postman/scrum_28.postman_collection.json` passed against the running
authService and eventRequestService on the shared Supabase project, using real
signed-in accounts for each role (`docs/authentication.txt`, "Test accounts").
This covers submission, assignment, coordinator discovery and access, start
review, reassignment, cancellation and completion, including every 401, 403,
404 and 409 path. `Confirmed` was set by SQL for the completion cases, since its
owning story is not implemented.

TC-04A was added after that collection run. Its live API equivalent passed
against the rebuilt service on 24 September 2026: the API returned 409 and a
database query confirmed there were zero assignments to users without the
Event Coordinator role. A complete 40-case Postman rerun remains pending.

Migration `0014` closes the previously documented reassignment/status-transition
race by making both operations lock the same event-request row. Shared-database
verification completed on 24 September 2026.

Local verification on 24 September 2026: eventRequestService passed 148 tests
and Ruff; authService passed 38 tests; the frontend passed 53 unit tests, lint
and TypeScript checking; all seven Playwright tests passed. A production build
completed with Next.js's webpack builder. The default Turbopack build could not
be verified on the reviewing host because its helper process was not permitted
to bind an internal port; CI must run the standard `npm run build` command.
