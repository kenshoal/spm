# SCRUM-35 — Current Increment Test Cases

**Requester-approved execution boundary — 6 October 2026:** Create and view Pending change requests only. Approval and rejection must be unavailable in the UI and API; no event/arrangement changes or change notifications occur. This is a partial delivery of the original story, not a rewrite of Jira's six criteria. SCRUM-35 stays In Progress in Sprint 2.

**New cases designed before implementation:** `AC2-N2` refuses both valid Approved and Rejected decision calls with HTTP 409 and code `CHANGE_DECISIONS_UNAVAILABLE`, without calling the decision primitive or changing stored state; `AC2-X2` shows the proposal and a clear deferred-decision notice without either decision button. The browser creation/view journey must retain Pending after reload and show the original event values.

**Jira:** [SCRUM-35](https://is212g9t4.atlassian.net/browse/SCRUM-35)

**Original Jira user story:** As an Event Organiser, I want to request a change to my event after submission, so that the plan reflects my updated needs.

**Active impediment — IMP-S2-01:** The original criteria include arrangement flags, conflict handling before confirmation and organiser outcome notifications. These remain requirements of SCRUM-35 even though the current increment does not implement them. This document records the partial implementation and its tests; it does not redefine the full story or establish Done.

## Original Jira acceptance criteria — retained

The IDs below refer to the original criteria in their Jira order; the labels are added here for traceability only.

- **Jira AC1:** After submission, the Organiser can raise a change request describing the requested change.
- **Jira AC2:** The Coordinator can review and approve or reject the change request.
- **Jira AC3:** Given an approved change to important information (date, time, expected attendance, venue requirements, equipment requirements), when applied, then the affected venue/equipment/registration arrangements are flagged for review.
- **Jira AC4:** Given an approved change creates a venue or equipment conflict, when applied, then the affected arrangement is flagged and the event cannot be confirmed until resolved.
- **Jira AC5:** Given a change request is rejected, then the event retains its prior arrangements unchanged.
- **Jira AC6:** The Organiser is notified of the outcome of the change request.

## Increment checks — current and deferred, with stable test IDs

The AC numbers in existing test IDs below belong to the earlier branch increment checks, not the original Jira criteria above. They are retained to avoid breaking existing test labels and historical evidence. Each specification row separately maps to the original Jira requirement it supports; security, validation and atomicity also support the project Definition of Done.

The requester approved implementation of this smaller increment on 4 October 2026. That approval does not replace the original Jira story or move its remaining requirements elsewhere.

- **AC1:** Given the organiser owns an event in **Approved** or **Planning**, when they submit an explanation and at least one changed date/time, attendance, venue requirement, equipment requirement or registration need, then one pending change request is retained while the event remains unchanged.
- **AC2:** The owning organiser and currently assigned Event Coordinator can view the change request; unrelated users receive no event or change-request information.
- **Historical AC3 (deferred):** Given the assigned coordinator approves a pending, current change request, then all proposed values are applied atomically and the decision, coordinator and time are retained.
- **Historical AC4 (deferred):** Given the assigned coordinator rejects a pending change request with a reason, then the rejection is retained and the event remains unchanged.
- **AC5:** A second pending request, repeated decision, disallowed event status, invalid payload or action by a former/unrelated coordinator is refused without side effects.
- **Historical AC6 (deferred):** If the event changes after the organiser creates the request, approval is refused as stale without partially changing either the event or decision record.

### Scope boundaries

The **current increment** covers Pending amendment creation in Approved/Planning and relationship-based visibility only. Public approval/rejection is refused and no changes are applied to the active plan; the internal decision primitive is retained for later work. Venue/equipment/registration flags, conflict blocking and organiser notifications remain **unfinished SCRUM-35 requirements** with related dependencies in SCRUM-20/36/37/49; their ownership is not transferred by this document. The branch refuses changes in other event statuses, including Confirmed, which limits coverage of the broad after-submission requirement.

## Test-case specification

### Fixture and execution boundaries

- **Focused API setup:** `eligible_fixture()` in `backend/eventRequestService/tests/test_event_change_request.py` seeds a submitted request, sets Approved (or the parametrized status), assigns `coord-1`, and overrides caller authentication. `organiser-1` is the owner; `organiser-2` and `coord-2` are unrelated. Tokens are fixture identities, not real user accounts.
- **Default input:** `change_payload()` uses explanation `Attendance increased after stakeholder confirmation.` and attendance `80`; each row states overrides. Events and assignments are in-memory fakes recreated per test.
- **API actions:** create with `POST /event-requests/{id}/change-requests`, list with `GET` on that path, and decide with `POST /event-requests/{id}/change-requests/{change_id}/decision`. A positive create is `201` and a list is `200`; valid assigned-coordinator decisions now return `409` with `detail.code = CHANGE_DECISIONS_UNAVAILABLE`. Invalid payloads still fail validation, and unrelated callers retain access refusals.
- **Component setup:** `frontend/__tests__/event-change-request.test.tsx` uses `approvedEvent` and `pending` fixtures and mocked server actions. This checks rendering and action wiring, not database persistence.
- **Browser setup:** `frontend/e2e/event-change-request.spec.ts` seeds an Approved event through its local mock API, switches organiser/coordinator session cookies, submits attendance `80`, checks both decisions are refused and revisits the organiser page with the original attendance and Pending proposal intact. It is not a real authentication/database journey.
- **Database setup:** `database/verify_pending_event_change_requests.sql` requires the relevant migrations and at least one real auth user, creates its fixtures inside a transaction, and rolls them back. The current Pending-only script was executed against the shared project in a rolled-back transaction; the original decision script is historical/deferred and is not the current workflow oracle.

The matrix specifies expected behaviour for the existing increment. Historical runs are recorded separately; unproved side effects remain limitations rather than assumed passes. Ineligible-status cases describe current implementation restrictions, not a decision that Jira AC1 should exclude those states.

| ID | Increment check | Original Jira mapping | One-line purpose | Scenario and technique | Preconditions | Action and data | Expected result | Forbidden side effects | Layer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AC1-H1 | AC1 | Jira AC1 (partial); DoD | Protects the active plan from being overwritten before coordinator review. | Happy: owner requests a changed attendance | Approved event owned by organiser-1 | Explain the change; attendance 80 | 201; one Pending request retained | Event stays unchanged | API/DB |
| AC1-P1 | AC1 | Jira AC1 (partial); DoD | Checks that approval of the event enables the organiser amendment path. | Partition: Approved is eligible | Approved event owned by organiser-1 | Explain the change; attendance 80 | 201 Pending request | No event mutation | API |
| AC1-P2 | AC1 | Jira AC1 (partial); DoD | Checks that entering planning does not remove the organiser amendment path. | Partition: Planning is eligible | Planning event owned by organiser-1 | Explain the change; attendance 80 | 201 Pending request | No event mutation | API |
| AC1-B1 | AC1 | Jira AC1 (partial); DoD | Protects against rejecting a valid explanation at the minimum length. | Boundary: one-character explanation | Eligible owned event | Submit explanation length 1 | 201 Pending request | No event mutation | Model/API |
| AC1-B2 | AC1 | Jira AC1 (partial); DoD | Protects against rejecting a valid explanation at the maximum length. | Boundary: maximum explanation | Eligible owned event | Submit explanation length 2000 | 201 Pending request | No event mutation | Model/API |
| AC1-B3 | AC1 | Jira AC1 (partial); DoD | Prevents oversized explanations from being stored. | Boundary: explanation above maximum | Eligible owned event | Submit explanation length 2001 | 422 | No request row | Model/API |
| AC1-N1 | AC1 | Jira AC1 (partial); DoD | Prevents empty amendment tickets that contain no proposed event change. | Negative: no changed field | Eligible owned event | Explanation only | 422 | No request or event write | Model/API |
| AC1-N2 | AC1 | Jira AC1 (partial); DoD | Prevents unnecessary review work when proposed values equal the active plan. | Negative: proposed value equals current value | Eligible owned event | Submit current attendance | 409 | No request or event write | DB/API |
| AC1-X1 | AC1 | Jira AC1 (partial); DoD | Makes the amendment path discoverable without offering unsupported actions. | Cross-cutting: organiser can find the change workflow from the request list | Owned Approved, Planning and Submitted events | Open Change requests on an eligible card | Eligible cards lead to the detail page with a Request a change button; Submitted retains View request | No amendment action offered for Submitted | UI/E2E |
| AC1-X2 | AC1 | Jira AC1 (partial); DoD | Prevents dismissing a form from accidentally submitting an amendment. | Cross-cutting: change entry opens in a dismissible dialog | Eligible owned event without a pending change | Open the dialog, close it, then reopen and submit | Structured form opens above the page; closing returns to the detail view | No change request written when the dialog is closed | E2E |
| AC1-X3 | AC1 | Jira AC1 (partial); DoD | Keeps the event action and form usable in the reviewed viewport. | Cross-cutting: action and dialog are placed where organisers can use them | Eligible owned event in a 969×930 viewport | Locate the action beside the event title and open the dialog | Action is outside the read-only notice; dialog is centered within 10 pixels on both axes | No event or change request write from opening the dialog | E2E |
| AC2-X1 | AC2 | Jira AC1, AC2; DoD | Keeps the two responsible actors informed through the same retained proposal. | Cross-cutting: related actors can read history | One pending request and current assignment | Owner and assigned coordinator list requests | 200 with same retained request | No event or decision write from viewing history | API/UI |
| AC2-N1 | AC2 | Jira AC1, AC2; DoD | Prevents protected event existence or proposal data leaking to unrelated users. | Negative: unrelated users cannot infer existence | Same event | Other organiser/coordinator lists or creates | 404 | No protected data returned or written | API |
| AC4-N1 | AC4 | Jira AC2, AC5 (event only); DoD | Prevents unexplained rejections and premature decision writes. | Negative: blank rejection reason | Pending request | Reject with whitespace | 422 | Pending request and event unchanged | Model/API |
| AC5-N1 | AC5 | Jira AC1; DoD | Prevents competing Pending proposals from obscuring which plan is under review. | Negative: duplicate pending request | Pending request exists | Owner submits another | 409 | Only original pending row remains | DB/API |
| AC5-P1 | AC5 | Jira AC1 (partial); DoD | Preserves the current increment boundary by refusing amendments in Draft. | Partition: Draft is ineligible | Owned Draft | Owner submits valid change | 409 | No change request written | API |
| AC5-P2 | AC5 | Jira AC1 (partial); DoD | Preserves the current increment boundary by refusing amendments in Submitted. | Partition: Submitted is ineligible | Owned Submitted event | Owner submits valid change | 409 | No change request written | API |
| AC5-P3 | AC5 | Jira AC1 (partial); DoD | Preserves the current increment boundary by refusing amendments in Under Review. | Partition: Under Review is ineligible | Owned event under review | Owner submits valid change | 409 | No change request written | API |
| AC5-P4 | AC5 | Jira AC1 (partial); DoD | Preserves the current increment boundary by refusing amendments in Changes Requested. | Partition: Changes Requested is ineligible | Owned returned event | Owner submits valid change | 409 | No change request written | API |
| AC5-P5 | AC5 | Jira AC1 (partial); DoD | Preserves the current increment boundary by refusing amendments in Confirmed. | Partition: Confirmed is excluded | Owned Confirmed event | Owner submits valid change | 409 | No change request written | API |
| AC5-P6 | AC5 | Jira AC1 (partial); DoD | Preserves the current increment boundary by refusing amendments in Completed. | Partition: Completed is terminal | Owned Completed event | Owner submits valid change | 409 | No change request written | API |
| AC5-P7 | AC5 | Jira AC1 (partial); DoD | Preserves the current increment boundary by refusing amendments in Cancelled. | Partition: Cancelled is terminal | Owned Cancelled event | Owner submits valid change | 409 | No change request written | API |
| AC5-P8 | AC5 | Jira AC1 (partial); DoD | Preserves the current increment boundary by refusing amendments in Rejected. | Partition: Rejected is terminal | Owned Rejected event | Owner submits valid change | 409 | No change request written | API |
| AC5-N3 | AC5 | Jira AC2; DoD | Prevents a former coordinator from deciding after responsibility changes. | Negative: former coordinator acts after reassignment | Request created before reassignment | Former coordinator decides | 403 | Event and request unchanged | API/DB |
| AC3-X1 | AC3, AC6 | Jira AC2; DoD | Prevents browser callers from bypassing server authorization and transaction rules. | Cross-cutting: browser roles cannot bypass server workflow | Migration applied | Inspect grants and call table/RPC as browser role | Access denied | No direct write | DB |
| AC2-N2 | Current create/view boundary | Jira AC2 (deferred); DoD | Prevents API approval from applying an unassessed proposal. | Negative: valid approval is unavailable | Assigned coord-1; one Pending request | POST Approved with reason | 409; detail.code CHANGE_DECISIONS_UNAVAILABLE | Entire event and request unchanged; no decision primitive or notification call | API |
| AC2-N4 | Current create/view boundary | Jira AC2 (deferred); DoD | Prevents API rejection from advancing the deferred decision workflow. | Negative: valid rejection is unavailable | Assigned coord-1; one Pending request | POST Rejected with nonblank reason | 409; detail.code CHANGE_DECISIONS_UNAVAILABLE | Entire event and request unchanged; no decision primitive or notification call | API |
| AC2-X2 | Current create/view boundary | Jira AC2 (view only); DoD | Keeps proposals visible without offering premature decisions. | Cross-cutting: coordinator view is read-only | Pending request with explanation and attendance 80 | Render ChangeRequestPanel | Proposal and availability notice visible; neither decision button exists | No decision action offered | UI/E2E |
| AC2-N3 | Current create/view boundary | Jira AC2 (deferred); DoD | Gives an accurate refusal message to a stale decision form. | Negative: unavailable decision response | Mock API returns 409 with unavailable code | Call retained decision action | Deferred-workflow message returned | No success revalidation | Action unit |
| AC2-N5 | Current create/view boundary | Jira AC1, AC2; DoD | Preserves shared-event viewing without exposing another organiser's amendment controls. | Negative: same-organisation colleague views Approved event | Browser fixture owner playwright-user and colleague-session | Open shared detail | Shared notice and event visible; no Request a change control or misleading history error | No amendment action or protected history disclosed | E2E |

### Retired API cases — retain IDs and historical evidence

These success/stale/repeated decision cases were removed from the active API suite because decisions are now unavailable. Their original expected results below describe the deferred workflow, not current acceptance. The historical execution records remain intact; re-enable or redesign these cases only when that workflow is integrated.

| ID | Increment check | Original Jira mapping | One-line purpose | Scenario and technique | Preconditions | Action and data | Historical expected result | Forbidden side effects | Layer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AC3-H1 | AC3 | Jira AC2; DoD | Prevents approval from retaining a decision without applying its proposed plan. | Happy: assigned coordinator approves | Pending current request | Approve | Proposed values applied; Approved decision retained | No unrelated event fields changed | API/DB/E2E |
| AC4-H1 | AC4 | Jira AC2, AC5 (event only); DoD | Prevents a rejected proposal from altering the active event plan. | Happy: assigned coordinator rejects with reason | Pending current request | Reject with reason | Rejected decision retained | Event fields unchanged | API/DB/UI |
| AC5-N4 | AC5 | Jira AC2; DoD | Prevents a repeated decision from overwriting a retained outcome. | Negative: repeated decision | Already decided request | Coordinator decides again | 409 | Original decision and event remain | API/DB |
| AC6-N1 | AC6 | Jira AC2; DoD | Prevents an older proposal from overwriting a newer event plan. | Negative: stale plan cannot be overwritten | Event updated after request creation | Coordinator approves | 409 stale conflict | Event and request remain unchanged | DB/API |

## Automation inventory for the current increment

Paths are relative to this repository. Every listed case retains its existing ID; no automated tests were changed by this documentation update.

| Existing cases | Actual automated reference | What it can prove / limitation |
| --- | --- | --- |
| AC1-H1 | `backend/eventRequestService/tests/test_event_change_request.py::test_owner_creates_pending_change_without_mutating_event` | Pending response, one row, proposed attendance and unchanged event snapshot using a fake repository. |
| AC1-P1, AC1-P2 | Same file, `test_eligible_event_statuses_accept_change_request` | Parametrized Approved/Planning acceptance; actual payload is attendance 80. |
| AC1-B1–B3 | Same file, `test_change_explanation_boundaries` | 1/2000/2001-character explanation results and request-row counts. |
| AC1-N1 | Same file, `test_change_request_requires_at_least_one_changed_field` | Explanation-only request refused with no amendment row. |
| AC1-N2 | Same file, `test_change_request_rejects_unchanged_value` | Unchanged attendance refused; event value and amendment rows retained. |
| AC1-X1 | `frontend/__tests__/event-change-request.test.tsx`, `links approved and planning events to change requests`; `frontend/e2e/event-change-request.spec.ts` | List navigation is wired for eligible events. |
| AC1-X2, AC1-X3 | `frontend/e2e/event-change-request.spec.ts`, `organiser creates a pending change and coordinator views it without deciding` | Dialog close/reopen, no ticket after close, title action and viewport centering; not full accessibility/mobile coverage. |
| AC2-X1 | Backend file, `test_owner_and_assigned_coordinator_can_view_change_request` | Owner/current coordinator receive the same retained Pending response. |
| AC2-N1 | Backend file, `test_other_organiser_cannot_create_or_view_change_request` | Unrelated callers receive 404 with no proposal writes. |
| AC3-H1 (retired API case) | Historical backend file, `test_assigned_coordinator_approves_and_applies_change`; component `shows proposed values and confirms approval` (retired component case); historical browser journey; original database script | Historical decision evidence only; current browser journey finishes Pending and does not approve. |
| AC4-H1 (retired API case) | Historical backend file, `test_assigned_coordinator_rejects_without_changing_event`; database script | Retained reason/outcome and unchanged event fields; real arrangement preservation remains unverified. |
| AC4-N1 | Backend file, `test_rejection_requires_reason`; historical component `requires a reason when rejecting a change` (retired) | API rejects whitespace without writes; the retired component asserted a required input and is historical, not a current rejected browser journey. |
| AC5-N1 | Backend file, `test_only_one_pending_change_request_is_allowed`; database script | Sequential duplicate refusal; does not itself exercise concurrent callers. |
| AC5-P1–P8 | Backend file, `test_disallowed_event_statuses_refuse_change` | Parametrized status restrictions with unchanged event status/no amendment rows. |
| AC5-N3 | Backend file, `test_former_coordinator_cannot_decide_after_reassignment`; database script | Former coordinator refused; Pending request and event retained. |
| AC5-N4 (retired API case) | Historical backend file, `test_repeated_change_decision_is_refused` | Sequential repeated approval after rejection is refused. |
| AC6-N1 (retired API case) | Historical backend file, `test_stale_change_request_cannot_overwrite_newer_event`; database script | Stale approval refused with event and Pending request retained. |
| AC3-X1 | `database/verify_pending_event_change_requests.sql`, privilege assertions | Current real-database grant checks; browser roles cannot bypass the workflow. |
| AC2-N2, AC2-N4 | Backend file, `test_change_decisions_are_unavailable_without_side_effects` | Both valid decision calls are refused without invoking the decision primitive or notification client. |
| AC2-X2 | Component `shows pending changes without approval or rejection controls`; current Playwright journey | Read-only coordinator proposal and no decision buttons. |
| AC2-N3 | `frontend/__tests__/coordination-actions.test.ts`, `explains when change decisions are unavailable` | Unavailability is not misreported as a stale plan. |
| AC2-N5 | `frontend/e2e/event-change-request.spec.ts`, `a colleague views the event without change controls or a misleading history error` | Additional regression coverage for shared-view integration; it passed before any access change, so no such production change was made. |

## Implementation evidence

| Acceptance criterion | Evidence |
| --- | --- |
| AC1, AC5 | `EventChangeRequestCreate`, the organiser route and `create_event_change_request` validate ownership, event state, changed values and the single-pending rule before retaining a request. Approved and Planning cards lead to the detail page, where an eligible request opens the form in a centered dialog from the event title row. |
| AC2 | The history route checks the owning organiser or latest coordinator assignment before returning `event_change_requests`; the organiser and coordinator detail pages render that history. |
| AC2-N2, AC2-N4 | The public decision endpoint rechecks the assignment and amendment, then returns 409 CHANGE_DECISIONS_UNAVAILABLE before invoking the retained decision primitive. |
| Historical AC3/AC4/AC6 | Internal decision functions and migrations remain retained; their atomic/stale rules do not enable public approval/rejection in this increment. |
| AC1-H1, AC5-N1, AC3-X1 | `verify_pending_event_change_requests.sql` proves durable Pending values, the whole unchanged event, duplicate refusal, no outbox/notification row for the event and browser-role grants in a rolled-back transaction. |

## Historical execution records — not rerun in this documentation update

| ID | Automation status | Actual result | Execution status | Build or commit | Executed by and date | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| AC1-H1, AC1-P1–P2, AC1-B1–B3, AC1-N1–N2, AC2-X1, AC2-N1, AC3-H1, AC4-H1, AC4-N1, AC5-N1, AC5-P1–P8, AC5-N3–N4, AC6-N1 | Green | 25 focused backend cases passed; unchanged values, related visibility and unrelated coordinator disclosure are directly asserted | Pass | `ffe481a` | Codex, 5 Oct 2026 | `uv run pytest tests/test_event_change_request.py -q`; mocked repository. Full event-service regression: 261 passed with two dependency deprecation warnings. Ruff passed. |
| AC1-H1, AC3-H1, AC4-N1 | Green | Component and action coverage passed within the full 187-test frontend suite | Pass | `ffe481a` | Codex, 5 Oct 2026 | `npm test -- --run`; 22 files and 187 tests passed. ESLint and TypeScript passed. `next build --webpack` passed; default Turbopack was blocked by sandbox port permissions. |
| AC1-H1, AC2, AC3 | Green | Organiser-to-coordinator approval journey and all earlier browser workflows passed | Pass | `ffe481a` | Codex, 5 Oct 2026 | `npx playwright test`; 24 Chromium tests passed using local mock services. |
| AC1-H1, AC1-N2, AC3-H1, AC4-H1, AC5-N1, AC5-N3, AC6-N1, AC3-X1 | Green | Real functions, atomic writes, stale/reassignment refusals and grants passed in one rolled-back transaction | Pass | Supabase migrations through `20261005143815` | Codex, 5 Oct 2026 | Ran `database/verify_event_change_requests.sql` against project `rrmvhxrxrrnigjdxcbwt`; no fixture rows retained. The first run exposed the non-advancing timestamp defect; migrations `0020`–`0022` corrected it before this pass. |
| AC1-X1 | Green | List navigation test failed before the link existed, then passed; organiser browser journey now starts from the list | Pass | `fbd4b64`, 6 Oct 2026 | `npm test -- --run __tests__/event-change-request.test.tsx`: 4 passed; full frontend suite: 188 passed; `npm run test:e2e`: 24 passed with local mock services; ESLint, type checking and Webpack build passed. PR #43 CI passed at this commit. |
| AC1-X1, AC1-X2 | Green | The user observed the hash link failing to expose the form; the focused list test then failed before implementation. The dialog opens, closes without a write and reopens for submission | Pass | `92728fd`, 6 Oct 2026 | `npm test -- --run`: 188 passed; `npx playwright test e2e/event-change-request.spec.ts --config playwright.review.config.ts`: 1 passed against running local mock services; ESLint, type checking and Webpack build passed. The temporary reuse-server config was removed after the run. PR CI pending push. |
| AC1-X3 | Green | Browser test first failed because the action was not beside the event title; after moving it, the dialog center was within 10 pixels of the 969×930 viewport center | Pass | `5e94371`, 6 Oct 2026 | Focused Playwright journey: 1 passed against running local mock services; frontend suite: 188 passed; ESLint, type checking and Webpack build passed. Temporary reuse-server config removed; current PR CI pending push. |

Human review of these AI-drafted test cases is still required before the story meets the repository Definition of Done.

## Reconciliation and audit follow-up — 6 October 2026

**Evidence boundary:** old records above remain historical at their listed commits. The requester-approved create/view change was tested after merging current dev; fresh results below distinguish local mocked tests, real database verification and pending PR CI.

### Live Jira versus branch coverage

| Live Jira criterion | Existing branch case coverage | Remaining limitation |
| --- | --- | --- |
| 1 — Request after submission | Branch AC1 / AC5 cases prove Approved/Planning acceptance and refusal of other states. | Earlier post-submission states are not supported; scope decision required. |
| 2 — Coordinator review and decision | Current cases prove related viewing and decision refusal; historical decision evidence is separate. | Approval/rejection are deliberately unavailable; full Jira AC2 is outstanding. |
| 3 — Affected arrangements flagged | No branch case proves a durable venue/equipment/registration flag. | Missing implementation and resource ownership; not passed. |
| 4 — Conflicts block confirmation | No branch case proves resource conflicts prevent confirmation. | Missing integrated revalidation/confirmation gate; not passed. |
| 5 — Rejection preserves arrangements | Historical AC4-H1 asserted the event snapshot; current valid rejection is refused. | Rejection workflow and integrated preservation of existing arrangements remain outstanding. |
| 6 — Organiser notified of outcome | Current history UI/browser journey show a Pending proposal only. | No decision notification is sent; in-page history is not notification-delivery evidence. |

### Documentation direction

Document the existing increment against the original Jira ACs. The earlier proposed replacement ACs and interim AC7 in the sibling `scrum-35-increment-plan.md` are superseded as a scope-change plan; they must not be treated as approved requirements. Any approval safety design remains an unresolved discussion rather than a new acceptance criterion.

Existing case IDs remain stable. The specification records each case's one-line purpose and original Jira mapping, and the automation inventory identifies its actual test function or verification script. Purpose comments explain the defect/risk the case protects against; they are distinct from scenario steps. Preserve historical evidence and require a new dated execution record before claiming a fresh pass.

### Audit priorities, not new approved test specifications

These are findings from existing tests and standards; detailed new cases follow scope approval.

- The focused explanation-boundary test covers 1, 2000 and 2001 characters. Check where zero/blank input is proved before claiming complete minimum-boundary coverage.
- The approval API case is retired. Future decision integration will need independent assertions for all five editable fields and unaffected arrangement records.
- Several negative tests assert HTTP status and state but not the specific response error code required by AGENTS.md. Add those assertions where missing after confirming the error contract.
- The current browser journey verifies Pending persistence, original event values and refusal of both decisions. Historical decision journeys are not current completion evidence.
- Historical AC4-H1 verified the event snapshot, not existing resource rows; original Jira AC5 remains outstanding.
- The shared-database script is needed for real transaction/constraint proof. An ordinary sequential duplicate-request test does not by itself prove simultaneous requests or concurrent decisions; inspect existing verification before choosing a distinct concurrency test.
- Current approval tests do not prove arrangement revalidation or the confirmation guard. Keep Jira AC3/AC4 outstanding; this documentation update introduces no new guard or replacement requirement.

**Completion status against original Jira:** Not done. Existing core evidence remains useful, but the original arrangement/notification requirements, broader lifecycle scope clarification, integrated arrangement-preservation evidence and human/PR review remain outstanding. Fresh partial-increment validation is recorded below. Keep SCRUM-35 In Progress in Sprint 2 until Sprint Review; backlog movement is reserved for the user.


## Fresh Pending-only execution record — 6–7 October 2026

Implementation: `2f9fc24cb2db5c3c766a410fd6b90634af00052e`, following dev reconciliation `1783094`. Executed by Codex locally; requester-approved delivery boundary, with human test-case and PR review still pending. Case IDs use the legacy increment numbering above, not replacement Jira ACs.

| Layer / case IDs | Command or source | Actual result and environment | Status |
| --- | --- | --- | --- |
| Red: AC2-N2 / AC2-N4 | Focused API tests before the deferred-decision response | Both failed because the prior route invoked the decision primitive; a throwing spy exposed the forbidden call. | Expected Red observed |
| Red: AC2-X2 | Coordinator component test before removing controls | Failed because the Pending-only notice was absent and decision controls remained. | Expected Red observed |
| Red: AC2-N3 | Server-action message test before error-code handling | Failed because the new unavailable decision response was described as a stale event plan. | Expected Red observed |
| Focused API: active cases in `test_event_change_request.py` | From `backend/eventRequestService`: `.venv/bin/python -m pytest tests/test_event_change_request.py -q` | 23 passed using authentication overrides and fake repositories; includes both 409 refusals with exact code, whole event/proposal preservation and no decision primitive or notification POST. | Green |
| Event-service regression | `.venv/bin/python -m pytest -q` | 297 passed; two existing dependency deprecation warnings. This count is the whole service suite, not 297 SCRUM-35 cases. | Pass |
| Backend static check | `.venv/bin/ruff check .` | All checks passed. Existing virtual environment used because `uv run` was blocked from its shared cache. | Pass |
| Focused frontend: AC1-X1 / AC1-H1 / AC2-X2 / AC2-N3 plus existing action cases | From `frontend`: `npm test -- --run __tests__/event-change-request.test.tsx __tests__/coordination-actions.test.ts` | 17 passed across two files; action dependencies mocked. | Green |
| Frontend regression | `npm test -- --run` | 188 passed across the frontend suite; this is not a story-only count. | Pass |
| Frontend static checks | `npm run lint`; `npm run typecheck` | Both passed after the final copy update. | Pass |
| Production build and browser regression | `npm run test:e2e` | Webpack production build and all 26 Chromium browser cases passed. Two are SCRUM-35 journeys; remaining cases protect merged dev workflows. Uses local mock APIs and fixture session cookies, not live Supabase Auth. | Pass |
| Added regression: AC2-N5 | Shared-view case in `e2e/event-change-request.spec.ts` | Passed on existing shared-view behaviour before any access change; no production access modification was made for this case. | Pass; no Red claim |
| Real database: AC1-H1 / AC5-N1 / AC3-X1 | `database/verify_pending_event_change_requests.sql` executed via Supabase MCP against `rrmvhxrxrrnigjdxcbwt` | Assertions passed: one durable Pending proposal, exact proposed values, whole event unchanged, duplicate refused, unchanged per-event outbox/notification counts, restricted browser grants. Follow-up confirmed assertions enabled and zero retained verification events. Transaction rolled back; no DDL applied. | Pass |

The internal historical decision verification script is retained for future integration; it was not used to claim an enabled current decision API. No tests here establish resource staff assessments, resource flags, conflict/confirmation blocking, notification delivery, concurrent request races, or the full live-auth application journey. Original Jira AC1 is partial; AC2 lacks decisions; AC3–AC6 remain unfinished.

PR CI is tracked separately on the exact pushed PR head. Passing local checks and shared-database assertions do not substitute for human review, merged integrated verification or full original-story completion.


### Latest dev reconciliation — 7 October 2026

While finalising the PR, dev advanced to `ef4b191` (venue blocking, PR #45). Merge `f0e2789` retains both sets of migration documentation; no production SCRUM-35 conflict remained. Repeated event-service tests: 297 passed and Ruff passed. Newly integrated venue-service tests: 260 passed and Ruff passed, using `../eventRequestService/.venv/bin/python -m pytest -q` / the corresponding Ruff from `backend/venueService` because it has no separate local virtual environment. Frontend regression increased to 244 passed; lint and type checking passed. These counts include teammates' merged work and are not additional SCRUM-35 acceptance coverage.

The post-merge `npm run test:e2e` production build and all 26 browser cases also passed. The server logged one `The destination stream closed early` diagnostic during navigation; no assertion failed. Its underlying navigation/stream cause was not separately investigated. PR CI remains a separate exact-head check.
