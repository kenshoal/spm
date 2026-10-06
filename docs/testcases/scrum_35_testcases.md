# SCRUM-35 — Request Changes After Approval

**Jira:** [SCRUM-35](https://is212g9t4.atlassian.net/browse/SCRUM-35)

**User story:** As an Event Organiser, I want to request structured changes to my approved event, so that the assigned Event Coordinator can review and apply those changes without directly editing the existing plan.

## Approved story contract

The requester approved implementation of this narrowed contract on 4 October 2026 after reviewing the Jira story and its dependencies.

- **AC1:** Given the organiser owns an event in **Approved** or **Planning**, when they submit an explanation and at least one changed date/time, attendance, venue requirement, equipment requirement or registration need, then one pending change request is retained while the event remains unchanged.
- **AC2:** The owning organiser and currently assigned Event Coordinator can view the change request; unrelated users receive no event or change-request information.
- **AC3:** Given the assigned coordinator approves a pending, current change request, then all proposed values are applied atomically and the decision, coordinator and time are retained.
- **AC4:** Given the assigned coordinator rejects a pending change request with a reason, then the rejection is retained and the event remains unchanged.
- **AC5:** A second pending request, repeated decision, disallowed event status, invalid payload or action by a former/unrelated coordinator is refused without side effects.
- **AC6:** If the event changes after the organiser creates the request, approval is refused as stale without partially changing either the event or decision record.

### Scope boundaries

This story covers post-approval amendment requests, relationship-based visibility, coordinator decisions and atomic application. Venue, equipment and registration revalidation/conflict flags remain with their respective booking stories; notification delivery remains with SCRUM-36/SCRUM-37; amendments to **Confirmed** events are excluded until the team defines their cancellation and rebooking consequences.

## Test-case specification

| ID | AC | Scenario and technique | Preconditions | Action and data | Expected result | Forbidden side effects | Layer |
| --- | --- | --- | --- | --- | --- | --- | --- |
| AC1-H1 | AC1 | Happy: owner requests a changed attendance | Approved event owned by organiser-1 | Explain the change; attendance 80 | 201; one Pending request retained | Event stays unchanged | API/DB |
| AC1-P1 | AC1 | Partition: Approved is eligible | Approved event owned by organiser-1 | Change venue requirement | 201 Pending request | No event mutation | API |
| AC1-P2 | AC1 | Partition: Planning is eligible | Planning event owned by organiser-1 | Change venue requirement | 201 Pending request | No event mutation | API |
| AC1-B1 | AC1 | Boundary: one-character explanation | Eligible owned event | Submit explanation length 1 | 201 Pending request | No event mutation | Model/API |
| AC1-B2 | AC1 | Boundary: maximum explanation | Eligible owned event | Submit explanation length 2000 | 201 Pending request | No event mutation | Model/API |
| AC1-B3 | AC1 | Boundary: explanation above maximum | Eligible owned event | Submit explanation length 2001 | 422 | No request row | Model/API |
| AC1-N1 | AC1 | Negative: no changed field | Eligible owned event | Explanation only | 422 | No request or event write | Model/API |
| AC1-N2 | AC1 | Negative: proposed value equals current value | Eligible owned event | Submit current attendance | 409 | No request or event write | DB/API |
| AC1-X1 | AC1 | Cross-cutting: organiser can find the change workflow from the request list | Owned Approved, Planning and Submitted events | Open Change requests on an eligible card | Eligible cards lead to the detail page with a Request a change button; Submitted retains View request | No amendment action offered for Submitted | UI/E2E |
| AC1-X2 | AC1 | Cross-cutting: change entry opens in a dismissible dialog | Eligible owned event without a pending change | Open the dialog, close it, then reopen and submit | Structured form opens above the page; closing returns to the detail view | No change request written when the dialog is closed | E2E |
| AC2-X1 | AC2 | Cross-cutting: related actors can read history | One pending request and current assignment | Owner and assigned coordinator list requests | 200 with same retained request | No hidden fields omitted incorrectly | API/UI |
| AC2-N1 | AC2 | Negative: unrelated users cannot infer existence | Same event | Other organiser/coordinator lists or creates | 404 | No protected data returned or written | API |
| AC3-H1 | AC3 | Happy: assigned coordinator approves | Pending current request | Approve | Proposed values applied; Approved decision retained | No unrelated event fields changed | API/DB/E2E |
| AC4-H1 | AC4 | Happy: assigned coordinator rejects with reason | Pending current request | Reject with reason | Rejected decision retained | Event fields unchanged | API/DB/UI |
| AC4-N1 | AC4 | Negative: blank rejection reason | Pending request | Reject with whitespace | 422 | Pending request and event unchanged | Model/API |
| AC5-N1 | AC5 | Negative: duplicate pending request | Pending request exists | Owner submits another | 409 | Only original pending row remains | DB/API |
| AC5-P1 | AC5 | Partition: Draft is ineligible | Owned Draft | Owner submits valid change | 409 | No change request written | API |
| AC5-P2 | AC5 | Partition: Submitted is ineligible | Owned Submitted event | Owner submits valid change | 409 | No change request written | API |
| AC5-P3 | AC5 | Partition: Under Review is ineligible | Owned event under review | Owner submits valid change | 409 | No change request written | API |
| AC5-P4 | AC5 | Partition: Changes Requested is ineligible | Owned returned event | Owner submits valid change | 409 | No change request written | API |
| AC5-P5 | AC5 | Partition: Confirmed is excluded | Owned Confirmed event | Owner submits valid change | 409 | No change request written | API |
| AC5-P6 | AC5 | Partition: Completed is terminal | Owned Completed event | Owner submits valid change | 409 | No change request written | API |
| AC5-P7 | AC5 | Partition: Cancelled is terminal | Owned Cancelled event | Owner submits valid change | 409 | No change request written | API |
| AC5-P8 | AC5 | Partition: Rejected is terminal | Owned Rejected event | Owner submits valid change | 409 | No change request written | API |
| AC5-N3 | AC5 | Negative: former coordinator acts after reassignment | Request created before reassignment | Former coordinator decides | 403 | Event and request unchanged | API/DB |
| AC5-N4 | AC5 | Negative: repeated decision | Already decided request | Coordinator decides again | 409 | Original decision and event remain | API/DB |
| AC6-N1 | AC6 | Negative: stale plan cannot be overwritten | Event updated after request creation | Coordinator approves | 409 stale conflict | Event and request remain unchanged | DB/API |
| AC3-X1 | AC3, AC6 | Cross-cutting: browser roles cannot bypass server workflow | Migration applied | Inspect grants and call table/RPC as browser role | Access denied | No direct write | DB |

## Implementation evidence

| Acceptance criterion | Evidence |
| --- | --- |
| AC1, AC5 | `EventChangeRequestCreate`, the organiser route and `create_event_change_request` validate ownership, event state, changed values and the single-pending rule before retaining a request. Approved and Planning cards lead to the detail page, where an eligible request opens the form in a dialog. |
| AC2 | The history route checks the owning organiser or latest coordinator assignment before returning `event_change_requests`; the organiser and coordinator detail pages render that history. |
| AC3, AC6 | `decide_event_change_request` locks the event and amendment, rechecks the latest assignment and version, then applies all proposed values and decision metadata in one transaction. Migrations `0020`–`0022` make the event version marker strictly monotonic. |
| AC4 | The decision model requires a rejection reason, and the atomic decision function records the reason without updating the event plan. |
| AC1–AC6 | `verify_event_change_requests.sql` exercises the real Supabase functions, constraints, forbidden side effects and server-only privileges inside a rolled-back transaction. |

## Latest execution record

| ID | Automation status | Actual result | Execution status | Build or commit | Executed by and date | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| AC1-H1, AC1-P1–P2, AC1-B1–B3, AC1-N1–N2, AC2-X1, AC2-N1, AC3-H1, AC4-H1, AC4-N1, AC5-N1, AC5-P1–P8, AC5-N3–N4, AC6-N1 | Green | 25 focused backend cases passed; unchanged values, related visibility and unrelated coordinator disclosure are directly asserted | Pass | `ffe481a` | Codex, 5 Oct 2026 | `uv run pytest tests/test_event_change_request.py -q`; mocked repository. Full event-service regression: 261 passed with two dependency deprecation warnings. Ruff passed. |
| AC1-H1, AC3-H1, AC4-N1 | Green | Component and action coverage passed within the full 187-test frontend suite | Pass | `ffe481a` | Codex, 5 Oct 2026 | `npm test -- --run`; 22 files and 187 tests passed. ESLint and TypeScript passed. `next build --webpack` passed; default Turbopack was blocked by sandbox port permissions. |
| AC1-H1, AC2, AC3 | Green | Organiser-to-coordinator approval journey and all earlier browser workflows passed | Pass | `ffe481a` | Codex, 5 Oct 2026 | `npx playwright test`; 24 Chromium tests passed using local mock services. |
| AC1-H1, AC1-N2, AC3-H1, AC4-H1, AC5-N1, AC5-N3, AC6-N1, AC3-X1 | Green | Real functions, atomic writes, stale/reassignment refusals and grants passed in one rolled-back transaction | Pass | Supabase migrations through `20261005143815` | Codex, 5 Oct 2026 | Ran `database/verify_event_change_requests.sql` against project `rrmvhxrxrrnigjdxcbwt`; no fixture rows retained. The first run exposed the non-advancing timestamp defect; migrations `0020`–`0022` corrected it before this pass. |
| AC1-X1 | Green | List navigation test failed before the link existed, then passed; organiser browser journey now starts from the list | Pass | `fbd4b64`, 6 Oct 2026 | `npm test -- --run __tests__/event-change-request.test.tsx`: 4 passed; full frontend suite: 188 passed; `npm run test:e2e`: 24 passed with local mock services; ESLint, type checking and Webpack build passed. PR #43 CI passed at this commit. |
| AC1-X1, AC1-X2 | Green | The user observed the hash link failing to expose the form; the focused list test then failed before implementation. The dialog opens, closes without a write and reopens for submission | Pass | `92728fd`, 6 Oct 2026 | `npm test -- --run`: 188 passed; `npx playwright test e2e/event-change-request.spec.ts --config playwright.review.config.ts`: 1 passed against running local mock services; ESLint, type checking and Webpack build passed. The temporary reuse-server config was removed after the run. PR CI pending push. |

Human review of these AI-drafted test cases is still required before the story meets the repository Definition of Done.
