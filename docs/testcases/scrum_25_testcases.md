# SCRUM-25 — Record Attendance at an Event

Source: [Jira SCRUM-25](https://is212g9t4.atlassian.net/browse/SCRUM-25). Branch: `feat/scrum-25-record-attendance`, stacked on `feat/scrum-41-manual-registration` (same registrations panel). Retarget to `dev` once SCRUM-34 and SCRUM-41 merge.

## Approved contract

As ConnectSphere event staff, I want to check registered attendees in at the event, so that actual attendance is recorded separately from registration.

Jaren (story owner) approved on 23 October 2026: "the event's coordinator checks people in. Manual lookup only, QR becomes its own story, check-in only on the event day." On 31 October 2026 Jaren withdrew the separate QR story (SCRUM-68): QR scanning is not built in this release and is recorded only here. The rewording is recorded here, not written back to Jira.

| Jira AC | Outcome | Approved wording |
| --- | --- | --- |
| Staff can check in a registered attendee at the counter by scanning a QR code or by manual lookup. | **Split** | **AC1:** Given a Confirmed event on one of its event days, when its latest coordinator picks a registration from the registrations list and checks it in, then the check-in is recorded. QR scanning is not built in this release (see the note above). |
| Given a check-in, when recorded, then the attendee is marked **attended**, distinct from merely registered. | **Keep, clarified** | **AC2:** Given a check-in, then the registration stores `attended_at` (the check-in time) and `checked_in_by` (the coordinator) and keeps status `Registered`, so capacity counts are unchanged. |
| Attendance records distinguish registered-and-attended from registered-and-absent. | **Merge with AC2** | **AC3:** Given an event's registrations, then SCRUM-34's view shows `attended` (Registered with `attended_at`) and `absent` (Registered without it) counts, and each row's `attended_at`. Absent is worked out, not stored; the panel labels it "Not checked in". |
| Only registered attendees can be checked in. | **Keep, clarified** | **AC4:** Given a registration that isn't on this event or isn't `Registered`, or one already checked in, when the coordinator checks it in, then it is refused (404 `registration_not_found` or 409 `already_checked_in`) and nothing changes. |

Cross-cutting: only the latest-assigned `event_coordinator` (others 403, no session 401, unassigned or reassigned 404 `event_not_found`), rechecked under the event lock. Outside the event days: 409 `not_event_day`.

## Decisions

| # | Decision |
| --- | --- |
| D1 | `POST /event-requests/{id}/registrations/{registration_id}/check-in`. The clock comes from `get_now()` and is passed to the database as `p_now` (SCRUM-21 D9). |
| D2 | Event day: the Asia/Singapore calendar date of `p_now` equals the Asia/Singapore date of any entry in `proposed_date_times`. An event with no dates is never on its event day. |
| D3 | Migration `0061_event_attendance.sql`: nullable `attended_at timestamptz`, `checked_in_by uuid` on `event_registrations`, and `check_in_attendee(...)`, `service_role` only. No new status, so `status = 'Registered'` capacity counts stay correct. |
| D4 | Event must be `Confirmed`. |
| D5 | No undo of a check-in in this story. |

## Scope

- **Included:** AC1 to AC4; the endpoint; a "Check in" button on each not-yet-checked-in row of the coordinator's Registrations panel (Confirmed events, event day); attended and not-checked-in counts.
- **Excluded:** QR scanning (not built in this release; no separate story), undoing a check-in, organisers or other staff checking in, withdrawal (SCRUM-22), notifications.

## Persistence and atomicity

`check_in_attendee` locks the event row, then the registration row, rechecks assignment, status, event day, the registration's event and status, and whether it's already checked in, then updates. A refusal writes nothing; a race between two check-ins of the same registration leaves exactly one.

## Assumptions and open questions

1. Event days are compared by date only, not by the event's start time. Checking in early on the day is allowed.

## Test case specification

Layers: A = API (`backend/eventRequestService/tests/test_attendance_api.py`), D = DB (`database/verify_event_attendance.sql`), C = component (`frontend/__tests__/attendance.test.tsx`).

| ID | AC | Test scenario | Technique | Pre-conditions | Test steps | Test data | Expected result | Forbidden side effects | Layer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AC1-H1 | AC1, AC2 | The assigned coordinator checks a registration in on the event day | Happy | Confirmed, date 1 Feb 2030 18:00 SGT; C1 latest; a Registered row | POST check-in as C1 at 1 Feb 2030 12:00 SGT | — | 200; `attended_at` = now, `checked_in_by` C1, status `Registered` | Other rows unchanged | A + D |
| AC1-P1 | AC1 | Second day of a multi-day event | Partition | Dates 1 and 2 Feb 2030 | Check in on 2 Feb | — | Allowed | — | D |
| AC1-B1 | AC1 | 23:59:59 SGT the day before | Boundary | Date 1 Feb 2030 18:00 SGT | now = 31 Jan 23:59:59 SGT | — | `P0004 not event day` | No update | D |
| AC1-B2 | AC1 | 00:00:00 SGT on the day | Boundary | as above | now = 1 Feb 00:00:00 SGT | — | Allowed | — | D |
| AC1-B3 | AC1 | 00:00:00 SGT the day after | Boundary | as above | now = 2 Feb 00:00:00 SGT | — | `P0004 not event day` | No update | D |
| AC1-X1 | AC1 | Day is judged in Singapore, not UTC | Cross-cutting | Date 1 Feb 2030 01:00 SGT (31 Jan 17:00 UTC) | now = 1 Feb 08:00 SGT (1 Feb 00:00 UTC) and 31 Jan 20:00 SGT (31 Jan 12:00 UTC) | — | First allowed, second refused | — | D |
| AC1-N1 | AC1 | Event not Confirmed | Negative | Planning event | Call function | — | `P0002 event not found` | No update | D |
| AC1-N2 | AC1 | API refusal off the event day | Negative | as AC1-H1 but now = 3 Feb | POST | — | 409 `not_event_day` | Row unchanged | A |
| AC1-N3 | AC1 | Event with no dates | Negative | `proposed_date_times` empty | Call function | — | `P0004 not event day` | — | D |
| AC2-H1 | AC2 | Check-in keeps the place counted | Happy | capacity 1, 1 registered and checked in | `register_for_event` for another attendee | — | `P0004 event full` | — | D |
| AC3-H1 | AC3 | View shows attended and absent counts and row times | Happy | 3 Registered, 1 checked in | GET view as C1 | — | attended 1, absent 2; row has `attended_at` | — | A + C |
| AC4-N1 | AC4 | Registration from another event | Negative | Row on event B | Check it in on event A | — | 404 `registration_not_found` | Row unchanged | A + D |
| AC4-N2 | AC4 | Unknown registration id | Negative | — | POST random id | — | 404 `registration_not_found` | — | A |
| AC4-N3 | AC4 | Already checked in | Negative | Row checked in | POST again | — | 409 `already_checked_in` | `attended_at` and `checked_in_by` unchanged | A + D |
| AC4-N4 | AC4 | Withdrawn registration | Negative | Row withdrawn as SCRUM-22 does it (`status` Withdrawn, `withdrawn_at` set), with 0062 applied before 0061 | Call function | — | `P0002 registration not found` | Row unchanged | D |
| AC4-X1 | AC4 | Two sessions check the same row in | Cross-cutting | One Registered row | Concurrent calls (row lock) | — | One succeeds, the other `already checked in` | Never two updates | D (sequential under lock) |
| AC3-N1 | AC3 | A checked-in attendee withdraws before the start time | Negative | Row checked in at 12:00 SGT on the event day; event starts 18:00 | `withdraw_registration` at 13:00 as the attendee | — | `P0004 already checked in` (0067) | Status `Registered`, `withdrawn_at` null, `attended_at` kept | D |
| AC3-N2 | AC3 | API refusal for a checked-in attendee's withdrawal | Negative | Row with `attended_at` set | POST `/attendee/registrations/{id}/withdrawal` | — | 409 `already_checked_in` | Row unchanged | A |
| AC1-N4 | AC1 | Coordinator reassigned away | Negative | C1 then C2 | Call as C1 | — | `P0002 event not found` / 404 | Row unchanged | A + D |
| AC1-N5 | AC1 | No session | Negative | — | POST without header | — | 401 | — | A |
| AC1-P2…P4 | AC1 | Other roles | Partition | — | POST | event_organiser, venue_staff, attendee | 403 | — | A |
| AC1-X4 | AC1 | Browser roles cannot run the function | Cross-cutting | 0061 | Privilege check | anon, authenticated | No EXECUTE | — | D |
| AC1-X2 | AC1, AC3 | Panel offers "Check in" only on rows not yet checked in, and only when allowed | Cross-cutting | Panel with one of each | Render with and without `canCheckIn` | — | Button only on unchecked rows when allowed; checked-in rows show the time | — | C |
| AC1-X3 | AC1 | The check-in action posts to the bound registration and maps refusals | Cross-cutting | `fetch` stubbed | Call action | 200, 409 not_event_day, 409 already_checked_in, 404 | Right URL; messages per code; revalidates on success | — | C |


## Latest execution record

| ID | Automation status | Actual result | Execution status | Build or commit | Executed by and date | Remarks and evidence |
| --- | --- | --- | --- | --- | --- | --- |
| D-layer cases (AC1-H1, P1, B1–B3, X1, N1, N3, N4, X4; AC2-H1; AC4-N1, N3, N4, X1) | Green | `ALL EVENT ATTENDANCE VERIFICATIONS PASSED`; SCRUM-21 and SCRUM-41 verifiers also pass after 0061 | Pass | `ea52ccb`, disposable `postgres:16` in local Docker, bootstrap through 0052, then 0060 and 0061 | Claude for Jaren, 23 Oct 2026 | Red first: before 0061 it failed because `check_in_attendee` does not exist. A check-in also succeeded when run as `service_role`. AC4-X1 is proven sequentially under the row lock, not by two live sessions |
| A-layer cases (11 incl. parametrized) and 1 repository test | Green | As expected | Pass | `ea52ccb`, local Windows, faked repositories | Claude for Jaren, 23 Oct 2026 | Red first: 404, no route. Full suite `pytest`: 801 passed, 1 skipped; `ruff check .` clean |
| C-layer cases (AC1-B1–B3, N3, X2, X3; AC3-H1; 11 tests) | Green | As expected | Pass | Frontend commit on this branch, local, `fetch` stubbed | Claude for Jaren, 23 Oct 2026 | Red first against stubs (7 failed; the 3 "false" boundary cases passed against the stub). `npm test`: 514 passed; lint, typecheck, build clean |
| D-layer rerun in dev order (review fix) | Green | All three verifiers pass with 0062 applied before 0061; the previous verifier failed on `event_registrations_withdrawn_at_check` | Pass | Branch after the review fix, disposable `postgres:16` in local Docker: bootstrap through 0052, then 0060, 0062, 0061 | Claude for Jaren, 30 Oct 2026 | AC4-N4 now withdraws as SCRUM-22 does (`status` and `withdrawn_at`) instead of dropping the status CHECK. CI job `scrum41-database-verify` applies the same order |
| AC3-N1, AC3-N2 (review of PR #103: no withdrawal after check-in) | Green | `ALL EVENT ATTENDANCE VERIFICATIONS PASSED`; API 409 `already_checked_in` | Pass | This branch after `0bb3f32`, disposable `postgres:16` in local Docker (bootstrap through 0052, then 0060, 0062, 0061, 0067); local Windows for the API | Claude for Jaren, 30 Oct 2026 | Red first: before 0067 the verifier stopped at `AC3-N1: withdrew a checked-in registration`, and the API test got 200. The SCRUM-21, SCRUM-41 and SCRUM-22 verifiers still pass after 0067. `pytest`: 963 passed, 1 skipped. `ruff check .` reports one DTZ001 in `tests/test_registration_window_notifier.py`, which is unchanged from dev and not in this change |
| Shared development rollout | Green | `ALL EVENT ATTENDANCE VERIFICATIONS PASSED` | Pass | `0061` then `0067` applied to shared development (`rrmvhxrxrrnigjdxcbwt`) through the Supabase MCP, after `0062` was already there | Claude for Jaren, 30 Oct 2026 | Live `check_in_attendee` and `withdraw_registration` bodies match the files on dev (md5 `900bb3b6…`, `bda8b8a4…`); EXECUTE for `service_role` only. `verify_event_attendance.sql` run in a transaction and rolled back: no fixtures left. Signed-in browser check still to do: shared has no Confirmed event with a registration capacity yet |
| Browser journey | Planned | — | Blocked | — | — | No local Supabase credentials; needs the shared database after 0060 and 0061 are applied |
| Signed-in live check (AC1, AC2, AC3) | Green | Coordinator1 checked the attendee in on the event day: Checked in 1, Not checked in 0, check-in time shown, "Check in" gone for that row; the place stays counted (Places available 4) | Pass | Local stack on Windows (`docker compose`, `next dev`) against shared development, seeded accounts; test event `86a4d5eb…` ("SCRUM-25/34/41 LIVE CHECK 31 Oct (Jaren)") dated 31 Oct 2026 22:00 SGT | Claude for Jaren, 31 Oct 2026 | Withdrawal after check-in (AC3-N1) is proven on shared by the rolled-back verifier; there is no attendee withdraw screen yet. The PostgREST 500 defect (see SCRUM-41) also affected check-in refusals and is fixed in the same change |

Test design was AI-drafted; a team member still needs to review it (`testing.md` §10).
