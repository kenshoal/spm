# SCRUM-66 — Apply Setup/Turnaround Padding in Venue Availability and Search

**Issue tracker:** SCRUM-66

**User story:** As an Event Coordinator, I want venue availability and search to account for each venue's setup and turnaround time, so that I don't request a slot that will be refused at approval.

## Story contract review

SCRUM-66 is the follow-up to SCRUM-20 raised by the Product Owner (Jaren) on 22 October 2026. It completes Week 7 Customer Change #1, which says setup and turnaround "must be included when checking availability and detecting booking conflicts": SCRUM-20 (0054) covered conflict detection in booking approval; SCRUM-66 covers availability. The calendar part builds on SCRUM-69 (Kennedy, PR #108), which moved the SCRUM-31 calendar to times and left the padding seam `occupied_minutes` for this story.

| issue tracker criterion | Outcome | Reason |
| --- | --- | --- |
| Availability, search and the SCRUM-31 calendar treat a booking as occupying its start minus setup to its end plus turnaround, using the same rule as SCRUM-20's conflict check. | Keep → AC1, AC3, AC4 | All three use `time_conflicts.padded_range`, the Python twin of `private.check_booking_candidate` (0054). |
| A slot that approval would refuse because of padding is not shown as free. | Keep → AC1, AC2, AC3, AC4 | Includes a time whose own setup or turnaround leaves 07:00–24:00, as approval refuses it. |
| A gap exactly equal to turnaround plus setup is shown as free. | Keep → AC1, AC3, AC4 | Ranges are half-open, as in SCRUM-20 AC5. |

## Increment scope

- **Included:** dated venue search with a time (`GET /venues/search`), dated search with only a date, the availability check (`POST /venues/{id}/availability`) and the availability calendar (`GET /venues/{id}/calendar`).
- **Excluded:** booking approval (already padded by SCRUM-20/0054; unchanged here); blocks (compared without padding, as approval does); tentative holds (SCRUM-18).
- **No migration:** search, the availability check and the calendar run in venueService.
- **Rules:**
  - A booking occupies its venue from start minus the venue's setup to end plus its turnaround. Both bookings at a venue use that venue's values.
  - A requested time is padded the same way; its padded range must stay inside 07:00–24:00.
  - Only approved bookings take time. Pending, rejected and cancelled requests never do.
  - Blocks are compared with the requested time without padding.
- **Decision (Product Owner, 27 October 2026):** with only a date, search offers a day when some 15-minute booking would be accepted there, i.e. a gap of at least 15 minutes plus setup plus turnaround, under the same rules. This is the time-based equivalent of the old "one free slot" rule (SCRUM-15 AC3-B1, SCRUM-23 AC2-P5). The booking's setup and turnaround must fit 07:00–24:00, as in the timed conflict check, and existing bookings' setup and turnaround count as occupied. Boundary pairs: AC2-B1 (between bookings) and AC2-B2 (at 07:00).

## Acceptance criteria

- **AC1 (search with a time):** A venue is offered for a date and time only if the time's own setup and turnaround fit 07:00–24:00, no active block overlaps the time, and no approved booking's padded range overlaps the time's padded range. A gap exactly equal to setup plus turnaround is offered.
- **AC2 (search with only a date):** A venue is offered for a date only if some 15-minute booking on that date would be offered under AC1.
- **AC3 (availability check):** The check reports `booking_conflict` with each padded overlap (cut at 07:00–24:00), and `setup_outside_window` / `turnaround_outside_window` in approval's order.
- **AC4 (calendar):** A booked range includes the venue's setup and turnaround, cut at 07:00–24:00; an active block still wins over a booking; free time agrees with search.

## Test-case specification

Times are on 10 November 2026 at one venue unless stated. "30 / 45" means setup 30 minutes, turnaround 45. Unless stated, the venue is 30 / 45 with A approved 10:00–12:00.

| ID | AC | Test scenario | Technique | Pre-conditions | Test steps | Test data | Expected result | Forbidden side effects | Layer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AC1-H1 | AC1 | A time inside A's turnaround is not offered | Happy | A | Search | 12:15–13:00 | Not offered | — | API |
| AC1-B1 | AC1 | After A, the exact gap is offered; one step less is not | Boundary | A | Search | 13:15–14:00; 13:00–13:45 | Offered; not offered | — | API |
| AC1-B2 | AC1 | The same boundary before A | Boundary | A | Search | 08:00–08:45; 08:00–09:00 | Offered; not offered | — | API |
| AC1-B3 | AC1 | The time's own padding must fit the window | Boundary | 30 / 45, no bookings | Search | 07:30–09:00; 07:15–09:00; 22:00–23:15; 22:00–23:30 | Offered; not; offered; not | — | API |
| AC1-P1 | AC1 | 0 / 0 behaves as before | Partition | 0 / 0, A | Search | 12:00–13:00; 11:45–13:00 | Offered; not offered | — | API |
| AC1-P2 | AC1 | Pending, rejected and cancelled requests take no time | Partition | 10:00–12:00 in each status | Search | 12:15–13:00 | Offered | — | API |
| AC1-P3 | AC1 | Blocks are not padded | Partition | Block 10:00–12:00, no bookings | Search | 12:00–13:00; 11:45–13:00 | Offered; not offered | — | API |
| AC1-P4 | AC1 | Padding stays on its venue and dates | Partition | A; another 30 / 45 venue | Search | 12:15–13:00 on 10 Nov at the other venue; at A's venue on 11 Nov | Offered; offered | — | API |
| AC2-B1 | AC2 | A day is offered only with a padded 15-minute gap | Boundary | Approved 07:30–12:45 and 15:30–23:15 (gap 13:30–15:00); and 07:30–12:45 and 15:15–23:15 (gap 75 minutes) | Search by date | — | Offered; not offered | — | API |
| AC2-B2 | AC2 | At the start of the day the setup must fit after 07:00 | Boundary | Approved 09:00–23:15 (gap 07:00–08:30); and 08:45–23:15 (gap 75 minutes) | Search by date | — | Offered; not offered | — | API |
| AC2-P1 | AC2 | 0 / 0: one free step is enough | Partition | 0 / 0, approved 07:00–23:45, then also 23:45–24:00 | Search by date | — | Offered; not offered | — | API |
| AC3-H1 | AC3 | The check reports a padded clash with its padded overlap | Happy | A | Check | 12:15–13:00 | Not available; `["booking_conflict"]`; overlap 11:45–12:45 | — | API |
| AC3-B1 | AC3 | The exact gap is available | Boundary | A | Check | 13:15–14:00 | Available; no reasons | — | API |
| AC3-B2 | AC3 | Window codes, and an overlap cut at 07:00 | Boundary | Approved 07:30–09:00; a 30 / 45 venue with none | Check | 07:15–08:00; 22:00–23:30 at the empty venue | `["setup_outside_window", "booking_conflict"]`, overlap from 07:00; `["turnaround_outside_window"]` | — | API |
| AC4-H1 | AC4 | The calendar shows A with its padding | Happy | A | Read November | — | Booked 09:30–12:45; free 07:00–09:30 and 12:45–24:00 | — | API |
| AC4-P1 | AC4 | 0 / 0 calendar unchanged | Partition | 0 / 0, A | Read | — | Booked 10:00–12:00 | — | API |
| AC4-B1 | AC4 | Padding beyond the window is cut | Boundary | 0 / 0 with 07:00–08:00 and 23:00–24:00 approved, then changed to 30 / 45 | Read | — | Booked 07:00–08:45 and 22:30–24:00; free 08:45–22:30 | — | API |
| AC4-P2 | AC4 | A block still wins over a padded booking | Partition | A; block 12:00–13:00 | Read | — | Booked 09:30–12:00; blocked 12:00–13:00 | — | API |
| AC4-X1 | AC4 | The calendar and search agree | Cross-cutting | A | Read; search the first free time and one step earlier | 13:15–14:00; 13:00–13:45 | Offered; not offered | — | API |

## Latest execution record

Build: `feat/scrum-66-padded-availability` on `dev` `d2fc6a6` (after SCRUM-69, PR #108), uncommitted working tree, 27 October 2026. Executed with Claude Code, pending human review. Code: `backend/venueService/app/time_conflicts.py`, `availability.py`, `block_checks.py`, `availability_models.py`, `booking_decisions.py`, `calendar_view.py`; `frontend/e2e/support/venue-api.mjs`, `frontend/app/venues/availability/page.tsx`. Tests: `backend/venueService/tests/test_padded_availability.py`.

| ID | Automation status | Actual result | Execution status | Build or commit | Executed by and date | Remarks and evidence |
| --- | --- | --- | --- | --- | --- | --- |
| AC1-H1, AC1-B1, AC1-B2, AC1-B3, AC1-P1, AC1-P2, AC1-P3, AC1-P4 | Green | As expected | Pass | `d2fc6a6` + working tree, `python:3.12-slim` | Claude Code, 27 Oct 2026 | Red on `dev` for AC1-H1, AC1-B1b, AC1-B2b, AC1-B3b, AC1-B3d, AC1-P4 |
| AC2-B1, AC2-B2, AC2-P1 | Green | As expected | Pass | same | same | Red on `dev` for AC2-B1 and AC2-B2 |
| AC3-H1, AC3-B1, AC3-B2 | Green | As expected | Pass | same | same | Red on `dev` for AC3-H1, AC3-B2 |
| AC4-H1, AC4-P1, AC4-B1, AC4-P2, AC4-X1 | Green | As expected | Pass | same | same | Red on `dev` for AC4-H1, AC4-B1, AC4-P2, AC4-X1 |

Red: on `dev`'s code, 14 of the 26 cases failed (every padding case); the 12 that passed on both are the unchanged-behaviour partitions.

| Check | Command and environment | Result | Remarks |
| --- | --- | --- | --- |
| Backend regression | `pytest` (whole venueService suite) and `ruff check .` in `python:3.12-slim` | 655 passed; Ruff clean | Includes SCRUM-69's 51 calendar cases and SCRUM-20's approval cases; approval's window codes are reported once |
| Frontend | `vitest run`, `npm run lint`, `npm run typecheck` | 537 passed; clean | The availability page says booked times include setup and turnaround |
| Production build and E2E | `npx playwright test` (builds with `next build --webpack`) | Build passed; 51/51 journeys | The E2E mock pads search and the calendar like venueService |
