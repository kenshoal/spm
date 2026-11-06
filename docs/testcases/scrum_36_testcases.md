# SCRUM-36 — Notify Decision Outcomes

Source: issue tracker SCRUM-36, read 23 October 2026. Branch: `feat/scrum-36-decision-outcomes`, base `dev` at `e429e72`+ (fast-forwarded 23 Oct).

## Approved contract

As a user responsible for an event request or venue booking, I want to be notified when it reaches a decision, so that I know the outcome without chasing another staff member.

The story owner (Tate) reviewed the four issue tracker ACs and approved the review below on 23 October 2026. The issue tracker wording is kept; the rewording below is recorded here, not written back to the issue tracker.

| issue tracker AC | Outcome | Approved wording |
| --- | --- | --- |
| Request approved, rejected or returned for clarification → the Organiser is notified. | **Narrow** | **AC1:** Given a Coordinator records an Approved or Rejected decision on an event request, when the decision is saved, then the request's Organiser receives `event_request_approved` or `event_request_rejected` (the rejection carries the reason). "Returned for clarification" is already delivered by SCRUM-37 (`clarification_requested`) and is not rebuilt. |
| Venue booking approved or rejected → the responsible Coordinator (and Organiser where relevant) is notified. | **Clarify** | **AC2:** Given Venue Staff reject a booking request, when the decision is saved, then the Organiser of the booking's event also receives `venue_booking_rejected` (venue, dates, reason, suggested alternative). An approval notifies the Coordinator only, as today. "Where relevant" is read as: the Organiser is told when the outcome can change their plans (a rejection), not on every approval (decided by the story owner, 23 Oct — option B). The Coordinator notice (SCRUM-15 AC4) is unchanged. |
| Event confirmed → the Organiser is notified. | **Keep** | **AC3:** Given the Safety Officer approves an event in Safety Review, when the event becomes Confirmed, then the Organiser receives `event_confirmed`. |
| Channel / batch / relevance rules (email per type, batches at a configurable frequency, role-relevance). | **Move** | **Out of this story's build, pending the Product Owner.** Needs an email provider that does not exist in the repo; shared with SCRUM-38 and SCRUM-57. To be asked of the PO (Heng Rui); not yet sent. In-app delivery and the existing role-and-event relevance rule from SCRUM-37 are unchanged. |

## Scope

- **Included:** AC1, AC2, AC3 as worded above, with an inbox line for each new notification type.
- **Excluded:** email, batching and per-type settings (AC4, awaiting the PO); `clarification_requested` (SCRUM-37, done); notices for registration or event changes (SCRUM-38, SCRUM-35); the Organiser seeing venue approvals; a durable retry queue (SCRUM-57 engineering item).

## Actors and permissions

- The assigned Coordinator records the Approved / Rejected decision (existing rule, SCRUM-17). Venue Staff decide booking requests (SCRUM-15). The Safety Officer approves (SCRUM-60). This story adds no new permission.
- Recipient is the event request's `organiser_id`. Nobody else receives the new notices; the Coordinator keeps the existing booking notice.

## Allowed state transitions

None added.

## Persistence and atomicity

No new persistence. Every notice is best-effort and sent only **after** the decision is saved: a refused decision tells nobody anything, and a failed or unreachable notification service is logged and never fails or undoes the decision (same rule as `clarification_requested`).

## Assumptions and open questions

1. **How venueService finds the Organiser (AC2) — open.** `EventRequestClient` reaches eventRequestService with the *caller's* token, and Venue Staff may not read an event, so it cannot be used. Options: (a) venueService reads `event_requests.organiser_id` from Supabase with the service key it already holds for bookings; (b) eventRequestService exposes a service-to-service lookup; (c) notificationService resolves the Organiser from `event_request_id`. Decided: (a) (Tate, 23 Oct). The live table has `event_requests.organiser_id` (uuid), checked read-only.
2. A rejected booking whose Organiser cannot be found still notifies the Coordinator and still saves the decision.
3. Notice keys (`event_id`) are derived from the request or booking id and the type, so an accidental repeat is stored once. A request can be approved only once, so there is no legitimate second notice.
4. Event Coordinator Lead and Organiser are the only people told; Safety Officer and Venue Staff are not.

## Test case specification

| ID | AC | Test scenario | Technique | Pre-conditions | Test steps | Test data | Expected result | Forbidden side effects | Layer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AC1-H1 | AC1 | Approving a request tells its Organiser | Happy | Request Under Review, assigned to `coord-1` | `coord-1` POSTs decision Approved | — | 200; Organiser gets `event_request_approved` with `event_request_id` | Nothing sent to anyone else | API + service |
| AC1-H2 | AC1 | Rejecting a request tells its Organiser the reason | Happy | As AC1-H1 | POST decision Rejected with reason | reason text | 200; Organiser gets `event_request_rejected` with `event_request_id`, `reason` | — | API + service |
| AC1-P1 | AC1 | Returning for clarification sends no approved or rejected notice | Partition | As AC1-H1 | POST decision Changes Requested | reason text | Only `notify_clarification_requested` fires | No approved / rejected notice | API + service |
| AC1-N1 | AC1 | A refused decision tells nobody (not assigned, wrong status, missing reason) | Negative | Not-assigned coordinator; request not Under Review; rejection with no reason | POST each | — | 403 / 409 / 422; status unchanged | No notice | API + service |
| AC1-N2 | AC1 | An unreachable notification service does not block the decision | Negative | Real client, `httpx.post` raises | POST Approved | — | 200; status Approved | Decision not rolled back | API |
| AC1-H3 | AC1 | The client posts the agreed shape for approved and rejected | Happy | URL configured | Call client methods | — | `event_type`, `recipient_id` = Organiser, payload, stable `event_id` | — | Client |
| AC1-N3 | AC1 | A network failure or error response is logged, never raised | Negative | `httpx.post` raises / returns 500 | Call client | — | No exception; warning logged | — | Client |
| AC1-N4 | AC1 | With no service configured nothing is attempted | Negative | `NotificationClient(None)` | Call client | — | No HTTP call | — | Client |
| AC1-H4 | AC1 | The Organiser's inbox explains each outcome and links to the request | Happy | Notification of each type | `describeNotification` | — | Plain sentence, rejection shows reason, link to the request | — | UI (unit) |
| AC1-N5 | AC1 | A missing request id gives no guessed link and a blank reason no empty detail | Negative | Notice without `event_request_id`, reason `"   "` | `describeNotification` | — | No link, no detail line | — | UI (unit) |
| AC2-H1 | AC2 | A rejected booking also tells the Organiser | Happy | Pending booking for an event whose Organiser is known | Venue Staff reject with reason | reason, suggested alternative | Coordinator gets `venue_booking_rejected` as today; Organiser gets `venue_booking_rejected` with venue, dates, reason, alternative | — | API |
| AC2-P1 | AC2 | An approved booking tells the Coordinator only | Partition | As AC2-H1 | Venue Staff approve | — | Coordinator notified as today | Organiser gets nothing | API |
| AC2-N1 | AC2 | If the Organiser cannot be found, the decision is saved and the Coordinator is still told | Negative | Organiser lookup fails | Venue Staff reject | — | 200; Coordinator notice sent | No error to Venue Staff | API |
| AC2-N2 | AC2 | A refused approval sends nothing to anyone | Negative | Conflict makes approval refuse | Venue Staff approve | — | 409 | No notice to Coordinator or Organiser | API |
| AC2-X1 | AC2 | The Coordinator notice is unchanged (type, recipient, payload, key) | Cross-cutting | Existing `test_booking_notifications` | Run | — | Existing tests pass untouched | — | API |
| AC2-H2 | AC2 | The Organiser's inbox names the refused venue and links to their own request page (the Coordinator's link would not open for them) | Happy | `venue_booking_rejected`, roles `event_organiser` | `describeNotification` | event, venue, reason, alternative | "A venue for your event Open day was rejected."; link `/event-requests/{id}/edit`; detail has venue, reason, alternative | No link to the Coordinator view | UI (unit) |
| AC2-N3 | AC2 | A notification outage on the Organiser's notice does not undo the decision | Negative | Notifier posts to an unreachable service | Venue Staff reject | — | 200; booking is rejected | Decision not rolled back | API |
| AC2-H3 | AC2 | The Supabase lookup reads only `organiser_id` of the one event request | Happy | Mock transport | `organiser_of(id)` | valid uuid | GET `/rest/v1/event_requests?id=eq.<id>&select=organiser_id` | No other column or row | Unit |
| AC2-N4 | AC2 | An unknown event or malformed id gives no Organiser; a store error is reported as a lookup error | Negative | Empty result / 500 / `not-a-uuid` | `organiser_of(id)` | — | `None` / `None` / `OrganiserLookupError` | No guess | Unit |
| AC2-X2 | AC2 | The Coordinator's wording and link are unchanged, also for someone who is both Organiser and Coordinator | Cross-cutting | roles include `event_coordinator` | `describeNotification` | — | Existing text and `/coordination/requests/{id}` | — | UI (unit) |
| AC3-H1 | AC3 | Safety approval tells the Organiser the event is confirmed | Happy | Request in Safety Review | Safety Officer approves | — | 200, status Confirmed; Organiser gets `event_confirmed` | Coordinator gets nothing new | API + service |
| AC3-N1 | AC3 | Safety "changes requested" sends no confirmed notice | Negative | As AC3-H1 | Decision changes_requested | reason | Only the existing coordinator notice | No `event_confirmed` | API + service |
| AC3-N2 | AC3 | A refused or repeated approval sends no confirmed notice | Negative | Request not in Safety Review; repeated approval | Approve | — | 409 | No notice | API + service |
| AC3-N3 | AC3 | An unreachable notification service does not block confirmation | Negative | Real client, `httpx.post` raises | Approve | — | 200; Confirmed | Not rolled back | API |
| AC3-H2 | AC3 | The client posts the agreed shape | Happy | URL configured | Call client | — | `event_confirmed`, `recipient_id` = Organiser, stable `event_id` | — | Client |
| AC3-H3 | AC3 | The Organiser's inbox line for a confirmed event | Happy | `event_confirmed` | `describeNotification` | — | Plain sentence with link | — | UI (unit) |

## Latest execution record

| ID | Automation status | Actual result | Execution status | Build or commit | Executed by and date | Remarks and evidence |
| --- | --- | --- | --- | --- | --- | --- |
| AC1-H1…H3, N1…N4, P1 | Green | `eventRequestService`: 764 → 772 passed, 1 skipped after AC3; focused file 12 passed | Pass (local) | `f1ff2db` (base `dev` e429e72) | Claude with Tate, 23 Oct 2026 | `tests/test_decision_outcome_notification.py`. Run: `.venv/bin/python -m pytest`, `ruff check .` clean. Two older spies (`test_clarification_notification.py`, `test_safety_review.py`) gained no-op methods for the new notices |
| AC1-H4, N5, AC2-H2, X2, AC3-H3 | Green | Frontend 497 passed (61 files); lint and typecheck clean | Pass (local) | `4c05ed6` | Claude with Tate, 23 Oct 2026 | `frontend/__tests__/decision-outcome-notification.test.ts`. Mocked inbox text only; no browser check |
| AC2-H1, P1, N1…N4, H3 | Green | `venueService`: 617 passed; ruff clean | Pass (local) | `cbffaf4` | Claude with Tate, 23 Oct 2026 | `tests/test_organiser_rejection_notification.py`. Run with eventRequestService's virtualenv (venueService has none), so not its own pinned environment. Live check: `event_requests.organiser_id` and `venue_booking_requests.event_request_id` exist (read-only query, 23 Oct) |
| AC3-H1, H2, N1…N3 | Green | See the eventRequestService line above | Pass (local) | `f1ff2db` | Claude with Tate, 23 Oct 2026 | `tests/test_event_confirmed_notification.py` |
| All | — | — | **Not run:** shared-database check of the Organiser lookup, real-app check of the three notices, CI | — | — | AC4 (email/batching) awaits the PO: question posted in Agents Discussion (msg 2656), no answer yet |
