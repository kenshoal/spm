# SCRUM-28: Track Event Status — first integration increment

This increment repairs the SCRUM-14 handoff into status tracking. It does not
claim that every SCRUM-28 status transition or role-specific dashboard exists.

| Criterion / risk | Purpose (one line) | Setup and action | Expected evidence | Status |
| --- | --- | --- | --- | --- |
| Submitted → Under Review | A verified assigned Coordinator must be able to begin review. | Submit a request, assign a coordinator, authenticate with that coordinator role, then POST `/event-requests/{id}/review`. | 200 and status `Under Review`; assignment alone leaves `Submitted`. | Automated service and role tests pass; live API unverified. |
| Review actor | An Organiser or Operations Manager must not impersonate the assigned Coordinator. | Give the same user ID an assignment but authenticate with either other role; POST review. | 403 and status remains `Submitted`. | Automated tests pass. |
| Review ownership | A different Coordinator must not change a request assigned to someone else. | Authenticate as an unassigned Coordinator; POST review. | 403 and no status change. | Automated service test passes. |
| Assignment visibility | An unrelated Event Organiser or Event Coordinator must not read assignment details by guessing a request ID. | Authenticate with single-role and multi-role identities and GET `/event-requests/{id}/coordinator`. | 404 for unrelated eligible roles; 403 for other roles; owner, Event Operations Manager and current Coordinator get 200. | Automated tests cover the merged multi-role model. |
| Stored status | The database must accept the agreed status set. | Inspect the live `event_requests_status_check`, update one Submitted row to Under Review inside a transaction, then roll back. | All ten statuses are present; the update succeeds; existing rows retain their original status. | Live schema query and rollback smoke check passed; live API path unverified. |
| Assignment table isolation | Direct browser keys must not bypass the API's role and ownership checks. | Inspect RLS and table grants for `event_coordinator_assignments`. | RLS enabled; `anon` and `authenticated` have no table SELECT; server role retains SELECT/INSERT. | Live grants query passed. |

Remaining SCRUM-28 coverage: define and test each allowed transition and actor,
rejected and cancelled paths, terminal-state protection, organiser status
visibility after review, role-specific coordination lists and details, and
browser/API integration. No frontend route or workflow test is claimed here.

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
