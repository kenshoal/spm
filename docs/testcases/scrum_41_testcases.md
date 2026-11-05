# SCRUM-41 — Manually Register an Attendee

Source: [Jira SCRUM-41](https://is212g9t4.atlassian.net/browse/SCRUM-41). Branch: `feat/scrum-41-manual-registration`, stacked on `feat/scrum-34-view-registration-info` (AC3 needs SCRUM-34's view). Retarget to `dev` once SCRUM-34 merges.

## Approved contract

As an Event Coordinator, I want to manually register an attendee who was provided to me by the Event Organiser, so that guests who don't self-register (e.g. VIPs) still hold a confirmed place.

Jaren (story owner) approved the decisions below on 23 October 2026: "the guest must already have an attendee account; coordinator looks them up. Allow adding outside the window, capacity still applies." The rewording is recorded here, not written back to Jira.

| Jira AC | Outcome | Approved wording |
| --- | --- | --- |
| Given attendee details provided by the Event Organiser, the Coordinator can create a registration for that attendee on a confirmed event. | **Clarify** | **AC1:** Given a Confirmed event whose latest coordinator is the caller, and the email of an existing account holding the `attendee` role, when the coordinator registers that email, then one `Registered` registration is stored for that account, even outside the registration window (D2). An unknown email, or one whose account isn't an attendee, is refused as `attendee_not_found` and nothing is stored. |
| Manually added registrations count toward the event's registration capacity the same as self-registrations. | **Keep, clarified** | **AC2:** Given an event whose active registrations equal its capacity, when the coordinator registers an attendee, then it is refused as `event_full` and nothing is stored. A manual registration takes a place that self-registration then can't take. An event with no capacity set is refused as `capacity_not_set`. |
| A manually registered attendee's registration is visible wherever self-registered attendees' registrations are visible (e.g. SCRUM-34's registration view). | **Keep** | **AC3:** Given a manual registration, then it appears in SCRUM-34's registration view and in the attendee's own `GET /attendee/registrations`, exactly as a self-registration does. |
| The registration record indicates it was entered by a Coordinator rather than self-registered, for accountability. | **Keep** | **AC4:** Given a manual registration, then its stored `registered_by` is the coordinator's account id, and a self-registration's is null. SCRUM-34's view returns `registered_by`. |

Cross-cutting: only the `event_coordinator` role may call it (others 403, no session 401). A coordinator who isn't the latest assignee gets 404 `event_not_found`, rechecked inside the locked database function (`security-and-state.md` §1.2). The same attendee can't hold two active registrations (SCRUM-21 D5): 409 `already_registered`.

## Decisions

| # | Decision |
| --- | --- |
| D1 | `POST /event-requests/{id}/registrations` with `{"attendee_email": "..."}`. Email is matched case-insensitively. |
| D2 | No registration-window check for manual registration. Status (Confirmed), duplicate and capacity checks still apply. |
| D3 | Effective attendee role uses authService's precedence (`staff_roles` rows, then `app_metadata.roles`, then `app_metadata.role`, else `attendee`), as `0038` already does in SQL. |
| D4 | Migration `0060_manual_event_registrations.sql`: nullable `registered_by uuid` (no foreign key, like `coordinator_id` in `0011`) and `coordinator_register_attendee(...)`, `SECURITY DEFINER` (it reads `auth.users`), `service_role` only. |
| D5 | Telling a coordinator "no attendee with that email" reveals whether an attendee account exists. This is accepted: only the event's own coordinator can ask, and the organiser supplied the details. |

## Scope

- **Included:** AC1 to AC4; the endpoint; an "Add attendee" form in the coordinator's Registrations panel; an "Added by coordinator" marker in that panel.
- **Excluded:** creating accounts for guests, notifications (SCRUM-38), withdrawal (SCRUM-22), waiting list (SCRUM-24), organisers adding attendees themselves.

## Actors and permissions

The latest-assigned `event_coordinator` only.

## Allowed state

Event `Confirmed`; active registrations < `registration_capacity`; no active registration for that attendee.

## Persistence and atomicity

`coordinator_register_attendee` locks the event row `FOR UPDATE`, rechecks the coordinator assignment, status, attendee, duplicate and capacity, then inserts with `registered_by`. A refusal writes nothing. Refusals: `P0002` 'event not found' / 'attendee not found'; `P0004` 'already registered' / 'event full' / 'capacity not set'.

## Assumptions and open questions

1. Should the attendee be notified that a coordinator registered them? Left to SCRUM-38.

## Test case specification

Layers: A = API (`backend/eventRequestService/tests/test_manual_registration_api.py`), D = DB (`database/verify_manual_event_registrations.sql`), C = component (`frontend/__tests__/manual-registration.test.tsx`).

| ID | AC | Test scenario | Technique | Pre-conditions | Test steps | Test data | Expected result | Forbidden side effects | Layer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AC1-H1 | AC1, AC4 | The assigned coordinator registers an attendee by email | Happy | Confirmed, open, capacity 10; C1 latest coordinator; attendee account | POST as C1 | `attendee_email` of the attendee | 201; row `Registered`, attendee id, `registered_by` C1 | — | A + D |
| AC1-H2 | AC1 | Registration outside the window is allowed (D2) | Happy | Confirmed, window closed | POST / call function | — | 201 / one row | — | A + D |
| AC1-P1 | AC1 | Email match ignores case | Partition | Attendee `vip@test.local` | Call with `VIP@Test.Local` | — | Row for that account | — | D |
| AC1-N1 | AC1 | Unknown email | Negative | No such account | POST | `nobody@test.local` | 404 `attendee_not_found` | No row | A + D |
| AC1-N2 | AC1 | Account isn't an attendee | Negative | Account with only `venue_staff` in `staff_roles` | Call function | — | `P0002 attendee not found` | No row | D |
| AC1-N3 | AC1 | Event isn't Confirmed | Negative | Planning event | Call function | — | `P0002 event not found` | No row | D |
| AC1-N4 | AC1 | Blank or missing email | Negative | — | POST `{}` and `{"attendee_email": "  "}` | — | 422 | Function not called | A |
| AC1-N5 | AC1 | Duplicate registration | Negative | Attendee already registered | POST | — | 409 `already_registered` | Still one row | A + D |
| AC2-B1 | AC2 | One place left | Boundary | capacity 2, 1 registered | Call function | — | Row stored | — | D |
| AC2-B2 | AC2 | Exactly full | Boundary | capacity 2, 2 registered | POST / call function | — | 409 `event_full` / `P0004 event full` | Count unchanged | A + D |
| AC2-N1 | AC2 | Capacity not set | Negative | Confirmed, capacity null | POST / call function | — | 409 `capacity_not_set` | No row | A + D |
| AC2-X1 | AC2 | A manual registration counts against self-registration | Cross-cutting | capacity 1; coordinator registers A | Attendee B calls `register_for_event` | — | `P0004 event full` | Only A's row | D |
| AC3-H1 | AC3 | Manual registration appears in SCRUM-34's view and the attendee's own list | Happy | AC1-H1 done | GET `/event-requests/{id}/registrations` as C1; GET `/attendee/registrations` as the attendee | — | Row in both | — | A |
| AC4-H1 | AC4 | Self-registration has null `registered_by`; manual has the coordinator | Happy | One of each | SCRUM-34 view | — | `registered_by` null vs C1 | — | A + D |
| AC4-N1 | AC1 | Coordinator not latest-assigned | Negative | C1 then C2 assigned | Call function as C1 | — | `P0002 event not found` / 404 | No row | A + D |
| AC4-N2 | AC1 | No session | Negative | — | POST without header | — | 401 | — | A |
| AC4-P1…P3 | AC1 | Other roles | Partition | — | POST | event_organiser, attendee, admin | 403 | — | A |
| AC4-X1 | AC1 | Browser roles cannot run the function or write `registered_by` | Cross-cutting | 0060 applied | Check privileges | anon, authenticated | No EXECUTE, no INSERT/UPDATE | — | D |
| AC1-X1 | AC1 | The form submits the email and shows the result | Cross-cutting | Coordinator panel | Type email, submit | — | Action called with event id and email; success refreshes; error message shown | — | C |

## Latest execution record

| ID | Automation status | Actual result | Execution status | Build or commit | Executed by and date | Remarks and evidence |
| --- | --- | --- | --- | --- | --- | --- |
| D-layer cases (AC1-H1, H2, P1, N1–N3, N5; AC2-B1, B2, N1, X1; AC4-H1, N1, X1) | Green | `ALL MANUAL REGISTRATION VERIFICATIONS PASSED`; SCRUM-21 verifier also passes after 0060 | Pass | `5cc4372`, disposable `postgres:16` in local Docker, bootstrap through 0052, then 0060 | Claude for Jaren, 23 Oct 2026 | Red first: run before 0060, it failed because `coordinator_register_attendee` does not exist. CI job `scrum41-database-verify` repeats this |
| A-layer cases (14 incl. parametrized) and 2 repository tests | Green | As expected | Pass | `5cc4372`, local Windows, faked repositories | Claude for Jaren, 23 Oct 2026 | Red first: 405, no POST route. Full service suite `pytest`: 787 passed, 1 skipped; `ruff check .` clean |
| AC1-X1 and action tests (C, 9) | Green | As expected | Pass | Frontend commit on this branch, local, `fetch` stubbed | Claude for Jaren, 23 Oct 2026 | Red first against empty stubs (8 failed). The form test found that React reset the email after a refusal, so the input is now controlled. `npm test`: 503 passed; lint, typecheck, build clean |
| Regression after merging dev (SCRUM-22 withdrawal, 0062) | Green | As expected | Pass | `9df6610`, local Windows | Claude for Jaren, 24 Oct 2026 | The registration controller, repository and error handlers now carry both the withdrawal route and the coordinator registration route. `pytest` in eventRequestService: 871 passed, 1 skipped; `ruff check .` clean. Frontend `npm test`: 509 passed; lint and typecheck clean. 0060 still runs before 0062 on a fresh database (CI job `scrum41-database-verify`) |
| Browser journey | Planned | — | Blocked | — | — | No local Supabase credentials; needs the shared database after 0060 is applied there |
| 0060 on the shared database | Planned | — | Not executed | — | — | Not applied. Apply after review, as with earlier migrations |
| Signed-in live check (AC1, AC2, AC3, AC4) | Green after fix | Coordinator1 added `attendee@example.com`: "Attendee added", Registered 1, Places available 4 of 5, row "Added by Coordinator". A second add was refused with nothing changed | Pass | Local stack on Windows (`docker compose`, `next dev`) against shared development, seeded accounts; labelled test event `86a4d5eb…` ("SCRUM-25/34/41 LIVE CHECK 31 Oct (Jaren)") taken through submit, approve, planning, booking, Venue Staff approval and Safety Officer approval to Confirmed; registration window and capacity (5) seeded by SQL, as SCRUM-21 D2 says | Claude for Jaren, 31 Oct 2026 | **Defect found and fixed:** the duplicate first showed "Registrations unavailable" (API 502), because PostgREST answers the function's `P0004` RAISE with HTTP 500 and `_rpc` treated every 500 as an outage. Fixed in `registration_repository._rpc` (a P0 code is a refusal); repository test AC4-N2 (SCRUM-21) red first (5 failed), then green. Rechecked: "This attendee is already registered for this event." |

Test design was AI-drafted; a team member still needs to review it (`testing.md` §10).
