# SCRUM-69 Test Cases: Show Venue Availability in Times

Last reviewed: 27 October 2026

Status: **scope approved by the Product Owner and the story owner (Kennedy) on 27 October 2026.** The criteria below are the six written on the Jira ticket, split into test-case groups; the response shape in A1 to A3 is the proposal Koei builds SCRUM-66's padding on, so it is shared with him before the frontend is built. Results are recorded below as work proceeds.

## Story

| Field | Value |
| --- | --- |
| Jira key | SCRUM-69 |
| Title | Show Venue Availability in Times |
| Sprint | Sprint 4 (22 October to 5 November 2026) |
| Points | 3 |
| User story | As an Event Coordinator, Venue Staff member or Safety Officer, I want a venue's availability calendar to show times instead of AM / PM / Night slots, so that I can see exactly when the venue is free now that bookings and blocks use 15-minute times. |
| Source | SCRUM-65 moved bookings, blocks and search to times but left the SCRUM-31 calendar on slots (migrations 0050 and 0051 keep the old `slots` column "for SCRUM-31's calendar until it moves to times"). Raised by Koei on 27 October 2026: SCRUM-66 (padding) needs the calendar on times first. SCRUM-31 and SCRUM-65 stay Done. |

## Story contract

| ID | Criterion (Jira) | Review outcome | Reason |
| --- | --- | --- | --- |
| AC1 | The calendar shows each date of the month as booked and blocked time ranges within 07:00 to 24:00, and the free time between them, in 15-minute steps. Ranges on a date do not overlap. | **Keep, Clarify** | The month, role and error rules of SCRUM-31 AC1 are kept unchanged. The new rule: each date is a partition of 07:00 to 24:00 into booked, blocked and free ranges (A1). |
| AC2 | A booked range comes from an approved booking and a blocked range from an active block, on the dates and times it covers. Pending, rejected and cancelled bookings and ended (lifted) blocks do not show. Where a block and a booking overlap, the time is shown as blocked. | **Keep** | Same sources and precedence as SCRUM-31 (A4), now on minutes. Times are half-open. |
| AC3 | A venue blocked as a whole in the catalogue shows its dates as unavailable. | **Keep** | Replaces SCRUM-31's `unavailable` slot state with a flag on each date (A2). |
| AC4 | The calendar shows no block reasons, event names or ids. | **Keep** | SCRUM-31 A3, unchanged. |
| AC5 | AM / PM / Night and "Not offered" no longer appear on the calendar or its API response. | **Clarify** | "Not offered" is dropped because every venue operates 07:00 to 24:00 (Product Owner, 20 October 2026). The Jira wording also mentions "the venue search link text"; that link never carried a slot, so the criterion is read as the calendar and its response only. |
| AC6 | Availability shown agrees with venue search and with the Venue Staff calendar for the same venue and date. | **Keep** | Checked against the search endpoint at every 15-minute step, and against the Venue Staff calendar model. |

### Included and excluded behaviour

| | Behaviour | Jira |
| --- | --- | --- |
| Included | `GET /venues/{venue_id}/calendar?month=YYYY-MM` returning times instead of slots | SCRUM-69 |
| Included | The availability page and its table showing booked, blocked and free times in words | SCRUM-69 |
| Included | The mock calendar in the browser tests and the browser journey | SCRUM-69 |
| Excluded | Setup and turnaround padding on the calendar. This story keeps one function, `occupied_minutes`, where a booking's occupied time is worked out; SCRUM-66 widens it | SCRUM-66 |
| Excluded | Tentative holds | SCRUM-18 |
| Excluded | The Venue Staff calendar (block reasons, event names): unchanged | SCRUM-23 |
| Excluded | Dropping the old `slots` column from the database | A later cleanup once nothing reads it |

### Actors and relationship permissions

Unchanged from SCRUM-31: Event Coordinator, Venue Staff and Safety Officer may read any venue's calendar. Every other role is refused; no token is 401. Nobody can change anything through this read.

### State and persistence

Read-only, no migration. A date's time is derived in this order: an active block, then an approved booking, otherwise free. A venue blocked in the catalogue sets the date's `unavailable` flag.

### Assumptions and open questions

| ID | Assumption or question | Used by |
| --- | --- | --- |
| A1 | Each date returns `entries` (booked or blocked ranges, earliest first, never overlapping, adjacent ranges of the same state merged) and `free` (the remaining ranges). Entries and free together cover exactly 07:00 to 24:00 (minutes 420 to 1440). Where a block overlaps a booking, the overlap is a blocked range and the booking is split around it. | AC1, AC2 |
| A2 | A date has `unavailable: true` when the venue is blocked in the catalogue. Its `free` is then empty. Its entries are still returned. | AC3 |
| A3 | A booking occupies its booked minutes on every date of its range (SCRUM-65's model). Padding is SCRUM-66's: `occupied_minutes(venue, booking)` returns the start and end today and is the one place to change. | AC2 |
| A4 | Pending, rejected and cancelled bookings never show; only approved ones do. A lifted block does not show. | AC2 |
| A5 | The response never carries block reasons, event names, booking ids, user ids or the venue's `operating_slots`. | AC4, AC5 |
| A6 | Not in this story: SCRUM-18 (tentative holds, Koei) will add a `held` state. It needs one new value in `CalendarState`, one precedence decision (proposed: blocked, then booked, then held) and one entry in the frontend's `ENTRY_LABELS` and `ENTRY_STYLES`. Held time would not be free. Raised by Koei on 27 October 2026. | none |

## Test cases (specification)

Fixed data: venue V1 operating normally, October 2026 unless stated. Times are minutes after midnight (09:00 = 540, 12:00 = 720). `entries` are `{state, start_minute, end_minute}`; `free` are `{start_minute, end_minute}`.

| ID | AC | Test scenario | Technique | Pre-conditions | Test steps | Test data | Expected result | Forbidden side effects | Layer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AC1-H1 | AC1 | A coordinator reads a month for an open venue | Happy | No blocks or bookings | `GET /venues/{V1}/calendar?month=2026-10` as `event_coordinator` | October 2026 | 200; 31 dates in order; each `unavailable: false`, `entries: []`, `free: [{420, 1440}]` | none | API |
| AC1-P1, AC1-P2 | AC1 | Venue Staff and a Safety Officer may also read it | Partition | As AC1-H1 | Same call as each role | none | 200, 31 dates | none | API |
| AC1-B1 to AC1-B3 | AC1 | Month lengths, leap year and year end | Boundary | As AC1-H1 | Read February 2028, February 2027, December 2026 | `2028-02`, `2027-02`, `2026-12` | 29, 28 and 31 dates; last dates `2028-02-29`, `2027-02-28`, `2026-12-31` | none | API |
| AC1-N1 to AC1-N6 | AC1 | A month that is not `YYYY-MM` is refused | Negative | As AC1-H1 | Read with each value, and none | `2026-13`, `2026-00`, `2026-1`, `26-10`, `abc`, omitted | 422 | none | API |
| AC1-N7 | AC1 | An unknown venue | Negative | none | Read an unknown id | `does-not-exist` | 404 "Venue not found" | none | API |
| AC1-N8 to AC1-N10 | AC1 | Other roles are refused | Negative | As AC1-H1 | Read as organiser, attendee, technical support | none | 403 "Insufficient permissions" | none | API |
| AC1-X1 | AC1 | No token | Cross-cutting | As AC1-H1 | Read without a token | none | 401 "Authentication required" | none | API |
| AC1-X2 | AC1 | Every date is a partition of 07:00 to 24:00 | Cross-cutting | Overlapping and touching bookings and blocks on several dates | Read the month; for each date sort entries and free together | mixed fixture | The ranges are ordered, never overlap, leave no gap, start at 420 and end at 1440, all on 15-minute steps | none | API |
| AC1-U1 | AC1 | The table lists each date with its times in words | Happy | A month with one booking and one block | Render the table | fixture | One row per date; the booked and blocked times written as "Booked 09:00–12:00" and "Blocked 10:00–11:00"; free times listed | Colour-only state | UI |
| AC1-U2 | AC1 | Previous and next month links are kept | Cross-cutting | As AC1-U1 | Render | none | Links to the adjacent months (and none at the first or last representable month) | none | UI |
| AC2-H1 | AC2 | An approved booking shows its times on each of its dates only | Happy | Booking 09:00 to 12:00 on 12 to 14 October | Read October | 540 to 720 | Each of the three dates has one `booked` entry 540 to 720 and `free` `[420–540]`, `[720–1440]`; 11 and 15 October are fully free | none | API |
| AC2-B1, AC2-B2 | AC2 | The first and last date are included, the days around are not | Boundary | As AC2-H1 | Read 11, 12, 14, 15 October | none | `entries` empty on 11 and 15; one entry on 12 and 14 | none | API |
| AC2-B3, AC2-B4 | AC2 | A booking touching the window edges, and a one-step booking | Boundary | Booking 07:00 to 07:15; booking 23:45 to 24:00; booking 12:00 to 12:15 | Read the month | 420 to 435; 1425 to 1440; 720 to 735 | Entries of exactly those minutes; `free` has no empty or reversed range | none | API |
| AC2-B5 | AC2 | Half-open: a range ending at 12:00 leaves 12:00 free | Boundary | Booking 09:00 to 12:00 | Read | 540 to 720 | `free` contains a range starting at 720 | none | API |
| AC2-H2 | AC2 | An active block shows its times | Happy | Block 20 to 21 October, 18:00 to 24:00 | Read October | 1080 to 1440 | Both dates: one `blocked` entry 1080 to 1440; `free` `[420–1080]`; 22 October fully free | none | API |
| AC2-P1 | AC2 | A lifted block does not show | Partition | Lifted block on 20 October | Read | none | No entry | none | API |
| AC2-P2 to AC2-P4 | AC2 | Pending, rejected and cancelled bookings do not show | Partition | One of each on 12 October | Read | none | No entry | none | API |
| AC2-P5 | AC2 | A multi-day booking applies its times to every date | Partition | Booking 09:00 to 12:00 on 5 to 7 October | Read | none | Three dates each with 540 to 720; no other date has a `booked` entry | none | API |
| AC2-P6 | AC2 | The calendar builder itself ignores bookings that are not approved, whatever it is handed | Partition | A pending, a rejected and a cancelled booking passed straight to `build_calendar` | Build one month | one booking per status | No entry on its date | none | Unit |
| AC2-P7 | AC2 | The calendar builder itself ignores another venue's blocks and bookings | Partition | A block and a booking of another venue passed straight to `build_calendar` | Build one month for this venue | other venue's data | No entry; the date is fully free | none | Unit |
| AC2-H3 | AC2 | Where a block and a booking overlap the time is blocked, and the booking is split around it | Happy | Booking 09:00 to 12:00 and block 10:00 to 11:00 on 12 October | Read | none | Entries: booked 540–600, blocked 600–660, booked 660–720; `free` `[420–540]`, `[720–1440]` | none | API |
| AC2-H4 | AC2 | Two touching bookings are one booked range | Happy | Bookings 09:00 to 10:00 and 10:00 to 11:00 | Read | none | One `booked` entry 540 to 660 | A visible boundary between the events | API |
| AC2-H5 | AC2 | Cancelling an approved booking frees its time | Happy | Approved booking, then cancelled | Read before and after | none | `booked` entry, then none | none | API |
| AC2-X1 | AC2 | A booking spanning two months shows in both; one outside does not | Cross-cutting | Booking 30 October to 2 November; booking in December | Read October and November | none | Entries on 30 and 31 October and on 1 and 2 November only | none | API |
| AC2-X2 | AC2 | Reading changes nothing | Cross-cutting | A block and a booking | Read twice | none | 200 both times; venue, blocks and bookings unchanged | Any write | API |
| AC3-P1 | AC3 | A catalogue-blocked venue shows its dates unavailable | Partition | Venue with `status` blocked | Read | none | Every date `unavailable: true`, `free: []` | none | API |
| AC3-P2 | AC3 | An available venue is not marked unavailable | Partition | Venue available | Read | none | Every date `unavailable: false` | none | API |
| AC3-P3 | AC3 | A block on an unavailable venue still shows | Partition | Catalogue-blocked venue with a block | Read | none | The block's entry is returned and the date is unavailable | none | API |
| AC3-U1 | AC3 | An unavailable date reads "Unavailable" | Partition | Unavailable day | Render | fixture | The row says Unavailable and lists no free time | Free times shown | UI |
| AC4-X1 | AC4 | No private details | Cross-cutting | A block with a secret reason and a booking with a secret event name | Read as coordinator, staff and safety officer | secrets | None of the reason, event name, booking id, user id or block id appears; the top-level keys are `venue_id`, `month`, `days`; day keys `date`, `unavailable`, `entries`, `free`; entry keys `state`, `start_minute`, `end_minute` | Any extra field | API |
| AC5-X1 | AC5 | No slot vocabulary in the response | Cross-cutting | A busy venue | Read | none | The text contains none of `slot`, `AM`, `PM`, `NIGHT`, `not_offered`, `operating_slots` | none | API |
| AC5-U1 | AC5 | No slot vocabulary on the screen | Cross-cutting | A busy month | Render | fixture | The page shows no "AM", "PM", "Night" or "Not offered" | none | UI |
| AC6-X1 | AC6 | The calendar and venue search agree at every 15-minute step | Cross-cutting | Three venues with bookings and blocks | For each date and each step from 07:00 to 24:00, ask search for that step and compare | fixture | A venue is in the search result exactly when the step is inside a free range of a non-unavailable date | none | API |
| AC6-U1 | AC6 | The calendar and the Venue Staff calendar agree on free time | Cross-cutting | The same blocks and bookings | Build both models | fixture | For each date, the staff calendar has free time exactly when the availability calendar has a free range | none | UI (unit) |
| AC1-E1 | AC1, AC2 | The journey: search, open the calendar, see times, change month | Happy | Mock API with a booking and a block in March 2030 | Search with a date, click View availability, read the March table, click Next month | `2030-03` | The booked and blocked times are shown in words; April has 30 rows; an organiser is refused | none | E2E (mocked API) |

## Latest execution record

| ID | Automation status | Actual result | Execution status | Build or commit | Executed by and date | Remarks and evidence |
| --- | --- | --- | --- | --- | --- | --- |
| AC1-H1, P1, P2, B1 to B3, N1 to N10, X1, X2; AC2-H1 to H5, B1 to B5, P1 to P7, X1, X2; AC3-P1 to P3; AC4-X1; AC5-X1; AC6-X1 (API and unit) | Green | `.venv/bin/pytest -q tests/test_venue_calendar.py`: 48 passed. Whole `backend/venueService`: 626 passed, 10 skipped; `ruff check .` clean. Red before the change: 27 failed, 17 passed (the rules that did not change), all for the missing `entries` / `unavailable` fields | Pass | branch `feat/scrum-69-availability-times` on `dev` `5bbf833` (uncommitted), local venv, in-memory stores | Claude for Kennedy, 27 Oct 2026 | `backend/venueService/tests/test_venue_calendar.py`. Not run against Supabase: the repository calls are unchanged |
| Mutation check on `calendar_view.py` | Green | Eleven one-line faults, all caught: booking not split around a block, touching ranges not merged, last or first date excluded, pending bookings shown, lifted blocks shown, free time kept for an unavailable venue, another venue's block or booking shown, free time starting before 07:00, a booking's end moved by a step | Pass | as above | Claude for Kennedy, 27 Oct 2026 | "Pending bookings shown" first survived because the repository already filters to approved bookings; AC2-P6 and AC2-P7 were added to call the builder directly |
| AC1-U1, AC1-U2, AC2-U1, AC3-U1, AC5-U1, AC6-U1 (UI) | Green | `npx vitest run`: 66 files, 527 tests passed (14 in `venue-availability.test.tsx`); `npm run lint` and `npm run typecheck` clean. Red before the component change: 8 of the file's tests failed | Pass | as above, local | Claude for Kennedy, 27 Oct 2026 | `frontend/__tests__/venue-availability.test.tsx` |
| AC1-E1 (E2E, mocked API) | Green | Playwright, Chrome channel: 2 passed (the journey and the organiser refusal) | Pass | as above; the mock venue API in `frontend/e2e/support/venue-api.mjs` mirrors the new rules | Claude for Kennedy, 27 Oct 2026 | `frontend/e2e/venue-availability.spec.ts`. Proves the screen and its wiring, not the real service |
| Final tree, with the SCRUM-31 review fixes that missed PR #68 | Green | `backend/venueService`: 629 passed, 10 skipped, `ruff check .` clean. `backend/eventRequestService`: 950 passed, 1 skipped (unchanged code). `frontend`: `npx vitest run` 66 files, 537 tests passed; lint and typecheck clean; Playwright (Chrome channel) `e2e/venue-availability.spec.ts` 2 passed | Pass | branch `feat/scrum-69-availability-times` at `29d3bf6` plus the docs cherry-pick, on `dev` `5bbf833` (no newer `dev` commits), local | Claude for Kennedy, 27 Oct 2026 | `e436066` (edge months, the searched month kept in the link, simpler month check, unneeded sorts removed) and its docs commit `8945c06` were pushed to the SCRUM-31 branch after PR #68 merged, so they never reached `dev`; they are cherry-picked here (two conflicts, in the search page imports and the availability test imports, resolved by keeping both sides) |
| Real stack, shared development, PR CI | Planned | Not run | Not executed | none | none | To do: update `scrum31_live_check.py` for the new response and run it against the Docker stack; PR CI after pushing |
