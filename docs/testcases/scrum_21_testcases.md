# SCRUM-21 — Register for a Confirmed Event

Source: [Jira SCRUM-21](https://is212g9t4.atlassian.net/browse/SCRUM-21) and `docs/superpowers/plans/2026-10-17-scrum-21-register-for-event.md`. Branch: `feat/scrum-21-register-for-event`, base `0846c22`.

## Approved contract

As an Attendee, I want to register for a confirmed event, so that my place is recorded.

The AC wording and decisions D1 to D9 below are the proposals in the implementation plan. Yang (story owner) asked for the plan to be implemented on 18 October 2026, and they were built as written. **D3, D5 and D8 still need Product Owner confirmation** (plan §8). The rewording is recorded here, not written back to Jira.

| Jira AC | Outcome | Approved wording |
| --- | --- | --- |
| An Attendee can view the event information appropriate for external users before registering. | **Clarify** | **AC1:** Given a Confirmed event, when an Attendee opens it, then they see its public details (D4) and places remaining. Internal planning data is never returned, and an event that isn't Confirmed is reported as not found. |
| Registration is only possible for a confirmed event within its open registration period. | **Split** | **AC2:** Given an event that isn't Confirmed, when an Attendee tries to register, then they are refused and no registration is stored. |
| Registration attempted outside the open period is not permitted. | **Merge** | **AC3:** Given a Confirmed event, when an Attendee registers before the window opens, at or after it closes, or when no window is set, then they are refused with the reason and nothing is stored (D3). |
| Given an event at full capacity, when an Attendee attempts to register, then registration is refused. | **Keep, clarified** | **AC4:** Given a Confirmed, open event whose active registrations equal its capacity, when an Attendee registers, then they are refused as full and the count is unchanged. Two attendees racing for the last place: exactly one succeeds. |
| Given a successful registration, when confirmed, then the Attendee's place is recorded and they can view their registration. | **Keep, clarified** | **AC5:** Given a Confirmed, open, not-full event, when an Attendee registers, then one registration is stored for them with status `Registered`, the response includes the event's public details, and they can list their own registrations (and no one else's). |

Cross-cutting: only the `attendee` role registers. Other roles get 403, no session gets 401, and the browser roles cannot call the DB function or read the table.

## Decisions

| # | Decision |
| --- | --- |
| D1 | Built in eventRequestService. |
| D2 | `registration_opens_at`, `registration_closes_at` (closes > opens) and `registration_capacity` (> 0), nullable, on `event_requests`. The coordinator screen to set them is a separate, not yet existing story. |
| D3 | Open from `registration_opens_at` (inclusive) until `registration_closes_at` (exclusive). Null window or null capacity = not open. **Needs PO confirmation.** |
| D4 | Public fields: `id, event_name, purpose, description, proposed_date_times, registration_opens_at, registration_closes_at, registration_capacity, places_remaining`. |
| D5 | One active registration per attendee per event; a second attempt is 409 `already_registered`. **Needs PO confirmation.** |
| D6 | A registration stores only the attendee's account id and timestamp. |
| D7 | Viewing or registering for a non-Confirmed event is 404. |
| D8 | `GET /attendee/events` lists Confirmed events with an open window. **Needs PO confirmation.** |
| D9 | `get_now()` dependency returns aware UTC; the DB function takes `p_now`. |

## Scope

- **Included:** AC1 to AC5. Endpoints `GET /attendee/events`, `GET /attendee/events/{id}`, `POST /attendee/events/{id}/registrations`, `GET /attendee/registrations`.
- **Excluded:** setting the window and capacity (new story), withdrawal (SCRUM-22), waiting list (SCRUM-24), notifications (SCRUM-38), manual registration (SCRUM-41), registration info (SCRUM-34), confirming an event (SCRUM-60), the frontend page (increment 2). The existing `GET /event-requests/public-events` (SCRUM-33 view of Confirmed and Completed events) is left unchanged.

## Actors and permissions

Only a caller with the `attendee` role. A registration belongs to its attendee; the list endpoint returns only the caller's own.

## Allowed state

An event is registrable only while `status = 'Confirmed'` and `registration_opens_at <= now < registration_closes_at` and active registrations < `registration_capacity`.

## Persistence and atomicity

`register_for_event` (migration `0029_event_registrations.sql`) locks the event row `FOR UPDATE`, checks status, window, duplicate and capacity, then inserts. A refusal writes nothing. The function is `service_role` only; `event_registrations` has RLS on and no browser policies.

## Assumptions and open questions

1. D3, D5, D8 need PO confirmation.
2. Who owns the "set window and capacity" story? Until it exists, live tests need SQL-seeded values.
3. Capacity versus venue `max_capacity` (Q&A #99) is for the setter story.
4. Add the SCRUM-60 to SCRUM-21 "blocks" link in Jira.

## Test case specification

Layers: U = unit (`tests/test_registration_rules.py`), A = API (`tests/test_registration_api.py`), R = repository (`tests/test_registration_repository.py`), D = DB (`database/verify_event_registrations.sql`, `database/verify_event_registrations_race.sh`). AC4-N2, AC5-N3 and the repository rows were added during the build; they add no new behaviour beyond the approved ACs.

| ID | AC | Test scenario | Technique | Pre-conditions | Test steps | Test data | Expected result | Forbidden side effects | Layer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AC1-H1 | AC1 | Attendee views a Confirmed event | Happy | Confirmed event, capacity 10, 3 registered, open window | GET `/attendee/events/{id}` as an attendee | — | 200, D4 fields, `places_remaining` 7 | — | A |
| AC1-H2 | AC1 | List shows only Confirmed events with an open window | Happy | Open Confirmed, closed Confirmed, not-yet-open Confirmed, Planning | GET `/attendee/events` | — | Only the open Confirmed event | — | A |
| AC1-X1 | AC1 | No internal field leaks | Cross-cutting | Confirmed event with organiser, venue, equipment and accessibility data | GET the event; call `to_public_event` | — | Keys equal the D4 whitelist exactly | — | U + A |
| AC1-P1…P9 | AC1 | Each non-Confirmed status is not visible | Partition | Event in the given status | GET `/attendee/events/{id}` | Draft, Submitted, Under Review, Changes Requested, Rejected, Approved, Planning, Completed, Cancelled | 404 | — | A |
| AC1-N1 | AC1 | Unknown id | Negative | Empty repository | GET `/attendee/events/{random}` | — | 404 | — | A |
| AC2-H1 | AC2 | Register for a Confirmed, open, not-full event | Happy | As AC1-H1 | POST `/attendee/events/{id}/registrations` | — | 201 | — | A |
| AC2-P1…P9 | AC2 | Register for each non-Confirmed status | Partition | Event in the given status, open window | POST registration | the nine statuses | 404 | No registration row | U + A |
| AC2-X1 | AC2 | Event cancelled between view and register | Negative | Event Cancelled after being Confirmed | Call `register_for_event` | — | `P0002` | No row | D |
| AC3-B1 | AC3 | 1 s before `opens_at` | Boundary | Confirmed, capacity free | `check_registration(now = opens - 1 s)` | — | `RegistrationNotOpenError` | — | U |
| AC3-B2 | AC3 | Exactly at `opens_at` | Boundary | as above | now = opens | — | allowed | — | U |
| AC3-B3 | AC3 | 1 s after `opens_at` | Boundary | as above | now = opens + 1 s | — | allowed | — | U |
| AC3-B4 | AC3 | 1 s before `closes_at` | Boundary | as above | now = closes - 1 s | — | allowed | — | U |
| AC3-B5 | AC3 | Exactly at `closes_at` | Boundary | as above | now = closes | — | `RegistrationNotOpenError` (D3) | — | U |
| AC3-B6 | AC3 | 1 s after `closes_at` | Boundary | as above | now = closes + 1 s | — | `RegistrationNotOpenError` | — | U |
| AC3-N1 | AC3 | Window not set | Negative | Confirmed, null window | check; POST registration | — | `RegistrationNotOpenError`; 409 `registration_not_open` | No row | U + A |
| AC3-N2 | AC3 | API refusal before the window | Negative | Confirmed, opens in the future | POST registration | — | 409 `registration_not_open` | No row | A |
| AC3-X1 | AC3 | The rule uses the injected clock | Cross-cutting | Window 1 to 31 Jan 2030 | Same event, two non-default `now` values | — | Result follows `now` | — | U |
| AC4-B1 | AC4 | capacity - 1 registered | Boundary | capacity 5, 4 registered | check; POST | — | allowed; 201 | — | U + A |
| AC4-B2 | AC4 | registered = capacity | Boundary | capacity 5, 5 registered | check; POST | — | `EventFullError`; 409 `event_full` | Count stays 5 | U + A |
| AC4-B3 | AC4 | Capacity 1, first registrant | Boundary | capacity 1, 0 registered | check; `places_remaining` after | — | allowed; then 0 | — | U |
| AC4-N1 | AC4 | Capacity not set | Negative | Confirmed, open window, null capacity | check | — | `RegistrationNotOpenError` | — | U |
| AC4-X1 | AC4 | Two sessions race for the last place | Cross-cutting | capacity 1, 0 registered, two `psql` sessions | Both call `register_for_event` | — | Exactly one row; the other gets `P0004 event full` | Never two rows | D |
| AC5-H1 | AC5 | Successful registration is stored and returned | Happy | As AC1-H1 | POST registration | — | 201; body has registration and public event; row has attendee, event, `Registered`, `created_at` | — | A + D |
| AC5-H2 | AC5 | Attendee lists own registrations | Happy | Attendee A registered for two events | GET `/attendee/registrations` as A | — | Only A's, newest first | — | A |
| AC5-N1 | AC5 | Another attendee's registrations are not shown | Negative | A registered | GET as B | — | Empty list | — | A |
| AC5-N2 | AC5 | Duplicate registration (D5) | Negative | A already registered | POST again | — | 409 `already_registered` | Still one row | A + D |
| AC5-X1 | AC5 | Other roles cannot register, and cannot call the three read endpoints either | Cross-cutting | Open event | POST as organiser, coordinator, operations manager; GET the three read endpoints as organiser and coordinator | `event_organiser`; `event_coordinator`; `event_operations_manager` | 403 | No row | A |
| AC5-X2 | AC5 | No session | Cross-cutting | Real auth dependency | Each of the four endpoints with no header | — | 401 | — | A |
| AC5-X3 | AC5 | Browser roles cannot reach the function or table | Cross-cutting | Local cluster with `0029` | `has_function_privilege`, `has_table_privilege` | `anon`, `authenticated` | false; `service_role` can execute | — | D |
| AC4-N2 | AC4 | The database refusal wins when the last place is taken between the pre-check and the write | Negative | Pre-check read says a place is free, the table already holds the last registration | POST registration | capacity 1, 1 registered | 409 `event_full` | Still one row | A |
| AC4-N2 | AC4 | A database refusal carries its SQLSTATE and message (`P0002`, `P0004` x3) | Negative | Mocked Supabase RPC | `register` | the four refusals | `RegistrationRpcError` with `errcode` and `reason` | — | R |
| AC5-N3 | AC5 | A Supabase outage is a 502 / repository error, never a refusal or a success | Negative | Repository raises `SupabaseRepositoryError`; mocked 500/503; network error | POST registration; `register` | — | 502; `SupabaseRepositoryError` (not `RegistrationRpcError`) | No row | A + R |
| AC1-X1 | AC1 | The event query selects no internal columns | Cross-cutting | Mocked Supabase | `get_event` | — | `select` equals the public-view columns | — | R |
| AC5-H1 / AC5-H2 | AC5 | The RPC payload and the attendee list query are correct | Happy | Mocked Supabase | `register`; `list_for_attendee` | — | RPC body has event, attendee, `p_now`; list filtered by attendee, newest first | — | R |
| AC4-B2 / AC4-B3 | AC4 | Only `Registered` rows are counted, per event; zero when none | Boundary | Mocked Supabase | `count_active_for_events` | — | `{e1: 2, e2: 1, e3: 0}`; empty id list makes no call | — | R |

## Latest execution record

| ID | Automation status | Actual result | Execution status | Build or commit | Executed by and date | Remarks and evidence |
| --- | --- | --- | --- | --- | --- | --- |
| AC1-X1, AC2-P1…P9, AC3-B1…B6, AC3-N1, AC3-X1, AC4-B1…B3, AC4-N1 (unit) | Green | 27 passed | Pass | branch on `0846c22`, local | Claude for Yang, 18 Oct 2026 | `tests/test_registration_rules.py`. Red before: 27 failed with `NotImplementedError`. Mutations (closes inclusive, opens exclusive, capacity `>`) each fail the intended tests |
| AC1-H1/H2/X1/P1…P9/N1, AC2-H1/P1…P9, AC3-N1/N2/B5, AC4-B1/B2/N2, AC5-H1/H2/N1/N2/N3/X1/X2 (API) | Green | 43 passed (4 of them parametrised over endpoints/roles) | Pass | as above, repository faked | Claude for Yang, 18 Oct 2026 | `tests/test_registration_api.py`. Red before: 41 failed, all FastAPI route-level 404 |
| Repository rows | Green | 12 passed | Pass | as above, mocked Supabase transport | Claude for Yang, 18 Oct 2026 | `tests/test_registration_repository.py` |
| AC5-H1, AC5-N2, AC3-B1…B6, AC3-N1, AC4-B1/B2/N1, AC2-X1, AC5-X3 (DB) | Green | `ALL EVENT REGISTRATION VERIFICATIONS PASSED`; re-running 0029 is safe | Pass | **disposable local PostgreSQL 16** built by `database/tests/bootstrap_event_status_history.py` + `0026` + `0029` | Claude for Yang, 18 Oct 2026 | `psql -f database/verify_event_registrations.sql`. Red before `0029`: `type "public.event_registrations" does not exist`. Not run on shared Supabase (`0029` not applied there) |
| AC4-X1 (DB race) | Green | `RACE VERIFICATION PASSED`: one row stored, the second session refused with `event full` | Pass | as above | Claude for Yang, 18 Oct 2026 | `database/verify_event_registrations_race.sh`; leaves one Cancelled fixture event behind (status history is immutable) |
| Whole service | Green | `pytest -q`: 422 passed (340 before the story); `ruff check .`: clean | Pass | local | Claude for Yang, 18 Oct 2026 | Not run: PR CI, shared-database checks, browser (no frontend in this increment) |

Still open: PO confirmation of D3, D5 and D8; teammate review of these AI-drafted cases (`testing.md` §10); applying `0029` to shared development; increment 2 (frontend and Playwright journey) after SCRUM-60.
