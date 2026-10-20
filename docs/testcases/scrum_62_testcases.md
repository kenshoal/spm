# SCRUM-62 — Event Coordinator Lead Oversees Assignments

Source: [Jira SCRUM-62](https://is212g9t4.atlassian.net/browse/SCRUM-62), read 15 October 2026. Branch: `feat/scrum-58-start-planning-button` (shared with SCRUM-58 by the story owner's choice), base `bf4aed5`. Requirement: Week 7 Customer Change #5 (Addition of Event Coordinator Lead Role); discussion #129 (same role, new name).

## Approved contract

As the Event Coordinator Lead, I want to see and manage which coordinator handles each event, so that every event has a suitable coordinator.

The story owner (Tate) reviewed the five Jira ACs and approved the review below on 15 October 2026. Jira wording is kept; the rewording below is recorded here, not written back to Jira.

| Jira AC | Outcome | Approved wording |
| --- | --- | --- |
| The system says "Event Coordinator Lead" wherever it said "Event Operations Manager". | **Keep, clarified** | **AC1:** Given any screen label, message or notice that named the Event Operations Manager, then it says "Event Coordinator Lead". Only wording shown to people changes. The internal role id `event_operations_manager` (migration `0010`, auth service, API checks) is unchanged. |
| New requests wait in a queue for the Lead and are never handed to a coordinator automatically. | **Keep** | **AC2:** Given an organiser submits a Draft, when submission completes, then the request appears in the Lead's awaiting-assignment queue and no coordinator assignment exists for it. Existing behaviour; this story adds the missing test. |
| The Lead can see all assignments and active events, grouped by coordinator. | **Clarify, decided 20 Oct** | **AC3:** Given I am the Lead, when I open Coordinator assignments, then requests awaiting a coordinator are listed first, followed by one group for **every** coordinator in the directory (including those with none), named by email, sorted by name, each showing its number of active events and those events oldest first (by `created_at`), each with its reassign control. A coordinator with no active events shows "No active events". "Active" is what `/assignments` already returns (in-flight statuses). Grouping happens in the frontend; no API change. |
| When an event moves to a different coordinator, both the new and the old coordinator are told. Whether the organiser is told too is for the team to decide. | **Clarify, decided 20 Oct** | **AC4:** Given an event assigned to coordinator A, when the Lead reassigns it to coordinator B, then B is told as today (`coordinator_assigned`) and A receives `coordinator_unassigned` (payload `event_request_id`, `coordinator_id` = A, `assigned_by`), shown in A's inbox without a link because A can no longer open the event. No `coordinator_unassigned` on a first assignment or when the new coordinator is the same person. The organiser is not told (team decision). Delivery is best-effort like the existing notice: a failure is logged and the reassignment stays saved. |
| Coordinators can only manage their own events. | **Keep** | **AC5:** Given an event assigned to coordinator A, when any other coordinator tries to view it or act on it, then they are refused and nothing changes. Existing behaviour (SCRUM-39, SCRUM-58); this story adds one test that covers every coordinator-owned action together. |

## Scope

- **Included (increment 1, 15 Oct 2026):** AC2 and AC5 tests for existing behaviour; AC1 visible-label rename.
- **Included (increment 2, 20 Oct 2026):** AC3 (frontend grouping) and AC4 (old-coordinator notice). Branch `feat/scrum-62-lead-overview`, base `29e535b`.
- **Excluded:** telling the organiser on reassignment (team decision, 20 Oct); registration of coordinators and any change to who may assign (SCRUM-14, Done); email or durable delivery (SCRUM-57, backlog).

## Actors and permissions

- The Event Coordinator Lead is the user with role `event_operations_manager`. Only that role reads the awaiting-assignment queue and assigns or reassigns a coordinator.
- A coordinator may view and act only on events whose **latest** assignment names them.

## Allowed state transitions

None added. Assignment never changes an event's status (existing test `test_assign_coordinator_does_not_change_event_request_status`).

## Persistence and atomicity

No new persistence in this increment.

## Assumptions and open questions

1. ~~AC3: group in the API or the frontend?~~ Frontend (Tate, 20 Oct). Coordinators with no active events are shown (Tate, 20 Oct).
2. ~~AC4: is the organiser told?~~ No, coordinators only (Tate, 20 Oct).
3. The role id stays `event_operations_manager`. Renaming it would need a database migration and an auth-service change and is a separate decision.
4. **How the old coordinator is found (AC4):** `assign_event_request_coordinator` (0014) locks the event row and inserts the new assignment; assignment ids increase and rows are never deleted, so the previous coordinator is the row with the highest id below the new row's id for that event. Read after the insert, this is exact even under concurrent reassignments, and needs no migration.

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
| AC3-H1 | AC3 | The Lead sees each coordinator's active events under that coordinator | Happy | Two coordinators in the directory, three active assignments (two for A, one for B) | Render the grouped list | `coord-a@x`, `coord-b@x` | One group per coordinator with heading "email (count)", each event card under its own coordinator | No event shown under the wrong coordinator | UI (component) |
| AC3-P1 | AC3 | A coordinator with no active events still appears | Partition | Directory has C with no assignments | Render | — | Group for C with count 0 and "No active events" | — | UI (component) |
| AC3-P2 | AC3 | An assignment whose coordinator is missing from the directory is still shown, not dropped | Partition | Directory unavailable or coordinator no longer listed | Group assignments | coordinator id `coord-z` not in directory | A group labelled by the id holding that event | Event not lost | Unit |
| AC3-X1 | AC3 | Order is deterministic: groups by name, events oldest first | Cross-cutting | Coordinators and events supplied out of order | Group assignments | names `b@x`, `a@x`; events created 2nd before 1st | Groups `a@x`, `b@x`; events oldest first | — | Unit |
| AC3-X2 | AC3 | Each event in a group keeps its reassign control, preset to the current coordinator | Cross-cutting | One assignment for A | Render | — | The card has the reassign form with A selected as current | — | UI (component) |
| AC4-H1 | AC4 | Reassigning tells the old coordinator, and still tells the new one | Happy | Request assigned to `coord-1` | Lead reassigns to `coord-2` | — | `coordinator_assigned` to `coord-2`; `coordinator_unassigned` to `coord-1` with `event_request_id`, `coordinator_id`=`coord-1`, `assigned_by` | Nothing sent to the organiser | Service |
| AC4-N1 | AC4 | A first assignment sends no unassigned notice | Negative | Request with no assignment | Lead assigns `coord-1` | — | Only `coordinator_assigned` to `coord-1` | No `coordinator_unassigned` | Service |
| AC4-N2 | AC4 | Reassigning to the same coordinator sends no unassigned notice | Negative | Request assigned to `coord-1` | Lead assigns `coord-1` again | — | No `coordinator_unassigned` | — | Service |
| AC4-B1 | AC4 | With three or more assignments, the notice goes to the immediately previous coordinator, not an older one | Boundary | Assigned to `coord-1`, then `coord-2` | Lead reassigns to `coord-3` | — | `coordinator_unassigned` to `coord-2` only | `coord-1` not told | Service |
| AC4-N3 | AC4 | A failed unassigned notice does not undo the reassignment | Negative | Notification service returns 500 / refuses connection | Call the client | — | No exception; reassignment response unchanged | — | Client |
| AC4-H2 | AC4 | The client posts the agreed event shape | Happy | URL configured | `notify_coordinator_unassigned` | — | POST `event_type` `coordinator_unassigned`, `recipient_id` = old coordinator, agreed payload | — | Client |
| AC4-H3 | AC4 | The old coordinator's inbox explains the change and offers no link | Happy | Notification of type `coordinator_unassigned` | `describeNotification` | — | "An event request you coordinated has been reassigned to another coordinator.", `href` null | No link to a page that would 404 | UI (unit) |

## Latest execution record

| ID | Automation status | Actual result | Execution status | Build or commit | Executed by and date | Remarks and evidence |
| --- | --- | --- | --- | --- | --- | --- |
| AC2-H1, AC2-N1 | Green | Request appears in the Lead's queue; assignment store empty; both coordinators' own queues empty | Pass | branch `feat/scrum-58-start-planning-button` on `bf4aed5`, **local**, pytest 9.1.1, Python 3.12.10, repositories faked | Claude for Tate, 15 Oct 2026 | `backend/eventRequestService/tests/test_coordinator_lead.py`. Existing behaviour, so no Red. Mutation M2 (queue returns `[]`) made AC2-H1 fail. The "no auto-assignment" half has no production code path to mutate, so it is guarded only by `coordinators.rows == []` |
| AC5-N1…N6 | Green | `coord-2` refused with 403 on `review`, `resume-review`, `decision`, `planning`, `cancellation`, `completion`; status unchanged | Pass | as above | Claude for Tate, 15 Oct 2026 | as above. Mutation M3 (`NOT_ASSIGNED_ERRCODE` changed) made all six fail. The ownership rule itself lives in the database function; here the fake repository stands in, so this proves the HTTP mapping, not the SQL |
| AC5-N7, AC5-H1 | Green | `coord-2` gets 404 with no event data; `coord-1` gets 200 | Pass | as above | Claude for Tate, 15 Oct 2026 | as above. Mutation M1 (`if assignment.coordinator_id == caller.id` → `if True`) made AC5-N7 fail |
| AC1-H1…H4 | Green | New wording shown in all four places; old wording absent | Pass | as above, plus Vitest 5.0.0 + jsdom, Node 24.20.0 | Claude for Tate, 15 Oct 2026 | `frontend/__tests__/event-request-status.test.tsx`, `operations-actions.test.ts`, `test-accounts.test.tsx`; `tests/test_coordinator_lead.py`. Red first: 4 failed on the old wording |
| AC4-H1, AC4-N1, AC4-N2, AC4-B1 | Green | Old coordinator gets `coordinator_unassigned` on reassignment, new one still gets `coordinator_assigned`; none on first assignment or same person; only the immediately previous holder is told | Pass | branch `feat/scrum-62-lead-overview` on `29e535b`, **local**, Python 3.12.10, repositories and notification client faked | Claude for Tate, 20 Oct 2026 | `tests/test_coordinator_assignment_service.py`. Red first: H1 and B1 failed on their assertions. N1 and N2 passed before the change (no notice existed), so they were proven by mutation: dropping the same-person guard (N2 fails), oldest instead of latest earlier row (B1 fails), including the new row (H1, B1 fail), inventing a previous holder on a first assignment (N1 fails). Restored and re-run green each time |
| AC4-H2, AC4-N3 | Green | Agreed payload posted to the old coordinator; connection error, 500 and no URL are all swallowed | Pass | as above, `httpx.post` stubbed | Claude for Tate, 20 Oct 2026 | `tests/test_notification_client.py`. Red was the method not existing, which is closer to a compile error than a behavioural Red; noted rather than claimed |
| AC4-H3 | Green | Inbox shows "An event request you coordinated has been reassigned to another coordinator." with no link | Pass | as above, Vitest 5.0.0 + jsdom, Node 24.20.0 | Claude for Tate, 20 Oct 2026 | `frontend/__tests__/notifications.test.tsx`. Red first: generic message |
| AC3-H1, AC3-P1, AC3-X2, AC3-P2, AC3-X1 | Green | One region per coordinator with count, idle coordinators shown with "No active events", unknown coordinator kept under its id, groups by name and events oldest first, reassign control kept | Pass | as above | Claude for Tate, 20 Oct 2026 | `frontend/__tests__/operations.test.tsx`. Red first: 5 failed (no regions; `groupByCoordinator` missing). The 9 existing tests in that file still pass |
| AC3-H2 | Green | In the browser, the event appears in its coordinator's group, then moves to the new coordinator's group on reassignment | Pass | as above, Playwright Chromium against the e2e mock services (real Next.js build, faked APIs) | Claude for Tate, 20 Oct 2026 | `frontend/e2e/assign-coordinator.spec.ts`. Not run Red; the component tests carry the Red evidence. Group headings matched by email with any count, because the mock server's state is shared across specs |

**Local evidence, 15 October 2026**

- Backend baseline before changes: `pytest` in `backend/eventRequestService` 340 passed. After: 352 passed, 0 failed, 0 skipped; `ruff check .` clean. Supabase and the auth service are faked.
- Frontend baseline before SCRUM-62: 314 passed (after the SCRUM-58 button). After: `npm test` 31 files, 316 passed, 0 failed, 0 skipped; `npm run lint`, `npm run typecheck` and `npm run build` clean.
- Red for AC1 (4 tests) seen before the rename; AC2 and AC5 are characterisation tests, proven by the three mutations above, each restored with `git checkout` and re-run green.
- Wording changed: login test-account label, `status-progress.tsx`, `operations/actions.ts`, the API's 403 detail, the e2e mock that mirrors it, one service docstring, and prose in `docs/AUTH_INTEGRATION.md`, `backend/authService/README.md` and `backend/eventRequestService/README.md`. Unchanged on purpose: the role id `event_operations_manager`, the seeded test email, and "Operations Manager" in older tests' comments.


**Local evidence, 20 October 2026 (increment 2)**

- Backend `pytest` in `backend/eventRequestService`: 428 passed, 1 skipped (pre-existing opt-in SCRUM-64 runtime test), 0 failed; `ruff check .` clean. 8 new tests.
- Frontend `npm test`: 38 files, 388 passed, 0 failed; `npm run lint` and `npm run typecheck` clean.
- Playwright, full suite: 43 passed. Its webServer runs `next build`, so the build passes too; the APIs are the e2e mock services, not the real stack.

**Not yet done:** PR CI for increment 2; a check against the real stack (real auth service, Supabase and notificationService) of the grouped page and of the old coordinator's inbox; human review of these test cases (`testing.md` §10). Increment 1's real-stack check of the renamed labels is also still outstanding.

## Human review of the test design (`testing.md` §10)

**Reviewed by Tate Lim (story owner), 20 October 2026: accepted as written.** The test cases were drafted by Claude; Tate reviewed the contract, the expected results and the "Not yet done" list against the agreed requirements.

Points raised in the review and left open:
- AC4-N3 is proven at the notification client only (it swallows connection errors, 500s and a missing URL). No test drives a full reassignment with the notice failing; the expected result's "reassignment response unchanged" rests on the client never raising.
- AC5-N1…N6 cover six coordinator actions. "Send for safety review" (SCRUM-58, `POST /event-requests/{id}/safety-review`) should be added once SCRUM-58's branch is merged.
