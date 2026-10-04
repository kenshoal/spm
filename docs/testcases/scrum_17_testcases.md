# SCRUM-17 — Review and Decide on an Event Request

**Jira:** [SCRUM-17](https://is212g9t4.atlassian.net/browse/SCRUM-17)

**User story:** As an Event Coordinator, I want to review a submitted request and approve it, reject it, or ask for clarification, so that planning only proceeds on sufficiently clear requests.

## Story contract review

The current Jira user story and all four acceptance criteria were reviewed against the repository and related backlog stories before this completion pass. The user approved continuing SCRUM-17 with the existing clarification-only scope on 30 September 2026.

| Criterion | Outcome | Reason |
| --- | --- | --- |
| AC1 | Keep | Complete read-only request visibility is necessary and independently testable. |
| AC2 | Keep | The three coordinator outcomes define the story's decision boundary. |
| AC3 | Keep | Retained reasons provide the required audit evidence for review outcomes. |
| AC4 | Clarify | “Clarification” supplements the submitted request; it does not amend canonical event fields. |

Notifications remain in SCRUM-36, post-approval event changes remain in SCRUM-35, relationship-based access remains in SCRUM-39 and complete status-transition history remains in SCRUM-48.

## Increment scope

An assigned Event Coordinator can read a submitted request, start review and record **Approved**, **Changes Requested**, or **Rejected**. Decisions and reasons are retained and written atomically with status changes. When clarification is requested, the owning organiser responds without editing the submitted request; the assigned coordinator then continues the review.

Notification delivery belongs to SCRUM-36. Post-approval organiser change requests belong to SCRUM-35. SCRUM-17 retains the state and content those stories can consume.

- **Actors and access:** Only the currently assigned Event Coordinator can review, decide or resume; only the owning Event Organiser can answer a clarification. Both related actors can read retained review activity.
- **Transitions:** `Submitted → Under Review`; `Under Review → Changes Requested / Approved / Rejected`; and `Changes Requested → Under Review` after an organiser response.
- **Persistence and atomicity:** Each decision is retained with its reason and written atomically with the resulting status under the event-request row lock. Clarification responses attach once to the active clarification without changing submitted fields.
- **Assumption:** A clarification response is supplementary prose. Any canonical post-submission field amendment requires the separate change-request workflow.

## Acceptance criteria

- **AC1:** The assigned Event Coordinator can view the complete submitted event request.
- **AC2:** While a request is under review, the assigned Event Coordinator can approve it, request clarification, or reject it.
- **AC3:** Each outcome and its reason are retained; clarification and rejection require a reason.
- **AC4:** The owning organiser can view and answer a clarification without editing submitted fields, after which the assigned coordinator can continue review.

## Acceptance-criteria test matrix

| ID | Criterion | One-line purpose comment | Layer | Preconditions and input | Action | Expected result | Forbidden side effects | Status or evidence |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AC1-T1 | AC1 | Proves the assigned coordinator receives every submitted field needed for a decision. | Component + E2E | Assigned coordinator; complete `Under Review` request with unique values. | Open and reload the coordination detail. | All nine submitted values render read-only. | No save, submit, delete or field-editing control appears. | Passing frontend and Playwright tests. |
| AC1-T2 | AC1 | Prevents unrelated coordinators from reading another coordinator's request. | API | Request assigned to coordinator A; caller is coordinator B. | Retrieve the request and its review activity. | Both return not found. | No request field or review reason is disclosed. | Passing backend tests. |
| AC2-T1 | AC2 | Proves approval settles an active review. | API + E2E | Assigned coordinator; request is `Under Review`. | Submit `Approved`. | Status becomes `Approved` and one outcome is retained. | No duplicate request is created. | Passing backend and Playwright tests. |
| AC2-T2 | AC2 | Proves an unclear request can be returned with guidance. | API + E2E | Assigned coordinator; request is `Under Review`; reason supplied. | Request clarification. | Status becomes `Changes Requested` and the reason persists. | Submitted fields remain unchanged. | Passing backend and Playwright tests. |
| AC2-T3 | AC2 | Proves rejection closes review with a reason. | API | Assigned coordinator; request is `Under Review`; reason supplied. | Submit `Rejected`. | Status becomes `Rejected` and the reason persists. | No planning action occurs. | Passing backend tests. |
| AC2-T4 | AC2 | Stops an unrelated or reassigned-away coordinator from deciding. | API + database | Caller is not the latest assigned coordinator. | Attempt a review decision. | The operation is forbidden. | Status and activity remain unchanged. | Passing backend and SQL verification. |
| AC2-T5 | AC2 | Prevents stale or repeated decisions from overwriting an outcome. | API + database | Request has already left `Under Review`. | Attempt another decision. | Conflict is returned. | No additional decision is written. | Passing backend and SQL verification. |
| AC2-T6 | AC2 | Restricts every review mutation to its named actor. | API | Organiser calls decision/resume, or coordinator calls clarification response. | Submit the wrong-role operation. | Each request returns forbidden. | Status, reason and response remain unchanged. | Passing backend tests. |
| AC3-T1 | AC3 | Requires actionable guidance for clarification and rejection. | Validation | Blank reason for `Changes Requested` or `Rejected`. | Submit the decision. | Validation returns 422. | No status or activity write occurs. | Passing backend and frontend tests. |
| AC3-T2 | AC3 | Keeps each decision and status update atomic. | Database | Valid or refused assigned-coordinator decision. | Execute the locked database function. | Valid writes commit together; refused calls write neither. | No partial outcome or status remains. | Passing SQL verification. |
| AC3-T3 | AC3 | Restricts retained decisions to users related to the request. | Security/API | Owner, assigned coordinator and unrelated users attempt access. | Read review activity. | Only the owner and assigned coordinator succeed. | Browser roles cannot read the table directly. | Passing backend and SQL verification. |
| AC3-T4 | AC3 | Ensures a final decision does not erase the clarification exchange that informed it. | API + E2E + database | Clarification and response exist; review resumes. | Approve and reload the activity. | Approval, question and response all remain visible. | Earlier activity is not updated or deleted. | Passing backend, Playwright and SQL verification. |
| AC3-T5 | AC3 | Enforces the documented decision-reason boundary. | API | Reasons of 2,000 and 2,001 characters. | Request clarification. | 2,000 is retained; 2,001 returns 422. | Rejected overflow leaves the request `Under Review`. | Passing backend tests. |
| AC4-T1 | AC4 | Lets the owner answer while the submitted request stays immutable. | API + E2E | Active clarification on the owner's request. | Submit a non-blank response. | Response and timestamp persist. | Event fields and request status do not change. | Passing backend and Playwright tests. |
| AC4-T2 | AC4 | Prevents unrelated, blank, duplicate or invalid-state responses. | API + database | Wrong owner, blank text, prior response or non-clarification status. | Submit a clarification response. | Request is rejected with 404, 409 or 422 as appropriate. | No response is created or replaced. | Passing backend and SQL verification. |
| AC4-T3 | AC4 | Requires an organiser response before the assigned coordinator can continue. | API + E2E | Active clarification, before and after the owner responds. | Call `resume-review`. | It fails before the response and returns to `Under Review` afterward. | No request or decision is duplicated. | Passing backend and Playwright tests. |
| AC4-T4 | AC4 | Enforces the documented clarification-response boundary. | API | Responses of 2,000 and 2,001 characters. | Submit the response. | 2,000 is retained; 2,001 returns 422. | Overflow leaves the clarification unanswered. | Passing backend tests. |
| UX-T1 | AC2-AC4 | Exposes review-activity outages instead of presenting incomplete workflow data. | Component + E2E | Request loads while review-activity retrieval fails. | Open coordinator and organiser detail pages. | An accessible refresh error appears. | Decision and response controls that depend on history are withheld. | Passing frontend and Playwright tests. |
| UI-T1 | Supporting status display | Keeps the full event journey visible at every status. | Component | Render each event status. | Inspect the progress tracker. | Seven milestones show completed, current or not reached. | Future stages are not presented as completed. | Passing frontend tests. |

## Definition of Done status

- [x] Review outcomes and allowed source states are explicit.
- [x] Assigned-coordinator and organiser ownership checks are enforced.
- [x] Decision, response and resume operations use locked server-only database functions.
- [x] Submitted request fields stay read-only during clarification.
- [x] Backend, frontend and critical browser tests cover success and forbidden side effects.
- [x] Migration, verification script and API notes are included.
- [x] Migration 0016 and SQL verification ran on the shared Supabase project.
- [ ] Historical Red-phase output is unavailable because the core implementation pre-dated adoption of `SKILLS.md`; current regression tests have Green evidence and independent review.
- [ ] Pull-request CI and reviewer approval have passed.

## Local validation evidence

Validated on 30 September 2026 against the current local working tree:

| Boundary | Command or environment | Result | Limitation |
| --- | --- | --- | --- |
| Backend API/service/repository | `.venv/bin/python -m pytest -q` | `208 passed`; two dependency deprecation warnings. | Uses isolated repositories for most controller tests. |
| Backend static analysis | `.venv/bin/python -m ruff check .` | Passed. | Local result only. |
| Frontend unit/component | `npm test -- --run` | `141 passed` across 17 files. | API calls are mocked at this layer. |
| Frontend types and lint | `npm run typecheck`; `npm run lint -- --quiet` | Passed. | Local result only. |
| Production build | `npm run build -- --webpack` | Passed. | Required network access to fetch configured Geist fonts. |
| Browser workflow | `CI=1 npx playwright test` | `19 passed`, including two SCRUM-17 journeys. | Uses isolated Node mock services, not the live FastAPI/Supabase stack. |
| Shared database | Supabase MCP executing `database/verify_event_request_review_decisions.sql` | Passed with transaction rollback; no fixture data retained. | Verifies database functions directly rather than through the browser. |
| Diff hygiene | `git diff --check` | Passed. | Does not replace review or CI. |

Focused test paths include `backend/eventRequestService/tests/test_event_review_decision.py`, `frontend/__tests__/event-request-status.test.tsx` and `frontend/e2e/review-event-request.spec.ts`. Pull-request CI and reviewer approval remain unverified until the exact commit is pushed.
