# SCRUM-37 — Notify Event Workflow Changes

**Jira:** [SCRUM-37](https://is212g9t4.atlassian.net/browse/SCRUM-37)

**User story:** As a user responsible for an event, I want to be notified when its workflow or important arrangements change, so that I can take the action required of my role.

**Split on 8 October 2026.** This story keeps AC1–AC3 and the in-app, prompt-delivery and relevance parts of AC6. AC4, AC5 and the email, per-type setting and grouped-delivery parts of AC6 were not built in Sprint 2 and moved to [SCRUM-57](https://is212g9t4.atlassian.net/browse/SCRUM-57) (backlog). The Product Owner has not yet confirmed the split.

## Story contract review

The user story and its acceptance criteria were reviewed on 5 October 2026 against the repository, the accepted customer clarifications (#117, #55, #37) and the neighbouring stories SCRUM-35, SCRUM-36 and SCRUM-17. Jira does not number the criteria. **AC1–AC5 follow the order of the five bullets in Jira, and AC6 is the cross-cutting channel, timing and relevance bullet.**

| Criterion | Outcome | Reason |
| --- | --- | --- |
| AC1 | Keep | Already refined on 27 September: the Operations Manager is no longer notified of every submission (#117). The Organiser's confirmation is observable in their inbox. |
| AC2 | Keep | Observable in the assigned Coordinator's inbox. |
| AC3 | Clarify | Intent is valid, but SCRUM-36 AC1 also lists "returned for clarification". Proposed split: SCRUM-37 sends the clarification notice, as this AC says; SCRUM-36 builds on the same hook for approved and rejected outcomes. Needs Heng Rui's confirmation. |
| AC4 | Keep | Needs an approved significant change to react to, which appears to come from SCRUM-35 (Request a Change to an Event, still in progress; its criteria were not reviewed here). Not built. |
| AC5 | Keep | Deferred. `POST /event-requests/{id}/cancellation` already exists, so the hook is feasible later; it is not built in this increment. |
| AC6 | Split | Three independently testable rules: **relevance** (built), **channel** (in-app built; email and per-type settings not built) and **timing** (prompt delivery built, where the AC1 relay polls every 10 seconds; grouped delivery not built). |

**Approval status.** Tate Lim, the story owner, asked for AC1–AC3 and the in-app side of AC6 to be built on 5 October 2026. The outcomes in the table above (especially the AC3 split with SCRUM-36 and the AC6 split) have **not** been approved by the Product Owner, and the Product Owner has not yet confirmed the 27 September refinement (Jira comment 10033). On 8 October 2026 Tate Lim, as story owner, split the unbuilt criteria into SCRUM-57 (see the note at the top); that split is also **not** yet approved by the Product Owner.

## Increment scope

This increment delivers the in-app notification path end to end for three events: an Organiser's submission confirmation (AC1), a Coordinator's assignment notice (AC2) and an Organiser's clarification notice (AC3). Users read their own notifications on a Notifications page and mark them read.

- **Actors and access:** a user reads and marks only their own notifications; the user id comes from authService, never from the request. Another user's notification is indistinguishable from a missing one (404). Recipients are the Organiser who owns the request (AC1, AC3) and the assigned Coordinator (AC2).
- **Allowed state transitions:** this story writes none. It reacts to transitions owned by other stories; AC3 follows `Under Review → Changes Requested` (SCRUM-17).
- **Persistence and atomicity:**
  - **AC1** is at-least-once. The database already records one outbox row per submission; a relay marks a row published only after notificationService accepts it, and notificationService stores a repeated `event_id` once.
  - **AC2 and AC3** are sent once, after the change is recorded, and are not retried. A failed send is logged and never fails the assignment or the decision. A notice lost to an outage is not redelivered.
- **Excluded:** approved, rejected, venue-booking and confirmation notices (SCRUM-36); significant-change notices (AC4, SCRUM-35); cancellation notices (AC5); email delivery, per-type channel settings and grouped delivery (AC6). AC4, AC5 and the AC6 remainder are now tracked in SCRUM-57.

### Assumptions and open questions

- AC3 and SCRUM-36 AC1 overlap on "returned for clarification" (see the review table). Heng Rui and the Product Owner need to confirm which story owns it.
- `POST /notifications/events` is internal and **not authenticated** (noted in notificationService's `app/main.py`). Anyone who can reach the service can create a notification for any user. This must be closed before go-live; it is not part of this increment.
- The clarification notice reuses the request's `/edit` page as its link, because that page hosts the Organiser's clarification response.
- A clarification notice lost to a notificationService outage is not redelivered. If the Product Owner needs it to be reliable, it should go through the outbox like AC1, which needs a database change owned by SCRUM-17.

## Acceptance criteria

- **AC1:** Given an event request is submitted, when submission succeeds, then the Organiser receives confirmation.
- **AC2:** Given a Coordinator is assigned or reassigned, when the assignment is recorded, then the assigned Coordinator is notified.
- **AC3:** Given clarification is requested, when the request is recorded, then the Organiser is notified with the clarification required.
- **AC4:** Given an approved significant change affects venue or equipment arrangements, when the change is applied, then the responsible Coordinator and affected internal staff are notified. *Not built; moved to SCRUM-57.*
- **AC5:** Given an event is cancelled, when cancellation is recorded, then the Organiser, assigned Coordinator and staff responsible for committed arrangements are notified where applicable. *Not built; moved to SCRUM-57.*
- **AC6:** Notifications are delivered in-app and/or by email, configurable per type (#37); they need not be real time and may be grouped at a configurable interval (#55); a user receives a notification only for events matching their role and relationship to the event (C-1b). *In-app, prompt-delivery and relevance rules built; email, per-type settings and grouping not built and moved to SCRUM-57.*

## Test-case specification

Test cases for AC4, AC5 and the unbuilt parts of AC6 are designed with their increments, now in SCRUM-57. IDs are never reused. Find the tests for any ID with `grep -rn "AC3-H1" backend frontend`.

| ID | AC | Technique | Layer | Scenario | Pre-conditions and input | Action | Expected result | Forbidden side effects |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AC1-H1 | AC1 | Happy | Unit, component, E2E | A submission produces a confirmation the Organiser can read. | Organiser has submitted; the outbox holds one unpublished `event_request.submitted` row for them. | Relay pass runs; Organiser opens Notifications. | One `event_request_submitted` notice for that Organiser with `event_id` = outbox row id; row marked published; inbox shows "Your event request was submitted." linked to the request. | Notice for another user; row published before delivery is accepted. |
| AC1-H2 | AC1 | Happy | Unit | The outbox is read oldest first and only the delivered row is marked. | Several unpublished rows; Supabase and the service URL both set. | List rows, then mark one. | Oldest first; marking updates only that unpublished row and keeps its first delivery time; the relay is built. | Other rows or an earlier `published_at` changed. |
| AC1-N1 | AC1 | Negative | Unit | A failed delivery is retried, not lost. | notificationService unreachable or answering with an error; or Supabase failing. | Relay pass. | Delivery reported as not delivered; row left unpublished and sent on a later pass; one failed pass does not stop the relay; a Supabase failure raises a repository error. | Row marked published; background task ending on an exception. |
| AC1-N2 | AC1 | Negative | Unit | Nothing is consumed when nobody can receive it. | `NOTIFICATION_SERVICE_URL` or Supabase not set. | Build the relay; call the client. | No relay is built; the client reports not delivered and makes no HTTP call. | Outbox rows marked published. |
| AC2-H1 | AC2 | Happy | Unit, API, component, E2E | An assigned Coordinator is told. | A Coordinator is assigned or reassigned. | Assignment is recorded. | `coordinator_assigned` event posted for that Coordinator, stored by notificationService, shown in their inbox with a link to the coordination page. | Anyone else notified. |
| AC2-N1 | AC2 | Negative | Unit | A notification problem never fails the assignment. | Service URL unset, unreachable, or returning an error. | Assign a Coordinator. | Assignment succeeds; the failure is logged, not raised. | Exception from the client; assignment rolled back. |
| AC3-H1 | AC3 | Happy | API, component, E2E | The Organiser is told what to clarify. | Request is `Under Review`, the caller is its assigned Coordinator, a reason is given. | Record `Changes Requested`. | 200 and status `Changes Requested`; one `clarification_requested` notice to the owning Organiser carrying the request id and reason; the inbox card shows the reason and links to `/event-requests/{id}/edit`. | Notice to the Coordinator or anyone else. |
| AC3-H2 | AC3 | Happy | Unit | The notice has the body notificationService expects. | A configured client. | Send a clarification notice. | POST body has `event_type`, `recipient_id` = Organiser and `payload` {`event_request_id`, `reason`}. | An `event_id` (the notice is not deduplicated). |
| AC3-P1, AC3-P2 | AC3 | Partition | API | Other outcomes send no clarification notice. | `Under Review`; decision `Approved` (no reason) or `Rejected` (with reason). | Record the decision. | 200 and the new status. | A `clarification_requested` notice (approved and rejected notices belong to SCRUM-36). |
| AC3-P3 | AC3 | Partition | Component | A missing reason does not leave a blank line. | Notice payload with no reason, a blank reason, or a non-text reason. | Describe the notice. | Message and link shown; no detail line. | A blank or "undefined" line. |
| AC3-N1 | AC3 | Negative | API | Only the assigned Coordinator's decision notifies. | Caller is a different Coordinator. | Request `Changes Requested`. | 403; status unchanged. | Decision stored; notice sent. |
| AC3-N2 | AC3 | Negative | API | A stale decision notifies nobody. | Request already `Approved`. | Request `Changes Requested`. | 409; status unchanged. | Decision stored; notice sent. |
| AC3-N3 | AC3 | Negative | API | A decision with no reason notifies nobody. | Blank reason. | Request `Changes Requested`. | 422; status unchanged. | Decision stored; notice sent. |
| AC3-N4 | AC3 | Negative | API | An outage does not block the Coordinator. | notificationService unreachable. | Record `Changes Requested`. | 200; status `Changes Requested`; reason retained. | Decision rolled back or refused. |
| AC3-N5, AC3-N6 | AC3 | Negative | Unit | A send failure is logged, not raised. | Connection failure (N5) or error response (N6). | Send a clarification notice. | Returns normally; a warning names the Organiser and request. | Exception from the client. |
| AC3-N7 | AC3 | Negative | Unit | Unconfigured means nothing is attempted. | No service URL. | Send a clarification notice. | No HTTP call. | An HTTP call. |
| AC6-H1 | AC6 | Happy | API, repository, component | A user sees only their own notifications, newest first. | Notifications exist for two users. | Open the inbox. | Own notifications only, newest first, with the fields the inbox shows and the time they were created. | Another user's notification; the recipient id. |
| AC6-H2 | AC6 | Happy | API, repository, action, E2E | A user can mark their own notification read. | An unread notification of theirs. | Mark as read. | Read time set; inbox refreshed; unread count falls. | Another notification changed. |
| AC6-P1 | AC6 | Partition | API, repository, component | Unread and read notifications are treated differently. | Mixed read and unread. | List unread only; render both. | Unread only is filtered in the database; only unread cards offer "Mark as read". | Read cards offering "Mark as read". |
| AC6-P2 | AC6 | Partition | API | Event shapes the contract allows are all accepted. | Same `event_id` for different recipients; no `event_id`; no payload. | Post each event. | Stored for each recipient; events without `event_id` each stored; payload defaults to empty. | A recipient missed. |
| AC6-P3 | AC6 | Partition | Repository | Marking an already-read notification is not an error. | A notification already read. | Mark as read again. | Returned unchanged with its first read time. | Read time overwritten. |
| AC6-P4 | AC6 | Partition | Component | A type or notice the page cannot link still shows. | Unknown event type, or no destination. | Render the inbox. | Generic message; no "View request" link. | A dead link. |
| AC6-P5 | AC6 | Partition | Component | An empty inbox says so. | No notifications. | Render the inbox. | "No notifications yet." | A blank page. |
| AC6-B1 | AC6 | Boundary | API | The list size is capped and out-of-range limits are refused. | 3 notifications; limits 2, 0 and 101. | List with each limit. | `limit=2` returns 2; 0 and 101 return 422. | An unbounded list; a silently adjusted limit. |
| AC6-N1 | AC6 | Negative | API, repository | A repeated event notifies once. | Same recipient and `event_id` sent twice. | Post twice. | Both accepted; one row stored. | A duplicate row. |
| AC6-N2 | AC6 | Negative | API | Malformed events are refused. | Missing or blank type or recipient, over-long recipient, non-object payload. | Post the event. | 422; nothing stored. | A stored row. |
| AC6-N3 | AC6 | Negative | API, repository, action | An outage is reported, not hidden. | Database failing, Supabase not configured, or the notification service unreachable. | Post an event; load the inbox. | 502 or an explicit configuration error; the page reports the failure. | An empty inbox that hides the outage. |
| AC6-N4 | AC6 | Negative | API, action | The inbox needs a valid session. | No, malformed or expired token; authService down or returning no user id. | Call the inbox. | 401 (502 when authService is down); an expired session goes back to sign in. | Notifications returned. |
| AC6-N5 | AC6 | Negative | API, repository, action | Another user's notification cannot be probed or changed. | A notification belonging to someone else; a malformed id. | Mark as read. | 404 identical to a missing one; malformed id 422; the page says it no longer exists. | The notification marked read; existence disclosed. |
| AC6-N6 | AC6 | Negative | Component | An odd payload cannot produce a link to another route. | Request id `a/b`, or no id. | Describe the notice. | Id is URL-encoded; no id means no link. | A link to another route. |
| AC6-X1 | AC6 | Cross-cutting | API | The inbox trusts only the identity authService verifies. | Valid token. | Call the inbox. | Uses the verified user id; accepts a lowercase `bearer` scheme; API docs offer a bearer sign-in. | A user id taken from the request. |
| AC6-X2 | AC6 | Cross-cutting | Component | Every user with a workspace can reach the inbox. | Each staff role. | Build the navigation. | A Notifications link after the workspace links. | The logo no longer opening the main workspace. |
| AC6-X3 | AC6 | Cross-cutting | API | A caller can confirm its event arrived. | An accepted event. | Post the event. | One log line naming the type and recipient. | — |
| AC6-X4 | AC6 | Cross-cutting | Repository | Supabase keys are sent the way Supabase expects. | Legacy JWT and new secret key formats. | Build the request. | Correct headers for each format. | A key sent in the wrong header. |

## Latest execution record

Run on 5 October 2026 on commit `ff62c8c` (branch `feat/submission-confirmation`, after merging `origin/dev` at `48b55ae`), by Tate Lim's session with Claude. Dependencies were mocked or faked in every automated layer.

| ID | Automation status | Actual result | Execution status | Remarks and evidence |
| --- | --- | --- | --- | --- |
| AC1-H1 | Automated, 5 tests | All passed. | Pass | Red phase unavailable: written before the testing standard. |
| AC1-H2 | Automated, 3 tests | All passed. | Pass | As above. |
| AC1-N1 | Automated, 4 tests | All passed. | Pass | Retry while notificationService is down is covered by unit tests only. |
| AC1-N2 | Automated, 3 tests | All passed. | Pass | |
| AC2-H1 | Automated, 5 tests | All passed. | Pass | Red phase unavailable (SCRUM-14 and earlier work). |
| AC2-N1 | Automated, 4 tests | All passed. | Pass | |
| AC3-H1 | Automated, 4 tests | All passed. | Pass | Red seen before the change: backend 11 of 11 new tests failed (`TypeError`, `AttributeError`); frontend 5 of 5 new tests failed. The Playwright journey failed with the clarification case removed. |
| AC3-H2 | Automated, 1 test | Passed. | Pass | |
| AC3-P1, AC3-P2 | Automated, 1 test, 2 cases | Passed. | Pass | A planted "notify on every outcome" bug was caught. |
| AC3-P3 | Automated, 1 test, 3 cases | Passed. | Pass | `shows a clarification request without a detail line when the reason is %j` in `frontend/__tests__/notifications.test.tsx`. |
| AC3-N1 to AC3-N3 | Automated, 1 test, 3 cases | Passed. | Pass | |
| AC3-N4 | Automated, 1 test | Passed. | Pass | |
| AC3-N5, AC3-N6 | Automated, 1 test, 2 cases | Passed. | Pass | A planted "send failure escapes" bug was caught. |
| AC3-N7 | Automated, 1 test | Passed. | Pass | |
| AC6-H1 | Automated, 5 tests | All passed. | Pass | |
| AC6-H2 | Automated, 4 tests | All passed. | Pass | |
| AC6-P1 | Automated, 3 tests | All passed. | Pass | |
| AC6-P2 to AC6-P5 | Automated, 7 tests | All passed. | Pass | |
| AC6-B1 | Automated, 2 tests | All passed. | Pass | **Gap:** the limits 0 and 101 are tested, but not the values at the boundary (1 and 100). |
| AC6-N1 to AC6-N6 | Automated, 21 tests | All passed. | Pass | |
| AC6-X1 to AC6-X4 | Automated, 6 tests | All passed. | Pass | |

### Commands and totals

Counts are test functions per ID (`grep` over the labels); the commands below give the case counts.

| Boundary | Command or environment | Result | Limitation |
| --- | --- | --- | --- |
| eventRequestService | `.venv/bin/pytest -q`; `.venv/bin/ruff check .` | `234 passed`, ruff clean. | Fakes and a stubbed HTTP client; no live Supabase or notificationService. |
| notificationService | `.venv/bin/pytest -q`; `.venv/bin/ruff check .` | `53 passed`, ruff clean. | Fake repository; the two scaffold health tests in `test_main.py` carry no AC. |
| Frontend unit and component | `npm test` | `163 passed` in 20 files. | API calls are mocked at this layer. |
| Frontend static checks and build | `npm run lint`; `npm run typecheck`; `npm run build -- --webpack` | All completed without errors. | Local result only. |
| Browser | `CI=1 npx playwright test` | `22 passed`. | Uses a fake notification API on port 8107 and fake auth, not the live services. |

### Checked earlier, not on this commit

On 2 October 2026 the AC1 relay was run against the shared Supabase project from the working tree before it was committed: 8 backlog rows were delivered and a new test request was confirmed in 3.8 seconds, and marking one notification read took an Organiser from 9 unread to 8. This was not re-run on `ff62c8c`, so treat it as supporting evidence, not current evidence.

### Checked live on 7 October 2026

Run by Tate Lim's session with Claude on `origin/dev` at `ef4b191` (working tree identical to it), with authService (8001), eventRequestService (8003, `NOTIFICATION_SERVICE_URL` set so the relay ran) and notificationService (8005) started locally from their virtual environments against the **shared Supabase project**. The steps were driven over HTTP with the shared test accounts; no browser was used. Before starting, `event_request_outbox` held 0 unpublished rows, so the relay had no backlog to deliver.

| ID | Steps | Actual result | Execution status |
| --- | --- | --- | --- |
| AC1-H1 | `event_organiser@example.com` submitted request `776689b2-2781-4c95-a474-29cd0464d081` (`POST /event-requests/submissions`, 201). | The Organiser's inbox held one `event_request_submitted` notice for that request, delivered by the outbox relay within the 30 s wait. | Pass (live, API) |
| AC2-H1 | `event_operations_manager@example.com` assigned `event_coordinator1@example.com` (`POST /event-requests/{id}/coordinator`, 201). | The Coordinator's inbox held one `coordinator_assigned` notice for that request. | Pass (live, API) |
| AC3-H1 | The Coordinator started review (200, `Under Review`), then recorded `Changes Requested` with a reason (200). | The Organiser's inbox held one `clarification_requested` notice whose payload carried the request id and the exact reason; the Coordinator's inbox held no clarification notice. | Pass (live, API) |

Limitations: one run; the Organiser's inbox *page* was not opened, so the card wording and link were not seen live (that layer is covered by component and browser tests with a fake API); the notice payloads still carry no event name. The run left test rows in the shared project: request `776689b2-2781-4c95-a474-29cd0464d081` (now `Changes Requested`), one coordinator assignment, one published outbox row and three notifications. The script was a throwaway in the session scratchpad and is not committed.

### Not yet verified

| Check | Status | Why and how |
| --- | --- | --- |
| Retry of an AC1 notice while notificationService is down, against the live stack | Not executed | Covered by unit tests only. |
| Pull-request CI and reviewer approval | Not executed | The branch is pushed; the pull request has not been opened from this session. |

## Definition of Done status

- [x] AC1, AC2 and AC3 each have implementation evidence; AC6's in-app, prompt-delivery and relevance rules do too.
- [ ] Scope split on 8 October 2026: AC4, AC5 and the email, per-type setting and grouped-delivery parts of AC6 moved to SCRUM-57, so this story's scope is AC1–AC3 and the in-app, prompt-delivery and relevance parts of AC6. The Product Owner has not confirmed the split.
- [x] Every automated test for AC1–AC3 and AC6 carries an `AC<n>-<letter><k>` label.
- [x] Unit, API, component and browser tests pass; authentication, relationship and forbidden side effects are covered for the inbox and for AC3.
- [x] Lint, type checking and build pass locally.
- [x] Service README and this document are updated.
- [ ] Historical Red-phase output is unavailable for AC1, AC2 and AC6 (written before the testing standard); AC3 has Red and Green evidence.
- [ ] Mutation testing has not been run; three bugs were planted by hand for AC3 only.
- [ ] AI-generated code and tests were reviewed and understood by a human team member.
- [ ] Product Owner approval of the story contract review, and of the 27 September refinement.
- [ ] Pull request reviewed, CI passing, merged to `dev` and running in the integrated stack.

**Status note.** Jira has shown SCRUM-37 as Done since 8 October 2026. The unchecked items above were still open at that time, so this checklist does not by itself show the Definition of Done is met.
