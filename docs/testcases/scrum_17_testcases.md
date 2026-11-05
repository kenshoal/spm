# SCRUM-17 — Review and Decide on an Event Request

Source: [Jira SCRUM-17](https://is212g9t4.atlassian.net/browse/SCRUM-17). User story: as an Event Coordinator, I want to review a submitted request and approve it, reject it, or ask for clarification, so that planning only proceeds on sufficiently clear requests.

Status (converted 1 Nov 2026): **AI-drafted conversion of the September catalogue to the `testing.md` matrix format; teammate review pending (`testing.md` §10).** The AC wording below is the approved wording recorded by the 30 September review (kept from the converted catalogue); **Jira remains the source of truth.** Labels in the test files read `SCRUM-17 AC<n>-<L><k>` (story-prefixed, following the `SCRUM-38 AC4-X1` precedent) because the shared files also carry SCRUM-8/11/14/28/39/60 labels. Nothing was executed in this pass: the matrix and the labels were added; every execution row below is `Not executed`. The 30 September evidence recorded by the previous revision is preserved as provenance for that commit, not re-claimed here (`testing.md` §8).

## Story contract

### Acceptance criteria

- **AC1:** The assigned Event Coordinator can view the complete submitted event request.
- **AC2:** While a request is under review, the assigned Event Coordinator can approve it, request clarification, or reject it.
- **AC3:** Each outcome and its reason are retained; clarification and rejection require a reason.
- **AC4:** The owning organiser can view and answer a clarification without editing submitted fields, after which the assigned coordinator can continue review.

The 30 September AC review outcomes (all Keep; AC4 Clarified — a clarification response supplements the request, it does not amend canonical event fields) carry over unchanged; the user approved continuing SCRUM-17 with the clarification-only scope on 30 September 2026.

### Scope

| | Behaviour | Owner |
| --- | --- | --- |
| Included | Read-only review visibility of every submitted field (AC1) | SCRUM-17 |
| Included | The three coordinator outcomes from `Under Review` and their refusals (AC2) | SCRUM-17 |
| Included | Retention of each outcome and reason; required reasons; decision-history access (AC3) | SCRUM-17 |
| Included | The clarification loop: respond without editing, then resume (AC4) | SCRUM-17 |
| Excluded | Notification delivery to the organiser or coordinator | SCRUM-36 |
| Excluded | Post-approval organiser change requests (SCRUM-17 retains the state and content those stories consume) | SCRUM-35 |
| Excluded | Relationship-based read access beyond this story's owner/assignee rules (the unrelated-organiser and unassigned-coordinator 404/403 partition in `test_event_request_controller.py` carries SCRUM-39's `AC5-H1`/`AC5-N1` labels — named, not claimed) | SCRUM-39 |
| Excluded | Complete status-transition history listing | SCRUM-48 |
| Excluded | The progress tracker's per-status rendering (the `event-request-status.test.tsx` status tests carry SCRUM-28's `AC6-*`/`AC1-P1` labels and SCRUM-60's `AC6-P2` — named, not claimed) | SCRUM-28 / SCRUM-60 |
| Excluded | Authentication gates themselves (the no-session 401 rows here prove state safety for this story's endpoints; the generic auth contract is SCRUM-26's) | SCRUM-26 |

### Actors and permissions

- **Event Coordinator (currently assigned):** the only actor who can decide (`/decision`), resume (`/resume-review`) and read the decision history; a coordinator reassigned away loses the authority immediately.
- **Event Organiser (owner):** the only actor who can answer a clarification (`/clarification-response`); reads the retained review activity.
- **Unrelated organiser or coordinator:** 404 on history and mutations — the request's existence is not disclosed.
- **Other authenticated roles:** 403; **no session:** 401 before anything is read.

### Allowed state transitions

| From | To | Trigger |
| --- | --- | --- |
| `Submitted` | `Under Review` | review start (transition controller) |
| `Under Review` | `Approved` | AC2 decision, assigned coordinator |
| `Under Review` | `Changes Requested` | AC2 decision with a required reason |
| `Under Review` | `Rejected` | AC2 decision with a required reason |
| `Changes Requested` | `Under Review` | AC4 resume, assigned coordinator, only after the organiser responds |

No other transition is reachable through this story's endpoints; a stale or repeated decision conflicts (409).

### Persistence and atomicity

- Each decision is written with its reason (when required) and the resulting status in one server-only database call under the event-request row lock; a refused call writes neither (`AC3-X3`).
- A clarification response attaches once to the active clarification and never changes the submitted fields or the request status.
- Decisions and responses are retained history: a later decision appends, it never updates or deletes earlier rows (`AC3-H1`).
- The history table and its RPCs are service-only: browser roles cannot read the table or execute the functions (`AC3-X3`, migration `0016` + `verify_event_request_review_decisions.sql`).

### Assumptions and open questions

1. The old catalogue's `AC2-T4` row (an unrelated or reassigned-away coordinator cannot even read the request) is now owned by SCRUM-39's labelled tests in `test_event_request_controller.py`; this matrix proves the mutation-side refusals (`AC2-N1`, `AC2-N2`) and the history-visibility partition (`AC3-P1…P5`).
2. The old `UI-T1` row (progress tracker per status) is owned by SCRUM-28's labelled tests in `frontend/__tests__/event-request-status.test.tsx`; not re-labelled here.
3. The reason/response boundary of 2,000 characters comes from the September catalogue's recorded rule; confirm against Jira at review.

### How to run the suites

| Area | Command |
| --- | --- |
| Event-request service | `cd backend/eventRequestService && .venv/bin/pytest tests/test_event_review_decision.py` (full suite: `pytest`) |
| Frontend components | `cd frontend && npm test` |
| Frontend browser journeys | `cd frontend && npm run test:e2e` (disposable APIs on ports 8104/8103, test frontend on 3100) |
| Database verification | `database/verify_event_request_review_decisions.sql`, after migration `0016`, rollback-only |
| Gates | `ruff check .` (backend), `npm run lint` / `npm run typecheck` / `npm run build` (frontend) |

## Test case specification

Layers: API = `backend/eventRequestService/tests/test_event_review_decision.py`; UI = `frontend/__tests__/event-request-status.test.tsx`; E2E = `frontend/e2e/review-event-request.spec.ts`; DB = `database/verify_event_request_review_decisions.sql` (rollback-only, after migration `0016`).

| ID | AC | Test scenario | Technique | Pre-conditions | Test steps | Test data | Expected result | Forbidden side effects | Layer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AC1-H1 | AC1 | The coordinator reads the complete submitted request with no edit controls | Happy | Under Review request with unique values in all nine fields, coordinator assigned | Render the coordinator detail for the request | name, purpose, description, 125 attendees, 20 Nov 2026, venue/accessibility/equipment/registration values | All nine values render read-only; no textbox and no save/submit/delete control | No editing control appears; no field is editable | UI (+ same assertions in the E2E journey, AC2-H1) |
| AC2-P1 | AC2, AC3 | An Approved outcome settles the review and is retained | Partition | Assigned coordinator; request Under Review | POST `/decision` with `Approved` | reason None | 200; status `Approved`; exactly one decision row with the coordinator id | No duplicate request; no other status change | API (+ DB section 4) |
| AC2-P2 | AC2, AC3 | A Changes Requested outcome is stored with its reason | Partition | As AC2-P1 | POST `/decision` with `Changes Requested` and a reason | "Please clarify the accessibility plan." | 200; status `Changes Requested`; row carries the reason | Submitted fields unchanged | API (+ DB section 5) |
| AC2-P3 | AC2, AC3 | A Rejected outcome is stored with its reason | Partition | As AC2-P1 | POST `/decision` with `Rejected` and a reason | "The proposed event is outside the programme scope." | 200; status `Rejected`; row carries the reason | No planning action occurs | API (+ DB section 9) |
| AC2-P4 | AC2 | A stale or repeated decision on a settled request writes nothing | Partition (+ DB) | Request already `Approved` | POST another decision; count history rows | "Rejected" / "stale decision" | 409; still exactly one history row | No second outcome row | DB section 10 |
| AC2-P5 | AC2 | A decision is refused from `Submitted` | Partition | Request `Submitted` | POST `/decision` | `Approved` | 409; status unchanged; no decision row | Nothing written | API |
| AC2-P6 | AC2 | A decision is refused from `Rejected` | Partition | Request `Rejected` | POST `/decision` | `Approved` | 409; status unchanged; no decision row | Nothing written | API |
| AC2-H1 | AC2, AC3, AC4, AC1 | Browser journey: clarify → organiser responds → resume → approve | Happy | Playwright seed: Under Review event, coordinator and organiser sessions | Coordinator opens the detail, checks every field visible and no edit controls, requests clarification with a reason; organiser opens the edit page, sees the read-only notice and answers; coordinator continues review and approves; checks the Review activity region | seed "SCRUM-17 Review Workshop", attendance 40, reason "Clarify whether a microphone is required.", response "A wireless microphone is required." | `Changes Requested` and the reason visible; response confirmation; `Approved` visible; question, response and outcome all in the history region | No textbox or save/submit/delete control at any step; no duplicate request created | E2E |
| AC2-N1 | AC2 | A coordinator who is not the current assignee cannot decide | Negative | Assigned to coord-1 | POST `/decision` as coord-2 | `Approved` | 403; status and history unchanged | Nothing written | API (+ DB section 2) |
| AC2-N2 | AC2 | Reassignment immediately strips the former coordinator | Negative | Reassigned from coord-1 to coord-2 | POST `/decision` as coord-1 | `Approved` | 403; status and history unchanged | Nothing written | API (+ DB section 2) |
| AC2-N3 | AC2 | A lifecycle value outside the review outcomes cannot pass | Negative | Request Under Review | POST `/decision` with an unknown decision | "Completed", "skip ahead" | 422; still Under Review; no decision row | Nothing written | API |
| AC2-N4 | AC2 | An unknown request id returns 404 without an orphan record | Negative | No such request | POST `/decision` on a random id | `00000000-…-0001` | 404; no decision row created | No orphan history | API (+ DB section 1) |
| AC2-N5 | AC2 | Malformed request ids are rejected at the boundary | Negative | None | POST to `/event-requests/not-a-uuid/{review, resume-review, decision, cancellation, completion}` | "not-a-uuid" | 422 on every route | Nothing reaches Supabase | API |
| AC2-X1 | AC2, AC4 | Each mutation is restricted to the actor its criterion names | Cross-cutting | Assigned coordinator fixtures for all three endpoints; caller holds the wrong role | Organiser calls `/decision` and `/resume-review`; coordinator calls `/clarification-response` | roles `["event_organiser"]` / `["event_coordinator"]` | 403 on each; status and history snapshots unchanged | Nothing written | API |
| AC2-X2 | AC2, AC4 | A caller with no session cannot mutate review state | Cross-cutting | Under Review fixture, no auth header | POST each of the three endpoints without a session | decision / response payloads | 401 on each; request row and history byte-identical | Nothing written | API |
| AC3-H1 | AC3, AC4 | Clarify → respond → resume → approve appends without overwriting | Happy | Assigned coordinator; request Under Review | The four calls in sequence | reason "Clarify equipment.", response "Two wireless microphones are required." | All 200; exactly two decision rows; the clarification keeps reason and response; the approval row has reason None | Earlier activity never updated or deleted | API (+ DB section 8) |
| AC3-H2 | AC3 | The retained outcome and reason render for related actors | Happy | One retained Changes Requested decision with its reason | Render `ReviewDecisionHistory` | reason "Clarify the equipment requirements." | The Review activity region shows the outcome and the reason | No outcome or reason dropped | UI |
| AC3-H3 | AC3 | The final decision renders beside the exchange that informed it | Happy | Decisions: Approved, then the earlier clarification with its response | Render `ReviewDecisionHistory` | the two-row history | Approved, the question and the response all visible | Nothing overwritten or hidden | UI |
| AC3-N1 | AC3 | Clarify and reject require a meaningful reason | Negative | Assigned coordinator; request Under Review | POST `/decision` with a blank, then a missing reason for both outcomes | "   " / None | 422 for each; status stays Under Review; no decision row | Nothing written | API (+ DB section 3) |
| AC3-P1 | AC3 | The owner reads the retained decision history | Partition | Decision exists; caller is the owning organiser | GET `/event-requests/{id}/decisions` | — | 200; the outcome and reason are returned | — | API |
| AC3-P2 | AC3 | The assigned coordinator reads the retained decision history | Partition | As AC3-P1; caller is coord-1 | GET decisions | — | 200; outcome and reason returned | — | API |
| AC3-P3 | AC3 | Another organiser cannot read the history | Partition | As AC3-P1; caller is organiser-2 | GET decisions | — | 404 | No reason disclosed | API |
| AC3-P4 | AC3 | Another coordinator cannot read the history | Partition | As AC3-P1; caller is coord-2 | GET decisions | — | 404 | No reason disclosed | API |
| AC3-P5 | AC3 | An unrelated role is refused the history | Partition | As AC3-P1; caller is an operations manager | GET decisions | — | 403 | No reason disclosed | API |
| AC3-B1 | AC3 | A 2,000-character decision reason is retained | Boundary | Request Under Review | POST `/decision` with a 2,000-char reason | `"r" × 2000` | 200; the row carries the full reason | — | API |
| AC3-B2 | AC3 | A 2,001-character decision reason is refused | Boundary | As AC3-B1 | POST with a 2,001-char reason | `"r" × 2001` | 422; still Under Review; no decision row | Overflow writes nothing | API |
| AC3-X1 | AC3, AC2, AC4 | A history outage is an accessible alert, not an apparently empty record | Cross-cutting | Component rendered with history unavailable | Render `ReviewDecisionHistory` with `unavailable` | — | Alert "Review activity unavailable"; message says it could not be loaded | Not presented as an empty history | UI |
| AC3-X2 | AC3, AC2, AC4 | A failed history read withholds blind actions for both actors | Cross-cutting | Seeded events with `review_history_unavailable` (Under Review, and Changes Requested with a response) | Open the coordinator detail for both and the organiser edit page | seeds | Alert visible; Approve/Request clarification/Reject absent; Continue review absent; Clarification response control absent | No blind mutation path rendered | E2E |
| AC3-X3 | AC3 | Decision history is service-only and functions are server-only | Cross-cutting | Migrated cluster (0016) | `has_table_privilege` / `has_function_privilege` for all three roles | `anon`, `authenticated`, `service_role` | anon/authenticated: no SELECT on the table, no EXECUTE on any review RPC; service_role: EXECUTE granted | Browser roles never bypass the API | DB |
| AC4-H1 | AC4 | The owner answers without editing the submitted request | Happy | Active clarification on the owner's request | POST `/clarification-response`; inspect the row and the request | "A wireless microphone is required." | 200; response and timestamp retained; status still `Changes Requested`; event fields unchanged | Submitted fields and status do not change | API (+ DB section 6) |
| AC4-H2 | AC4 | Resume returns to Under Review only after the response | Happy | Decision exists; then the owner responds | POST `/resume-review` before the response; respond; POST again | — | 409 before; 200 after; status `Under Review` | No request or decision duplicated | API (+ DB section 7) |
| AC4-P1 | AC4 | A response is refused from `Draft` | Partition | Request `Draft` | POST `/clarification-response` | "More details." | 409; status unchanged | No response created | API |
| AC4-P2 | AC4 | A response is refused from `Submitted` | Partition | Request `Submitted` | POST response | "More details." | 409; status unchanged | No response created | API |
| AC4-P3 | AC4 | A response is refused while `Under Review` | Partition | Request `Under Review` | POST response | "More details." | 409; status unchanged | No response created | API |
| AC4-P4 | AC4 | A response is refused from `Rejected` | Partition | Request `Rejected` | POST response | "More details." | 409; status unchanged | No response created | API |
| AC4-N1 | AC4 | Another organiser cannot answer someone else's clarification | Negative | Active clarification; caller organiser-2 | POST `/clarification-response` | "More details." | 404; `organiser_response` stays None | No response created or replaced | API (+ DB section 6 refusal) |
| AC4-N2 | AC4 | The coordinator cannot skip the organiser's response | Negative | Clarification unanswered | POST `/resume-review` | — | 409; still `Changes Requested` | Nothing written | API |
| AC4-N3 | AC4 | A blank response is refused without mutation | Negative | Unanswered clarification | POST response of whitespace | `"   "` | 422; response and `responded_at` stay None | Nothing written | API |
| AC4-N4 | AC4 | A repeated response cannot replace the first answer | Negative | Response already retained | POST a second response | "Replace that with four microphones." | 409; the history equals the retained snapshot | The first answer is preserved | API |
| AC4-B1 | AC4 | A 2,000-character response is retained | Boundary | Unanswered clarification | POST a 2,000-char response | `"a" × 2000` | 200; the row carries the response | — | API |
| AC4-B2 | AC4 | A 2,001-character response is refused | Boundary | As AC4-B1 | POST a 2,001-char response | `"a" × 2001` | 422; the clarification stays unanswered | Overflow writes nothing | API |

## Latest execution record

No suites were run for this conversion (label-and-matrix pass only). The label comments were added on the `docs/testcase-gap-sweep` working tree, 1 November 2026, by Claude for Yang Xue, and still need a teammate review of the test design (`testing.md` §10) plus a fresh run for any Done claim. The 30 September 2026 evidence in the previous revision (backend 208 passed, frontend 141 passed, 19 Playwright journeys, SQL verifier passed on the shared project) is provenance for a different commit and is **not** current evidence.

| ID | Automation status | Actual result | Execution status | Build or commit | Executed by and date | Remarks and evidence |
| --- | --- | --- | --- | --- | --- | --- |
| AC2-P1…P3, AC3-N1, AC2-N1, AC2-N2, AC2-P5, AC2-P6, AC2-N3, AC2-N4, AC3-P1…P5, AC4-H1, AC4-P1…P4, AC4-N1, AC4-H2, AC4-N2, AC3-H1, AC4-N3, AC4-N4, AC3-B1, AC3-B2, AC4-B1, AC4-B2, AC2-X1, AC2-X2, AC2-N5 | Automated (label added in this pass) | Not run in this pass | Not executed | working tree, `docs/testcase-gap-sweep`, labels only | Claude for Yang Xue, 1 Nov 2026 | `backend/eventRequestService/tests/test_event_review_decision.py` — labels `SCRUM-17 AC…` added above the tests; behaviour itself unchanged |
| AC1-H1, AC3-H2, AC3-H3, AC3-X1 | Automated (label added in this pass) | Not run in this pass | Not executed | as above | Claude for Yang Xue, 1 Nov 2026 | `frontend/__tests__/event-request-status.test.tsx` — the four review-decision tests wave 1 deliberately left unlabelled |
| AC2-H1, AC3-X2 | Automated (label added in this pass) | Not run in this pass | Not executed | as above | Claude for Yang Xue, 1 Nov 2026 | `frontend/e2e/review-event-request.spec.ts` — both journeys |
| AC2-P4, and the DB layer of AC2-P1…P3, AC2-N1, AC2-N2, AC2-N4, AC3-N1, AC3-H1, AC3-X3, AC4-H1, AC4-N1, AC4-H2 | Automated (label added in this pass) | Not run in this pass | Not executed | as above | Claude for Yang Xue, 1 Nov 2026 | `database/verify_event_request_review_decisions.sql` — section comments labelled `SCRUM-17 AC…` (rollback-only, after migration 0016) |
