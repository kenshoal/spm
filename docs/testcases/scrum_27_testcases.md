# SCRUM-27 — Authorise Access by Role

Source: [Jira SCRUM-27](https://is212g9t4.atlassian.net/browse/SCRUM-27). The
story decides what an authenticated user may do: the features available to them
follow from the roles they hold.

Status (1 November 2026): **AI-drafted test design from the approved Jira ACs
(pulled 1 November 2026), teammate review pending (`testing.md` §10); Jira
remains the source of truth.** The labelled-test pass added comments only to
files owned by this sweep; no suite was run in this pass, so every execution
row is **Not executed** (`testing.md` §8).

## Story contract

- AC1: Given an authenticated user, when they use the system, then the features available to them are determined by their role (Event Organiser, Event Coordinator, Event Operations Manager, Venue Staff, Technical Support Staff, Attendee).
- AC2: An Event Operations Manager can assign or reassign Event Coordinators but cannot perform unrelated role-specific actions unless they also hold the corresponding role.
- AC3: Given a person with multiple roles, when authorised functionality is evaluated, then the system recognises all assigned roles.

### Scope

- **Included:** role recognition in authService (`/auth/me` reading
  `app_metadata` and the `staff_roles` table, the full `roles` list), the
  role-assignment endpoint's permission rule (Event Operations Manager may
  assign only `event_coordinator`; Admin any role), the coordinator-assignment
  feature's role gate, the frontend role-driven workspaces
  (`workspaceForRoles`, `workspaceLinks`, per-page role guards), and the
  six-role partition in the browser.
- **Excluded (related stories, named not claimed):** SCRUM-39 (restrict data
  access by relationship — organisation sharing, 404 for unrelated organisers);
  SCRUM-45 (maintain the equipment catalogue) and SCRUM-16 (maintain equipment
  status) own their own role gates on equipment data; SCRUM-19 (the
  Coordinator's right to list Technical Support Staff only); SCRUM-14/SCRUM-62
  own the coordinator-assignment product behaviour and its queue UI;
  SCRUM-60 introduced the Safety Officer role, which sits alongside the six
  roles above; SCRUM-26 owns authentication itself (a valid session).
- **Boundary note:** the six roles are an enumeration, so there is no numeric
  boundary for AC1 — the partition over roles *is* the boundary work. The only
  genuine boundary in this story is the role-count edge of AC3 (zero roles),
  covered by AC3-B1.

### Actors and permissions

| Role (string) | Features the role grants | Explicitly refused |
| --- | --- | --- |
| Event Organiser (`event_organiser`) | `/event-requests` workspace; organiser features on own requests | the assignment workspace; listing staff |
| Event Coordinator (`event_coordinator`) | `/coordination/requests` workspace; coordination features on assigned events; listing Technical Support Staff only (SCRUM-19) | the role-assignment endpoint; other roles' workspaces |
| Event Operations Manager (`event_operations_manager`) | `/operations/assignments` workspace; assigning and reassigning Event Coordinators; listing Event Coordinators | assigning any role other than `event_coordinator`; listing holders of any other role |
| Venue Staff (`venue_staff`) | `/venues`, booking requests, venue blocks, venue search workspaces | staff listing; the assignment workspace |
| Technical Support Staff (`technical_support`) | `/equipment` workspace | staff listing; the assignment workspace |
| Attendee (`attendee`) | the default role when no role is stored; no staff workspace links | every staff workspace (`/unauthorised`) |
| Admin (`admin`) — outside AC1's six | assigning any role; listing holders of any role | — (supporting role for AC2) |

Every request re-reads the roles from the verified token (`roles` tuple built
per request); hidden buttons are not authorisation — each service and page
guard re-checks the role.

### Assumptions and open questions

1. `staff_roles` is the authoritative role store; `app_metadata.roles` is the
   mirror authService writes back after an assignment. When the table is
   reachable it wins; a user with no roles anywhere defaults to `attendee`.
2. Role changes take effect on the next request because roles are re-read per
   request; no test currently proves this freshness (AC3-N1, a gap row below).
3. A caller holding `event_operations_manager` *and* another role keeps the
   manager capability (AC3); AC2's refusals apply to holders who lack the
   relevant role.
4. The Admin role is not one of AC1's six roles; its any-role assignment right
   is recorded under AC2-P1 as the partition context for "who may assign".

## Test case specification

Layers: A = API (authService pytest), API-E = API (eventRequestService pytest),
UI = frontend Vitest, E2E = Playwright.

| ID | AC | Test scenario | Technique | Pre-conditions | Test steps | Test data | Expected result | Forbidden side effects | Layer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AC1-P1 | AC1 | The Event Organiser's workspace is the event-request area | Partition | Verified session holding `event_organiser` | Resolve the role's workspace and load `/event-requests` | Roles `["event_organiser"]`; the multi-role assertion `["event_coordinator", "event_organiser"]` also lands here | `/event-requests` | — | UI + E2E |
| AC1-P2 | AC1 | The Coordinator's workspace is the coordination area | Partition | Verified session holding `event_coordinator` | Log in as a coordinator and observe the landing page | `coordinator@example.com` | `/coordination/requests` with the assigned-requests heading | — | UI + E2E |
| AC1-P3 | AC1 | The Operations Manager's workspace is the assignment area | Partition | Verified session holding `event_operations_manager` | Log in as an operations manager and observe the landing page | `ops@example.com` | `/operations/assignments` | — | UI + E2E |
| AC1-P4 | AC1 | Venue Staff's workspace is the venue area with its three links | Partition | Verified session holding `venue_staff` | Resolve the role's workspace and navigation links | Roles `["venue_staff"]` | `/venues`, plus Booking requests, Venue blocks and Venue search links | No other role's links | UI |
| AC1-P5 | AC1 | Technical Support Staff's workspace is the equipment area | Partition | Verified session holding `technical_support` | Resolve the role's workspace and navigation links | Roles `["technical_support"]` | `/equipment`, plus the arrangement-reviews link | No other role's links | UI |
| AC1-P6 | AC1 | The Attendee has no staff workspace | Partition | Verified session holding only `attendee` | Resolve the role's workspace and navigation links | Roles `["attendee"]` | `/unauthorised`; empty navigation links | No staff link renders | UI |
| AC1-N1 | AC1 | The browser refuses an authenticated user who lacks the page's role | Negative | Valid session whose role is `admin` | Visit `/event-requests` | Session `non-organiser-session` | Redirect to `/unauthorised`; the "Your role can't use this page" heading | No organiser data renders | E2E |
| AC1-N2 | AC1 | The workspace guard redirects a signed-in user without the role | Negative | Valid session; verified roles lack `event_organiser` | Resolve `requireEventOrganiser` | Roles `["admin"]` | Redirect to `/unauthorised` | — | UI |
| AC1-X1 | AC1 | The app shell shows only the workspaces the user's roles grant | Cross-cutting | Verified roles | Render `workspaceLinks(roles)` for each role and for a multi-role user | Each role; `["event_coordinator", "venue_staff"]` | One link per granted workspace; the multi-role user gets the union; attendee gets none | No link to a workspace the roles do not grant | UI |
| AC2-H1 | AC2 | The Operations Manager assigns an Event Coordinator through the role endpoint | Happy | Operations Manager session; target user exists | `PATCH /auth/users/{user_id}/role` with `role=event_coordinator` | Manager caller; target `member@example.com` | 200; response role `event_coordinator`; `staff_roles` upsert carries `assigned_by` = manager id; `app_metadata.roles` refreshed | No other role written | A |
| AC2-H2 | AC2 | The Operations Manager reassigns the Coordinator and the old Coordinator loses the event | Happy | Seeded Submitted request; operations and coordinator sessions | Assign in the browser, verify the coordinator sees it, reassign, verify the old coordinator's queue empties | "Harbour Lights Gala"; `coordinator@example.com` → `reassign.coordinator@example.com` | The card moves to the new coordinator's group; the old coordinator's list no longer shows the event | — | E2E (SCRUM-62's labelled journey; named, not re-labelled) |
| AC2-H3 | AC2 | The Operations Manager lists the Coordinators available for assignment | Happy | Operations Manager session | `GET /auth/users?role=event_coordinator` | — | 200 with the coordinator id/email list, sorted | — | A |
| AC2-P1 | AC2 | Partition over assignable roles: an Admin assigns each staff role | Partition | Admin session | `PATCH /auth/users/{user_id}/role` with `technical_support`, then `event_operations_manager`, then `safety_officer` | The three role values | 200 each; the assigned role is stored and returned | — | A |
| AC2-N1 | AC2 | An Organiser cannot open the Operations Manager's assignment workspace | Negative | Valid Organiser session | Visit `/operations/assignments` | Session `test-session` (`event_organiser`) | Redirect to `/unauthorised` | No assignment queue renders | E2E |
| AC2-N2 | AC2 | The Operations Manager cannot assign any role other than Event Coordinator | Negative | Operations Manager session | `PATCH /auth/users/{user_id}/role` with `role=technical_support` | — | 403 "Insufficient permissions"; no upsert and no metadata update | `staff_roles` and `app_metadata` unchanged | A |
| AC2-N3 | AC2 | The Operations Manager cannot list the holders of other roles | Negative | Operations Manager session | `GET /auth/users?role=venue_staff` | — | 403 | — | A |
| AC2-N4 | AC2 | Roles without assignment duty cannot use the role endpoint at all | Negative | Caller is `technical_support`, or `attendee` with and without stored metadata | `PATCH /auth/users/{user_id}/role` | The three parametrized caller shapes | 403 each; no upsert; no metadata update | Role store unchanged | A |
| AC2-N5 | AC2 | The role endpoint requires a session | Negative | — | `PATCH /auth/users/{user_id}/role` without an Authorization header | — | 401; no write | Role store unchanged | A (see SCRUM-26 AC4-N4) |
| AC2-N6 | AC2 | An unknown role value is rejected by validation | Negative | Admin session | `PATCH /auth/users/{user_id}/role` with `role=superuser` | — | 422; no upsert; no metadata update | Role store unchanged | A |
| AC2-N7 | AC2 | Without the secret key the role feature is unavailable, not half-written | Negative | `SUPABASE_SECRET_KEY` absent | `PATCH /auth/users/{user_id}/role` | — | 503 "Role assignment is not configured" | No role written | A |
| AC2-N8 | AC2 | A role-store outage is reported as a gateway failure and writes nothing | Negative | `staff_roles` upsert raises a Postgrest error | `PATCH /auth/users/{user_id}/role` | — | 502 "Role store unavailable" | No partial write | A |
| AC2-X1 | AC2 | The assignment feature re-checks the Operations Manager role at its own API, behind the UI | Cross-cutting | Callers with and without `event_operations_manager` in their verified roles | Call the coordinator-assignment endpoints as a non-manager, then as a multi-role manager | `roles: ["venue_staff", "event_operations_manager"]` | Non-manager: 403, nothing written; the multi-role manager is allowed because one held role qualifies | No assignment written by a caller lacking the role | API-E |
| AC3-H1 | AC3 | A person holding several roles has all of them recognised | Happy | `staff_roles` holds two rows for the user | `GET /auth/me` with a valid token | `event_operations_manager` + `technical_support` | 200; `roles` lists both; `role` is the first | No role dropped | A |
| AC3-P1 | AC3 | Roles held as a list in the verified identity are returned in full | Partition | `app_metadata.roles` holds a list | `GET /auth/me` | `["event_operations_manager", "technical_support"]` | `roles` returned as the full list, in order | — | A |
| AC3-P2 | AC3 | A multi-role caller keeps each feature they hold | Partition | Caller holds `event_organiser` and `event_coordinator` and is the assigned Coordinator on another organiser's request | `GET /event-requests/{request_id}` | Caller with both roles | 200 — the coordinator access survives the unrelated organisation | — | API-E (SCRUM-39's labelled test; named, not re-labelled) |
| AC3-P3 | AC3 | Workspace resolution honours the whole multi-role list, not just its first entry | Partition | — | `workspaceForRoles(["event_coordinator", "event_organiser"])` | The two roles | `/event-requests` — the organiser workspace, not the first list entry's coordination one | — | UI (same test as AC1-P1…P6) |
| AC3-B1 | AC3 | With zero roles the identity defaults to Attendee | Boundary | Valid token; no role metadata stored (`{}` or absent) | `GET /auth/me` | `app_metadata` `{}` and `None` | 200; `role` and `roles` are `attendee` | No role is invented | A |
| AC3-N1 | AC3 | A role granted or revoked mid-session takes effect on the next request | Negative | An open session whose roles change in the role store between requests | Repeat an authorised request after the change | Role added, then removed | The new feature set applies immediately; a revoked role is refused; no stale role is honoured | — | A |
| AC3-X1 | AC3 | Every consuming service evaluates the whole roles tuple per request | Cross-cutting | authService returns the `roles` list; a protected endpoint in another service | Call protected endpoints as holders of various role sets | e.g. every role other than organiser or coordinator against the event info endpoint | Decisions use every held role: a role held in the tuple grants its feature; absent roles are refused | — | API-E (the per-service refusal suites are those services'; named, not claimed) |

## Latest execution record

This pass (1 November 2026) designed the matrix from the approved ACs and added
label comments only; **no suite was run**, so every row is **Not executed**.
"Automated (label added in this pass)" marks tests labelled on this branch;
"Automated (existing test)" marks tests that exist outside this sweep's file
list (or already carry another story's label), named here so the story owner
can add or find labels; nothing below is pass/fail evidence.

| ID | Automation status | Actual result | Execution status | Build or commit | Executed by and date | Remarks and evidence |
| --- | --- | --- | --- | --- | --- | --- |
| AC1-P1…P6, AC1-N2, AC3-P3 | Automated (label added in this pass) | Not run in this pass | Not executed | docs/testcase-gap-sweep, 1 Nov 2026 | Claude for Yang Xue, 1 Nov 2026 | `frontend/__tests__/auth.test.tsx` — one test resolves all six role workspaces (and the multi-role list), so the range label `AC1-P1…P6, AC3` sits above it; AC1-N2 is the without-the-role redirect test |
| AC1-P2, AC1-N1 | Automated (label added in this pass) | Not run in this pass | Not executed | docs/testcase-gap-sweep, 1 Nov 2026 | Claude for Yang Xue, 1 Nov 2026 | `frontend/e2e/auth.spec.ts` — the coordinator-login journey (AC1-P2) and the admin-session refusal (AC1-N1) |
| AC2-N1 | Automated (label added in this pass) | Not run in this pass | Not executed | docs/testcase-gap-sweep, 1 Nov 2026 | Claude for Yang Xue, 1 Nov 2026 | `frontend/e2e/assign-coordinator.spec.ts`, second test |
| AC1-X1 | Automated (existing test) | Not run in this pass | Not executed | docs/testcase-gap-sweep, 1 Nov 2026 | Claude for Yang Xue, 1 Nov 2026 | `frontend/__tests__/workspace-links.test.ts` — all five tests already carry labels owned by SCRUM-64 (`AC5-X9`), SCRUM-37 (`AC6-X2`) and SCRUM-23 (`AC1-X3`, `AC1-X4`); a second label per test is not allowed, so they are named here, not re-labelled |
| AC1-P3 | Automated (existing test) | Not run in this pass | Not executed | docs/testcase-gap-sweep, 1 Nov 2026 | Claude for Yang Xue, 1 Nov 2026 | Landing-page assertion inside `frontend/e2e/assign-coordinator.spec.ts` first test, already labelled `AC3-H2` for SCRUM-62; named, not re-labelled |
| AC2-H1, AC2-P1, AC2-N2, AC2-N4, AC2-N5, AC2-N6, AC2-N7, AC2-N8, AC3-H1, AC3-P1, AC3-B1 | Automated (label added in this pass) | Not run in this pass | Not executed | docs/testcase-gap-sweep, 1 Nov 2026 | Claude for Yang Xue, 1 Nov 2026 | `backend/authService/tests/test_registration.py` — labels added in the follow-through pass. AC2-H1 is `test_operations_manager_assigns_event_coordinator`; AC2-P1 spans `test_admin_assigns_role` and `test_admin_assigns_event_operations_manager_role` (its third case, SCRUM-60-labelled `test_admin_assigns_safety_officer_role`, is named, not re-labelled); AC2-N2/N4 share the parametrized `test_admin_endpoint_requires_admin_role`; AC2-N5 shares `test_admin_endpoint_requires_authentication` with SCRUM-26 AC4-N4; AC2-N6 `test_admin_endpoint_rejects_invalid_role`; AC2-N7 `test_admin_endpoint_returns_503_without_secret_key`; AC2-N8 `test_admin_endpoint_maps_role_store_failure`; AC3-H1 `test_current_user_reads_roles_from_staff_roles_table`; AC3-P1 `test_current_user_returns_all_roles`; AC3-B1 the parametrized `test_current_user_defaults_role_to_attendee` |
| AC2-H3, AC2-N3 | Automated (existing test) | Not run in this pass | Not executed | docs/testcase-gap-sweep, 1 Nov 2026 | Claude for Yang Xue, 1 Nov 2026 | `backend/authService/tests/test_registration.py` — `test_operations_manager_lists_event_coordinators` and `test_operations_manager_cannot_list_other_roles` already carry SCRUM-14's AC2-H3 and AC2-N11 labels and a test takes one label, so they are named here, not re-labelled |
| AC2-H2, AC2-X1 | Automated (existing test) | Not run in this pass | Not executed | docs/testcase-gap-sweep, 1 Nov 2026 | Claude for Yang Xue, 1 Nov 2026 | SCRUM-14's `backend/eventRequestService/tests/test_coordinator_assignment_controller.py` (`test_assign_coordinator_requires_operations_manager_role`, `test_assign_coordinator_allows_event_operations_manager_role`) and SCRUM-62's labelled e2e journey — named, not claimed |
| AC3-P2 | Automated (existing test) | Not run in this pass | Not executed | docs/testcase-gap-sweep, 1 Nov 2026 | Claude for Yang Xue, 1 Nov 2026 | `backend/eventRequestService/tests/test_organisation_access.py::test_assigned_coordinator_access_survives_unrelated_organisation`, already labelled `AC8-X1` for SCRUM-39; named, not re-labelled |
| AC3-X1 | Automated (existing test) | Not run in this pass | Not executed | docs/testcase-gap-sweep, 1 Nov 2026 | Claude for Yang Xue, 1 Nov 2026 | Per-service role-refusal suites, e.g. `backend/eventRequestService/tests/test_registration_info_api.py` `AC4-P1…P5` partition — those services' stories own the labels |
| AC3-N1 | Planned | — | Not executed | — | — | gap: no automated test yet — story owner to write (role change mid-session recognised on the next request) |
