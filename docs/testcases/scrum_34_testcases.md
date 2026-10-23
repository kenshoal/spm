# SCRUM-34 — View Event Registration Information

Source: [Jira SCRUM-34](https://is212g9t4.atlassian.net/browse/SCRUM-34). Branch: `feat/scrum-34-view-registration-info`, base `e429e72` (`dev`).

## Approved contract

As an Event Organiser or Event Coordinator, I want to view appropriate registration information for an event I manage, so that I can monitor participation without accessing unrelated attendee data.

Jaren (story owner) approved the review below on 23 October 2026 ("do it for me"). The rewording is recorded here, not written back to Jira.

| Jira AC | Outcome | Approved wording |
| --- | --- | --- |
| An Event Organiser can view registration information only for events they are permitted to manage. | **Clarify** | **AC1:** Given an event whose `organiser_id` is the caller, when an `event_organiser` requests its registration information, then it is returned. Another organiser's event, including a same-organisation colleague's (SCRUM-39 sharing is read-only and does not extend to attendee data), is reported as not found. |
| An Event Coordinator can view registration information only for events they coordinate. | **Clarify** | **AC2:** Given an event whose latest coordinator assignment is the caller, when an `event_coordinator` requests its registration information, then it is returned. A coordinator who was never assigned, or was reassigned away, is told the event is not found. |
| The view shows each attendee's current registration status and aggregate registered, withdrawn, and available-place counts. | **Clarify, dependency named** | **AC3:** Given a permitted caller, when the information is returned, then it lists every registration for that event only (attendee id, status, registered at; oldest first) and the counts `registered` (status `Registered`), `withdrawn` (status `Withdrawn`) and `places_available` (`capacity − registered`, never below 0; null when capacity is unset). No attendee contact details are returned. |
| Given a user without a permitted relationship to the event, when they request its registration information, then access is refused. | **Keep, clarified** | **AC4:** Given a caller with no session, then 401. Given a caller with neither role, then 403. Given an unknown event, or a role holder without the AC1/AC2 relationship, then 404 `event_not_found`, revealing nothing (`security-and-state.md` §2). |

## Decisions

| # | Decision |
| --- | --- |
| D1 | `GET /event-requests/{id}/registrations` in eventRequestService. Read-only: no migration. |
| D2 | `withdrawn` counts rows with status `Withdrawn`. The table's CHECK allows only `Registered` until SCRUM-22 widens it, so the count is 0 until then and needs no change afterwards. |
| D3 | Attendees are identified by account id only. No table holds attendee names, and the only other identifier, email, is contact data (AC3). Showing names or emails needs a new story (see open questions). |
| D4 | The event may be in any status; non-Confirmed events simply have no registrations. |
| D5 | Registrations are read in pages of 1,000, because the Data API caps a response at 1,000 rows. |

## Scope

- **Included:** AC1 to AC4; the API endpoint; a "Registrations" panel on the coordinator request page and on the organiser's own submitted request page.
- **Excluded:** withdrawal (SCRUM-22), waiting list (SCRUM-24), manual registration (SCRUM-41), attendance (SCRUM-25), exporting or contacting attendees, setting window and capacity.

## Actors and permissions

`event_organiser` with `organiser_id = caller`; `event_coordinator` holding the latest assignment. A caller with both roles is allowed if either relationship holds. Every other role is 403.

## Allowed state

No state changes. The endpoint only reads.

## Persistence and atomicity

None written. `event_registrations` stays service-role only (`0048`); the browser never reads it directly.

## Assumptions and open questions

1. Should organisers and coordinators see attendee names or emails? This needs a profile source and an authService change. It is not in this story (D3).
2. Can a same-organisation colleague (SCRUM-39) see registration counts? Assumed no, matching the registration-review panel, which colleagues don't see.

## Test case specification

Layers: A = API (`backend/eventRequestService/tests/test_registration_info_api.py`), R = repository (`tests/test_registration_repository.py`), C = component (`frontend/__tests__/registration-info.test.tsx`).

| ID | AC | Test scenario | Technique | Pre-conditions | Test steps | Test data | Expected result | Forbidden side effects | Layer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AC1-H1 | AC1, AC3 | The owning organiser sees their event's registrations | Happy | Event owned by `organiser-1`, capacity 10, 3 registered | GET as `organiser-1` with `event_organiser` | — | 200; 3 rows; registered 3, withdrawn 0, places_available 7 | Registrations unchanged | A |
| AC1-N1 | AC1, AC4 | Another organiser's event is hidden | Negative | Event owned by `organiser-1` | GET as `organiser-2` | — | 404 `event_not_found` | No registration data in body | A |
| AC2-H1 | AC2 | The latest-assigned coordinator sees the registrations | Happy | Coordinator C1 assigned | GET as C1 with `event_coordinator` | — | 200 with the rows | — | A |
| AC2-N1 | AC2, AC4 | A coordinator never assigned is refused | Negative | C1 assigned | GET as C2 | — | 404 `event_not_found` | — | A |
| AC2-N2 | AC2, AC4 | A coordinator reassigned away is refused | Negative | C1 then C2 assigned | GET as C1 | — | 404 `event_not_found` | — | A |
| AC2-X1 | AC1, AC2 | A caller holding both roles is allowed through either relationship | Cross-cutting | C1 assigned; event owned by someone else | GET as C1 with both roles | — | 200 | — | A |
| AC3-H1 | AC3 | Rows hold exactly id, attendee id, status, registered at, oldest first; no other event's rows | Happy | Two events, registrations at different times | GET for the first event | — | Keys exactly `id, attendee_id, status, created_at`; ordered by `created_at`; second event's rows absent | — | A |
| AC3-H2 | AC3 | An event with no registrations is a valid empty result | Happy | Planning event, capacity unset | GET | — | 200, `registrations` [], registered 0, withdrawn 0, places_available null | — | A + C |
| AC3-P1 | AC3 | Each status lands in its own count | Partition | 2 `Registered`, 1 `Withdrawn` (seeded in the fake ahead of SCRUM-22) | GET | — | registered 2, withdrawn 1, places_available 8; 3 rows listed | — | A |
| AC3-B1 | AC3 | One place left | Boundary | capacity 5, 4 registered | GET | — | places_available 1 | — | A |
| AC3-B2 | AC3 | Exactly full | Boundary | capacity 5, 5 registered | GET | — | places_available 0 | — | A |
| AC3-B3 | AC3 | Capacity unset | Boundary | capacity null, 0 registered | GET | — | places_available null | — | A |
| AC3-X1 | AC3 | All registrations are read past the 1,000-row page cap | Cross-cutting | Data API returns 1,000 rows then 1 | `list_for_event` | — | 1,001 rows; second request uses offset 1000 | — | R |
| AC3-X2 | AC3 | The panel shows counts and each row's status and date | Cross-cutting | Info with 2 rows | Render the panel | — | Counts and rows visible; empty state when no rows | — | C |
| AC4-N1 | AC4 | No session | Negative | — | GET without Authorization | — | 401 | — | A |
| AC4-P1…P5 | AC4 | Every other role is refused | Partition | Event exists | GET with the role | attendee, technical_support, venue_staff, event_operations_manager, admin | 403 | — | A |
| AC4-N2 | AC4 | Unknown event | Negative | Empty repository | GET a random uuid | — | 404 `event_not_found` | — | A |
| AC4-N3 | AC4 | Supabase unavailable | Negative | Repository raises `SupabaseRepositoryError` | GET | — | 502 (the service's existing Supabase-unavailable mapping) | — | A |
| AC4-N4 | AC4 | The panel reports a load failure without breaking the page | Negative | Loader throws | Render the panel | — | Alert "temporarily unavailable" | — | C |

## Latest execution record

| ID | Automation status | Actual result | Execution status | Build or commit | Executed by and date | Remarks and evidence |
| --- | --- | --- | --- | --- | --- | --- |
| AC1-H1 … AC4-N3 (API, 20 cases incl. parametrized) | Green | As expected | Pass | `ec113ec`, local Windows, Python 3.14, faked repositories | Claude for Jaren, 23 Oct 2026 | Red first: route missing (plain 404 Not Found). `pytest tests/test_registration_info_api.py`: 20 passed |
| AC3-X1 | Green | 2 requests, offsets 0 and 1000, 1,001 rows | Pass | `ec113ec`, local, `httpx.MockTransport` | Claude for Jaren, 23 Oct 2026 | Fails with the repository change stashed. Full service suite `pytest`: 773 passed, 1 skipped; `ruff check .` clean |
| AC3-H2, AC3-X2, AC4-N4 (component) | Green | As expected | Pass | Frontend commit on this branch, local, `getRegistrationInfo` mocked | Claude for Jaren, 23 Oct 2026 | Panel written before its tests (not test-first); planting two faults made all 3 fail. `npm test`: 494 passed; lint, typecheck, build clean |
| Browser journey | Planned | — | Blocked | — | — | No local Supabase credentials (`backend/eventRequestService/.env` absent), so the API cannot serve real data. Needs a run against the shared database with seeded registrations |
| Real Data API contract (`list_for_event`, `get_event_access`) | Planned | — | Not executed | — | — | Mocked only; confirm against the shared database alongside the browser journey |

Test design was AI-drafted; a team member still needs to review it (`testing.md` §10).
