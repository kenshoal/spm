# SCRUM-38 — Notify Registration Updates

Source: [Jira SCRUM-38](https://is212g9t4.atlassian.net/browse/SCRUM-38), description updated 23 October 2026. Branch: `feat/scrum-38-registration-notices`, based on `dev` (SCRUM-36 merged as PR #93; `dev` merged in on 25 Oct, commit `038a020`).

## Approved contract

As an Attendee or event manager, I want to be notified of registration updates relevant to me, so that I understand my registration status and the event's available capacity.

The story owner (Tate) reviewed the five Jira ACs and approved the review below on 23 October 2026. The agreed wording is already in the Jira description. The PO's reply on the channel rules (via hr_agent, 23 Oct, quoting discussions #37 and #55) was checked against both discussions.

| Jira AC | Outcome | Approved wording |
| --- | --- | --- |
| Attendee registers or withdraws → confirmation of the new status. | **Split** | **AC1:** Given an Attendee registers for a Confirmed event, when the registration is saved, then the Attendee receives `registration_confirmed` (event name, status Registered). The confirmation of a **withdrawal** is SCRUM-22's `registration_withdrawn` (Yang) and is not built here. |
| Final place taken → Organiser and Coordinator notified. | **Keep** | **AC2:** Given a registration takes the last place, when it is saved, then the Organiser and the assigned Coordinator each receive `registration_full`, once for that registration. |
| Registration opens or closes → Organiser and Coordinator notified. | **Keep, built on the shared runner** | **AC3:** Given a Confirmed event's registration opening or closing time has been reached within the lookback (default 72 h), when the periodic pass runs, then the Organiser and the assigned Coordinator each receive `registration_opened` or `registration_closed`, once per boundary time. Heng Rui's `PeriodicTaskRunner` (SCRUM-40, on `dev`) only supplies the timer; the rules are this story's. |
| Event change or cancellation → registered Attendees notified. | **Keep** | **AC4:** Given an event is cancelled, or an approved change to its **dates** is applied, when that is saved, then every registered Attendee receives `event_cancelled` or `event_changed` (with the new dates). Other approved changes (attendance, venue, equipment) are not visible to Attendees and notify none. |
| Channel / batch / relevance rules. | **Narrow** | **AC5:** in-app now, to people whose role and relationship to the event match. Email and the per-type setting come from SCRUM-57. **Batching dropped** (#55: immediate delivery acceptable); **personal switches not required** (#37: configuration by type only). |

## Scope

- **Included now:** AC1, AC2, AC3 and AC4, with an inbox line for each new type.
- **Also covered:** a Coordinator's manual registration (SCRUM-41) sends the same AC1 and AC2 notices, since it is another way to register.
- **Excluded:** withdrawal and waiting-list notices (SCRUM-22, SCRUM-24, Yang); email and channel settings (SCRUM-57); batching and personal switches (dropped); 

## Actors and permissions

- The Attendee is the signed-in user who registers (existing rule, SCRUM-21). The Organiser is `event_requests.organiser_id`. The Coordinator is the **latest** row of `event_coordinator_assignments` for the event (the same rule SCRUM-60 uses). No new permission.
- Recipients: the registering Attendee for AC1; the Organiser and the current Coordinator for AC2. Nobody else.

## Allowed state transitions

None added.

## Persistence and atomicity

No new persistence. Each notice is best-effort and sent only **after** the registration is saved: a refused registration (full, closed, already registered, not visible) tells nobody anything, and a failed or unreachable notification service is logged and never fails or undoes the registration (same rule as SCRUM-36). Keys: `registration-confirmed:<registration id>` and `registration-full:<registration id>` per recipient, so a repeat is stored once, while a place freed by a withdrawal and filled again notifies again.

## Assumptions and open questions

1. "Last place" is when the active registrations equal `registration_capacity` straight after this registration. If a race lets two attendees fill the last place, the database function admits only one, so only one `registration_full` is sent.
2. If no Coordinator is assigned yet, only the Organiser is told (a confirmed event has a Coordinator in practice, so this is a defensive case).
3. `organiser_id` is **not** added to the public event columns (SCRUM-21's test AC1-X1 forbids internal columns there). The registration repository gets two separate lookups instead: `get_organiser_id` and `latest_coordinator_id`.
4. The Attendee id is the Supabase user id (a uuid), the same id the inbox is keyed by.
5. The frontend has no Attendee event page, so the Attendee's inbox line carries no link. Add one when that page exists.
6. **AC4 recipients and cost.** Attendees are the event's active registrations (`event_registrations.status = 'Registered'`). Notices are posted one per Attendee, one after another, inside the request that cancelled or approved: a very large event adds latency to that request (each POST has a 5 s limit), and the database call returns at most 1,000 rows. Fine for the demo data; a queue (SCRUM-57's outbox item) is the real fix.
7. **AC4 trigger for changes.** Only a change to `proposed_date_times` is something an Attendee can see (the public event view shows the dates, not attendance, venue or equipment), so only that notifies. This is a reading of "affects registered Attendees"; tell me if the PO wants every approved change to notify.
8. **AC3 design.** The handler keeps no table of what it has sent. Every notice carries a key built from the event, the boundary time and the person, and notificationService stores a repeated key once (`UNIQUE (recipient_id, event_id)` in migration 0017). A missed run is caught up by the next pass if the boundary is still inside the lookback (default 72 h, `REGISTRATION_WINDOW_LOOKBACK_HOURS`); an older boundary is dropped on purpose, so a first start does not announce months-old windows. If the Organiser moves the window, the new time gives a new key and a new notice. It is off unless `REGISTRATION_WINDOW_NOTICES_ENABLED=true` and needs `NOTIFICATION_SERVICE_URL`. A runner outage longer than the lookback loses that boundary's notice.

## Test case specification

| ID | AC | Test scenario | Technique | Pre-conditions | Test steps | Test data | Expected result | Forbidden side effects | Layer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AC1-H1 | AC1 | Registering tells the Attendee, once the registration is saved | Happy | Confirmed event, window open, places left | Attendee POSTs a registration | event name "Community Dinner" | 201; Attendee gets `registration_confirmed` with event id, name, registration id, status | Nobody else is told | API + service |
| AC1-N1 | AC1 | A refused registration tells nobody (full, closed, already registered, not Confirmed) | Negative | Each refusing state | POST | — | 409 / 404 as today | No notice | API + service |
| AC1-N2 | AC1 | An unreachable notification service does not block registration | Negative | Real client, `httpx.post` raises | POST | — | 201; registration stored | Not rolled back | API |
| AC1-H2 | AC1 | The client posts the agreed shape | Happy | URL configured | `notify_registration_confirmed` | — | `event_type`, `recipient_id` = Attendee, stable `event_id`, payload | — | Client |
| AC1-H3 | AC1 | The Attendee's inbox line names the event; there is no link because the frontend has no Attendee event page yet | Happy | `registration_confirmed` | `describeNotification` | event "Community Dinner" | "You're registered for Community Dinner."; `href` null | No guessed link | UI (unit) |
| AC1-N6 | AC1 | A notice without an event name still reads well | Negative | `event_name` null | `describeNotification` | — | "Your registration is confirmed." | — | UI (unit) |
| AC2-H1 | AC2 | The registration that takes the last place tells the Organiser and the Coordinator | Happy | Capacity 10, 9 registered, a Coordinator assigned | Attendee registers | — | `registration_full` to the Organiser and to the Coordinator, each once | Attendee gets only AC1's notice | API + service |
| AC2-B1 | AC2 | One place short of full sends no full notice; the last place sends it | Boundary | Capacity 10; 8 then 9 registered | Register the 9th, then the 10th | — | 9th: no `registration_full`; 10th: sent | — | API + service |
| AC2-N1 | AC2 | A refused registration on a full event sends no full notice | Negative | 10 of 10 | Register an 11th attendee | — | 409 | No notice | API + service |
| AC2-P1 | AC2 | With no Coordinator assigned only the Organiser is told | Partition | Last place, no assignment | Register | — | `registration_full` to the Organiser only | No error | API + service |
| AC2-N2 | AC2 | An unavailable Coordinator lookup does not stop the Organiser's notice or the registration | Negative | Lookup raises | Register the last place | — | 201; Organiser told | Registration not undone | API + service |
| AC2-H2 | AC2 | The client posts the agreed shape for both recipients | Happy | URL configured | `notify_registration_full` | — | `event_type` `registration_full`, per-recipient key, payload with capacity | — | Client |
| AC2-H3 | AC2 | The Organiser's and Coordinator's inbox line | Happy | `registration_full` | `describeNotification` | roles organiser / coordinator | Sentence naming the event; Organiser links to their request page, Coordinator to the coordination page | No link the role cannot open | UI (unit) |
| AC2-X1 | AC2 | The Organiser is fetched by its own one-column query, so the public event columns stay free of internal ones (existing test AC1-X1 of SCRUM-21 still passes) | Cross-cutting | Mock transport | `get_organiser_id` | — | `select=organiser_id` on one event; `organiser_id` not in `EVENT_COLUMNS` | No internal column in any Attendee response | Unit |
| AC2-H4 | AC2 | The Coordinator is the newest assignment row | Happy | Mock transport | `latest_coordinator_id` | — | `event_coordinator_assignments?order=id.desc&limit=1&select=coordinator_id` | — | Unit |
| AC2-P2 | AC2 | An unknown event or an event with no assignment gives `None` | Partition | Empty result | the two lookups | — | `None` | No guess | Unit |

| AC1-H4 | AC1 | A Coordinator registering an Attendee (SCRUM-41) also tells that Attendee | Happy | Assigned Coordinator, attendee account exists | POST `/event-requests/{id}/registrations` | VIP email | 201; `registration_confirmed` for the Attendee | — | API + service |
| AC1-N3 | AC1 | A refused manual registration (unknown email, already registered, full) tells nobody | Negative | Each refusing state | POST | — | 404 / 409; no notice | No notice | API + service |
| AC1-N4 | AC1 | If the event cannot be re-read after a manual registration was saved, the registration stands | Negative | `get_event` raises | POST | — | 201; row stored; no notice | Registration not undone | API + service |
| AC2-H5 | AC2 | A manual registration that takes the last place tells the Organiser and the Coordinator | Happy | Capacity 3, 2 registered | POST | — | `registration_full` for both | — | API + service |
| AC3-H1 | AC3 | Registration that opened inside the lookback tells the Organiser and the Coordinator, naming the boundary time | Happy | Confirmed event, opens 1 h ago | `run_once()` | — | `registration_opened` for both | Nobody else | Service |
| AC3-H2 | AC3 | Registration that closed inside the lookback tells both | Happy | closes 5 min ago | `run_once()` | — | `registration_closed` for both | — | Service |
| AC3-P1 | AC3 | A window that opened and closed inside the lookback sends one notice of each kind per person | Partition | opens 30 h ago, closes 2 h ago | `run_once()` | — | 4 notices | — | Service |
| AC3-B1 | AC3 | A boundary is announced from the moment it is reached until the lookback ends | Boundary | opens now+1 s / now / now−72 h / now−72 h−1 s | `run_once()` | lookback 72 h | 0 / 2 / 2 / 0 notices | Not early, not late | Service |
| AC3-B2 | AC3 | Paging reads every event | Boundary | 5 events, page size 2 | `run_once()` | — | 5 events notified | — | Service |
| AC3-N1 | AC3 | Cancelled events, events with no window and old windows send nothing | Negative | three such events | `run_once()` | — | no notice | — | Service |
| AC3-N2 | AC3 | A Coordinator that cannot be found does not stop the Organiser's notice or other events | Negative | lookup raises for e1 | `run_once()` | — | Organiser told; others unaffected; `failed` = 1 | — | Service |
| AC3-N3 | AC3 | A sender failure for one person is contained | Negative | sender raises for one recipient | `run_once()` | — | rest still sent; `failed` = 1 | — | Service |
| AC3-N4 | AC3 | A clock without a time zone is refused | Negative | naive datetime | `run_once(as_of)` | — | `ValueError` | — | Service |
| AC3-N5 | AC3 | A lookback that is not positive and finite is refused at start-up | Negative | 0, −1, nan, inf | build settings | — | validation error | — | Unit |
| AC3-X1 | AC3 | Passes are repeatable: running twice sends identical notices, so notificationService keeps one copy per person | Cross-cutting | one event | `run_once()` twice | — | same notices both times | No state of its own | Service |
| AC3-X2 | AC3 | The key follows the boundary time: a moved window gets a fresh notice, the same boundary the same key | Cross-cutting | same / different boundary | `notify_registration_window` | — | equal / different keys | — | Client |
| AC3-X3 | AC3 | The database query asks for Confirmed events with a boundary in range, a page at a time | Cross-cutting | Mock transport | `list_window_boundaries` | — | `status=eq.Confirmed`, `or=(...)`, `order=id.asc`, `limit`, `id=gt.<last>` | No internal column | Unit |
| AC3-X4 | AC3 | The notices are off by default, switched on separately from completion, and use the shared runner | Cross-cutting | settings | build runner | — | `None` when off; handler registered when on | — | Unit |
| AC3-H3 | AC3 | The client posts the agreed shape with a key built from the event, boundary and person | Happy | URL configured | `notify_registration_window` | — | `registration_opened` with `boundary_at` | — | Client |
| AC3-H4 | AC3 | The Organiser's inbox line says registration opened or closed, with the time and their own link | Happy | notice per type | `describeNotification` | — | sentence, formatted time, `/event-requests/{id}/edit` | — | UI (unit) |
| AC3-H5 | AC3 | The Coordinator's line links to the coordination page | Happy | role coordinator | `describeNotification` | — | `/coordination/requests/{id}` | — | UI (unit) |
| AC3-N6 | AC3 | A notice without a name or time still reads well, with no empty detail line | Negative | name null, no time | `describeNotification` | — | "Registration for your event has closed." | — | UI (unit) |
| AC4-H1 | AC4 | Cancelling tells every registered Attendee, once the cancellation is saved | Happy | Confirmed event, two active registrations, assigned Coordinator | Coordinator POSTs `/cancellation` | attendees `attendee-1`, `attendee-2` | 200, status Cancelled; `event_cancelled` for both | Nobody else told | API + service |
| AC4-P1 | AC4 | An event nobody registered for sends nothing | Partition | No registrations | Cancel | — | 200; no notice | No empty send | API + service |
| AC4-N1 | AC4 | A refused cancellation (terminal status, not the assigned Coordinator) tells nobody | Negative | Completed event; another Coordinator | Cancel | — | 409 / 403; status unchanged | No notice | API + service |
| AC4-N2 | AC4 | If the Attendees cannot be listed, the cancellation still stands | Negative | Lookup raises | Cancel | — | 200, Cancelled; nothing sent | Cancellation not undone | API + service |
| AC4-H2 | AC4 | An approved change to the dates tells every registered Attendee the new dates | Happy | Planning event, two registrations, pending date change | Coordinator approves | new `proposed_date_times` | 200; `event_changed` with change id and new dates for both | — | API + service |
| AC4-P2 | AC4 | An approved change Attendees cannot see (attendance, venue, equipment) tells them nothing | Partition | Pending non-date change | Approve | `expected_attendance` 80 | 200; no Attendee notice | — | API + service |
| AC4-N3 | AC4 | A rejected change tells no Attendee | Negative | Pending date change | Reject with reason | — | 200; no Attendee notice | — | API + service |
| AC4-N4 | AC4 | An unreachable notification service does not block a cancellation | Negative | Real client, `httpx.post` raises | Cancel | — | 200, Cancelled | Not rolled back | API |
| AC4-H3 | AC4 | The client sends one cancellation notice per Attendee, each with its own stable key | Happy | URL configured | `notify_event_cancelled` | 2 attendees | 2 POSTs, `event_type` `event_cancelled`, key `event-cancelled:<event>:<attendee>` | — | Client |
| AC4-H4 | AC4 | The client sends the new dates to each Attendee, keyed by the change | Happy | URL configured | `notify_event_changed` | 1 attendee | `event_changed` with change id and dates; key `event-changed:<change>:<attendee>` | — | Client |
| AC4-N5 | AC4 | One Attendee's failed notice does not stop the rest | Negative | First POST raises | `notify_event_cancelled` | 2 attendees | Both attempted; failure logged | No exception | Client |
| AC4-X1 | AC4 | The attendee lookup asks for one column of one event's active registrations | Cross-cutting | Mock transport | `list_registered_attendee_ids` | — | `event_registrations?event_request_id=eq.<id>&status=eq.Registered&select=attendee_id` | No other column | Unit |
| AC4-H5 | AC4 | The inbox line for a cancelled event; no link (no Attendee event page) | Happy | `event_cancelled` | `describeNotification` | event name | "Community Dinner has been cancelled."; `href` null | No guessed link | UI (unit) |
| AC4-N7 | AC4 | A cancellation without an event name still reads well | Negative | `event_name` null | `describeNotification` | — | "An event you registered for has been cancelled." | — | UI (unit) |
| AC4-H6 | AC4 | The inbox line for changed dates shows the new dates in the app's usual format | Happy | `event_changed` with two dates | `describeNotification` | — | "The dates of Community Dinner have changed."; detail "New dates: ..." | — | UI (unit) |
| AC4-N8 | AC4 | A date-change notice with no usable dates shows no detail line | Negative | empty list | `describeNotification` | — | Message only | — | UI (unit) |

## Latest execution record

| ID | Automation status | Actual result | Execution status | Build or commit | Executed by and date | Remarks and evidence |
| --- | --- | --- | --- | --- | --- | --- |
| AC1-H1, H2, H4, N1a-d, N2…N4; AC2-H1, B1, N1, P1, N2, H2, H5 | Green | 18 in `tests/test_registration_notification.py`, 4 in `tests/test_registration_repository.py` | Pass (local) | `9216da7`; manual-registration part `a2a9747` | Claude with Tate, 25 Oct 2026 | Fake repository only; the lookups are not run against shared Supabase |
| AC3-H1…H3, P1, B1, B2, N1…N5, X1…X4 | Green | 21 in `tests/test_registration_window_notifier.py`, run with the settings, sender and query tests | Pass (local) | `53b4e7d` | Claude with Tate, 25 Oct 2026 | The query and the runner wiring use a mock transport and a prepared handler. **The handler has not run against shared Supabase or in the running app** |
| AC4-H1…H4, P1, P2, N1…N5 | Green | 12 in `tests/test_attendee_event_notification.py`; AC4-X1 in `tests/test_supabase_repository.py` (written after the code, not before) | Pass (local) | `9216da7` | Claude with Tate, 23 Oct 2026 | Date approval uses the prepared repository result, as in the SCRUM-35 date tests, not the real database function |
| Whole suites | — | `eventRequestService`: 950 passed, 1 skipped, ruff clean. Frontend: 523 passed (66 files), lint and typecheck clean | Pass (local) | AC1/2/4 `9216da7`+`20e8d96`; AC3 `53b4e7d`+`b723417` | Claude with Tate, 25 Oct 2026 | Frontend cases in `frontend/__tests__/registration-notification.test.ts`; mocked inbox text only |
| All | — | — | **Not run:** shared-database check of the two lookups, a real registration in the running app, CI | — | — | withdrawal notice (SCRUM-22) not built by its owner yet |
