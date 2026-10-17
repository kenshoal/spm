# SCRUM-62 — Event Coordinator Lead Oversees Assignments

Source: [Jira SCRUM-62](https://is212g9t4.atlassian.net/browse/SCRUM-62), read 15 October 2026. Branch: `feat/scrum-58-start-planning-button` (shared with SCRUM-58 by the story owner's choice), base `bf4aed5`. Requirement: Week 7 Customer Change #5 (Addition of Event Coordinator Lead Role); discussion #129 (same role, new name).

## Approved contract

As the Event Coordinator Lead, I want to see and manage which coordinator handles each event, so that every event has a suitable coordinator.

The story owner (Tate) reviewed the five Jira ACs and approved the review below on 15 October 2026. Jira wording is kept; the rewording below is recorded here, not written back to Jira.

| Jira AC | Outcome | Approved wording |
| --- | --- | --- |
| The system says "Event Coordinator Lead" wherever it said "Event Operations Manager". | **Keep, clarified** | **AC1:** Given any screen label, message or notice that named the Event Operations Manager, then it says "Event Coordinator Lead". Only wording shown to people changes. The internal role id `event_operations_manager` (migration `0010`, auth service, API checks) is unchanged. |
| New requests wait in a queue for the Lead and are never handed to a coordinator automatically. | **Keep** | **AC2:** Given an organiser submits a Draft, when submission completes, then the request appears in the Lead's awaiting-assignment queue and no coordinator assignment exists for it. Existing behaviour; this story adds the missing test. |
| The Lead can see all assignments and active events, grouped by coordinator. | **Clarify, open** | **AC3:** `/assignments` returns a flat list today. Grouping by coordinator is new. **Open decision:** group in the API or in the frontend. Not built in this increment. |
| When an event moves to a different coordinator, both the new and the old coordinator are told. Whether the organiser is told too is for the team to decide. | **Clarify, open** | **AC4:** the new coordinator is already notified (`notify_coordinator_assigned`); the old one is not. **Open decision:** whether the organiser is also told. Not built in this increment. |
| Coordinators can only manage their own events. | **Keep** | **AC5:** Given an event assigned to coordinator A, when any other coordinator tries to view it or act on it, then they are refused and nothing changes. Existing behaviour (SCRUM-39, SCRUM-58); this story adds one test that covers every coordinator-owned action together. |

## Scope

- **Included (increment 1, 15 Oct 2026):** AC2 and AC5 tests for existing behaviour; AC1 visible-label rename.
- **Excluded for now:** AC3 and AC4, until the two open decisions above are made. Registration of coordinators and any change to who may assign (SCRUM-14, Done).

## Actors and permissions

- The Event Coordinator Lead is the user with role `event_operations_manager`. Only that role reads the awaiting-assignment queue and assigns or reassigns a coordinator.
- A coordinator may view and act only on events whose **latest** assignment names them.

## Allowed state transitions

None added. Assignment never changes an event's status (existing test `test_assign_coordinator_does_not_change_event_request_status`).

## Persistence and atomicity

No new persistence in this increment.

## Assumptions and open questions

1. AC3: group in the API or the frontend?
2. AC4: is the organiser told when their event moves to a different coordinator?
3. The role id stays `event_operations_manager`. Renaming it would need a database migration and an auth-service change and is a separate decision.

## Test case specification

| ID | AC | Test scenario | Technique | Pre-conditions | Test steps | Test data | Expected result | Forbidden side effects | Layer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AC1-H1 | AC1 | A submitted request that is waiting says it waits for the Event Coordinator Lead | Happy | `StatusProgress` rendered for Submitted, no coordinator assigned | Render the component | status `Submitted`, `coordinatorAssigned=false` | Text "waiting for an Event Coordinator Lead" is shown; "Operations Manager" is not | — | UI (component) |
| AC1-H2 | AC1 | A refused assignment names the Event Coordinator Lead | Happy | `fetch` stubbed to 403 | Call `assignCoordinator` | request `request-1`, coordinator `coord-1` | Message "Only an Event Coordinator Lead can assign coordinators." | No page revalidated | Action |
| AC1-H3 | AC1 | The Lead's test-account label uses the new name; its seeded email, which holds the internal role id, is unchanged | Happy | `NODE_ENV=development` | Render `TestAccounts` | — | "Event Coordinator Lead" shown; "Event Operations Manager" absent; `event_operations_manager@example.com` still listed | — | UI (component) |
| AC1-H4 | AC1 | The API's 403 for a caller who is not the Lead names the Event Coordinator Lead | Happy | Auth service stubbed to return role `event_coordinator` | `GET /event-requests/awaiting-assignment` | token `valid-token` | 403; detail "Only an Event Coordinator Lead can assign a Coordinator" | — | API |
| AC2-H1 | AC2 | A submitted request waits in the Lead's queue and is not assigned to anyone | Happy | Organiser's Draft with all fields complete; empty assignment store | Organiser submits the Draft; the Lead reads `GET /event-requests/awaiting-assignment` | `complete_payload()` | Submit returns 200, status `Submitted`; the queue contains the request; the assignment store has no row for it | No assignment row | API |
| AC2-N1 | AC2 | No coordinator's own queue contains a request just submitted | Negative | As AC2-H1; coordinators `coord-1` and `coord-2` | Each coordinator reads `GET /event-requests/assigned-to-me` | — | Both lists are empty | No assignment row | API |
| AC5-N1…N6 | AC5 | A coordinator who is not assigned is refused on every coordinator-owned action, even when the action would be valid for the assigned coordinator | Negative | Request assigned to `coord-1`, in the status each action needs (Submitted, Changes Requested, Under Review, Approved, Planning, Confirmed) | `coord-2` POSTs `review`, `resume-review`, `decision`, `planning`, `cancellation`, `completion` | `coord-2` | 403 each | Status unchanged | API |
| AC5-N7 | AC5 | A non-assigned coordinator cannot see the event | Negative | Request assigned to `coord-1` | `coord-2` GETs `/event-requests/{id}` | — | 404, body does not reveal the event | — | API |
| AC5-H1 | AC5 | The assigned coordinator is not locked out by the test above (guards against a test that passes only because everything is refused) | Happy | As AC5-N1…N7 | `coord-1` GETs `/event-requests/{id}` | — | 200, same id | — | API |

## Latest execution record

| ID | Automation status | Actual result | Execution status | Build or commit | Executed by and date | Remarks and evidence |
| --- | --- | --- | --- | --- | --- | --- |
| AC2-H1, AC2-N1 | Green | Request appears in the Lead's queue; assignment store empty; both coordinators' own queues empty | Pass | branch `feat/scrum-58-start-planning-button` on `bf4aed5`, **local**, pytest 9.1.1, Python 3.12.10, repositories faked | Claude for Tate, 15 Oct 2026 | `backend/eventRequestService/tests/test_coordinator_lead.py`. Existing behaviour, so no Red. Mutation M2 (queue returns `[]`) made AC2-H1 fail. The "no auto-assignment" half has no production code path to mutate, so it is guarded only by `coordinators.rows == []` |
| AC5-N1…N6 | Green | `coord-2` refused with 403 on `review`, `resume-review`, `decision`, `planning`, `cancellation`, `completion`; status unchanged | Pass | as above | Claude for Tate, 15 Oct 2026 | as above. Mutation M3 (`NOT_ASSIGNED_ERRCODE` changed) made all six fail. The ownership rule itself lives in the database function; here the fake repository stands in, so this proves the HTTP mapping, not the SQL |
| AC5-N7, AC5-H1 | Green | `coord-2` gets 404 with no event data; `coord-1` gets 200 | Pass | as above | Claude for Tate, 15 Oct 2026 | as above. Mutation M1 (`if assignment.coordinator_id == caller.id` → `if True`) made AC5-N7 fail |
| AC1-H1…H4 | Green | New wording shown in all four places; old wording absent | Pass | as above, plus Vitest 5.0.0 + jsdom, Node 24.20.0 | Claude for Tate, 15 Oct 2026 | `frontend/__tests__/event-request-status.test.tsx`, `operations-actions.test.ts`, `test-accounts.test.tsx`; `tests/test_coordinator_lead.py`. Red first: 4 failed on the old wording |

**Local evidence, 15 October 2026**

- Backend baseline before changes: `pytest` in `backend/eventRequestService` 340 passed. After: 352 passed, 0 failed, 0 skipped; `ruff check .` clean. Supabase and the auth service are faked.
- Frontend baseline before SCRUM-62: 314 passed (after the SCRUM-58 button). After: `npm test` 31 files, 316 passed, 0 failed, 0 skipped; `npm run lint`, `npm run typecheck` and `npm run build` clean.
- Red for AC1 (4 tests) seen before the rename; AC2 and AC5 are characterisation tests, proven by the three mutations above, each restored with `git checkout` and re-run green.
- Wording changed: login test-account label, `status-progress.tsx`, `operations/actions.ts`, the API's 403 detail, the e2e mock that mirrors it, one service docstring, and prose in `docs/AUTH_INTEGRATION.md`, `backend/authService/README.md` and `backend/eventRequestService/README.md`. Unchanged on purpose: the role id `event_operations_manager`, the seeded test email, and "Operations Manager" in older tests' comments.

**Not yet done:** AC3 and AC4 (open decisions above); a browser or real-API check of the renamed labels; PR CI; human review of these test cases (`testing.md` §10).
