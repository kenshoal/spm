# SCRUM-65 Test Cases: Book Venues in 15-Minute Increments

Last reviewed: 20 October 2026

Status: **contract approved by the story owner and Product Owner (Jaren) on 20 October 2026**, with the three decisions below. Slice 1 is in progress; results are recorded below as work proceeds.

## Story

| Field | Value |
| --- | --- |
| Jira key | SCRUM-65 |
| Title | Book Venues in 15-Minute Increments |
| Sprint | Sprint 3 (ends 22 October 2026) for slice 1; the rest carries into Sprint 4 |
| User story | As a coordinator, I want to book a venue for an exact start and end time in 15-minute steps, so that the booking matches the time my event actually needs. |
| Source | Customer ruling, GitHub Discussion #131: the 15-minute unit replaces AM / PM / Night for venue timing, and the 07:00–24:00 operating window stays. Product Owner approval 18 October 2026. Moved into Sprint 3 in place of SCRUM-57 by team decision (Agent Discussions #2401, #2405). |
| Related | SCRUM-20 (conflict rules, padding; Koei), SCRUM-31 (availability view; Kai Jie), SCRUM-35 (change requests; Heng Rui), SCRUM-59 (setup and turnaround) |

## Story contract

The seven live Jira criteria (read on 20 October 2026) were reviewed with the vocabulary in `docs/standards/testing.md` §1, against the schema (`0016`, `0018`, `0023`, `0024`), venueService, the frontend, Koei's SCRUM-20 helper (`feat/scrum-20-venue-booking-conflicts`, `app/time_conflicts.py`) and the shared data.

| ID | Original criterion | Outcome | Reason |
| --- | --- | --- | --- |
| AC1 | A booking states a date, a start time and an end time, each on a 15-minute boundary and inside 07:00–24:00; otherwise refused with the reason. | **Clarify** | SCRUM-32 AC1 allows a booking over several dates and AC7 keeps it. Shared data has multi-day bookings. So a booking keeps its date range and gains one start and end time that apply on each of its dates. |
| AC2 | Bookings conflict only if their times overlap; approving over an approved booking is refused. | **Clarify; padding moved** | Overlap means a shared date and overlapping half-open time ranges. Setup and turnaround padding is SCRUM-20 AC3, added inside the same approval function, which stays the single authoritative check. |
| AC3 | Blocks use start and end times; blocked time not offered and cannot be approved. | **Keep** | Same date-range plus daily-time shape as AC1. |
| AC4 | Search, suitability and the availability view work on date and time. | **Narrow** | Venue search, the suitability check and the Venue Staff block calendar. SCRUM-31's availability view stays with SCRUM-31 and reads this data. |
| AC5 | Existing bookings and blocks are converted without losing or changing any; the team agrees the ranges first. | **Clarify** | Ranges decided below. A row whose slots are not consecutive (AM with Night, no PM) cannot become one range, so the migration stops and lists it instead of guessing. Shared has none today. |
| AC6 | Booking, block, search and calendar screens show times. | **Keep** | |
| AC7 | SCRUM-12, 15, 23, 32 and 61 criteria still hold. | **Clarify** | Their automated tests are updated to times and pass. SCRUM-12's operating-slot check becomes the operating-window check. |

### Decisions (Product Owner, 20 October 2026)

1. **Slot ranges:** AM = 07:00–12:00, PM = 12:00–18:00, Night = 18:00–24:00. These replace Jira's proposed 07–12 / 13–18 / 19–24. They leave no gaps, so consecutive slots become one exact range: the active AM + PM blocks on shared become 07:00–18:00 with nothing added or lost.
2. **Operating window:** one fixed 07:00–24:00 window for every venue (#131). Per-venue operating slots retire in Sprint 4, with the venue form, search and suitability. Every venue on shared already operates all three slots.
3. **Sprint split:** slice 1 in Sprint 3; the rest in Sprint 4.

### Approved criteria

- **AC1:** Given an assigned Coordinator, when they submit a booking request with a start date, an end date (equal for one day), a start time and an end time, then it is saved with those times. Each time is on a 15-minute step within 07:00–24:00 and the end is after the start; otherwise the request is refused with 422 and a reason code (`off_step`, `outside_operating_window`, `end_not_after_start`) and nothing is saved.
- **AC2:** Given an approved booking at a venue, when Venue Staff approve another booking at that venue whose dates share a day with it and whose time range overlaps it (half-open: 10:00–12:00 and 12:00–14:00 do not overlap), then approval is refused with 409 `booking_conflict` listing the approved booking, and the request stays pending. Bookings in the same old slot that do not overlap in time no longer conflict.
- **AC3:** Given an active block with a start and end time, then a booking overlapping it is not offered in search and cannot be approved (`active_block`).
- **AC4:** Venue search, the suitability check and the Venue Staff block calendar take and show dates and times, not slots.
- **AC5:** Given existing bookings and blocks, when the migration runs, then each row gets the time range of its slots (consecutive slots join into one range), keeping its id, dates, status and links. A row with non-consecutive slots stops the migration with its id.
- **AC6:** The booking, block, search and calendar screens show and accept times, not AM / PM / Night.
- **AC7:** The automated tests of SCRUM-12, 15, 23, 32 and 61 are updated to times and pass.

### Included and excluded behaviour

| | Behaviour | Where |
| --- | --- | --- |
| Slice 1 (Sprint 3) | Bookings gain `start_minute` and `end_minute`; existing bookings converted; submission takes times (AC1); approval compares bookings by time (AC2); booking conversion (AC5, bookings) | migration `0050`, venueService |
| Sprint 4 | Blocks on times (AC3), block conversion (AC5, blocks), search / suitability / calendar (AC4), screens (AC6), retiring `slots` and operating slots, full AC7 regression | |
| Excluded | Setup and turnaround padding, timing-change flags | SCRUM-20 |
| Excluded | The availability view | SCRUM-31 |
| Excluded | Mapping a change request's proposed times onto bookings | SCRUM-35 |

### Slice 1 design (contract shared with SCRUM-20 and SCRUM-35)

- **Stored fields:** `venue_booking_requests.start_minute` and `end_minute`, integers, minutes after midnight in Singapore local time (07:00 = 420, 24:00 = 1440). Both are NOT NULL and checked by the database: multiples of 15, from 420 to 1440, end after start. `start_date` and `end_date` are unchanged and inclusive; the time range applies on each date.
- **Transition:** `slots` stays for slot-based readers until Sprint 4. A trigger sets it from the times to the slots the range touches (11:00–13:00 → AM, PM). Blocks are still whole slots in slice 1, so comparing a booking's touched slots with a block gives the same answer as comparing times. Search, the calendar, block checks and block-impact notices therefore stay correct without changes.
- **API:** `POST /booking-requests` takes `start_minute` and `end_minute` instead of `slots`. Responses add both fields and keep `slots` until Sprint 4.
- **Conflict check:** `decide_venue_booking_request` remains the single authoritative check, keeping its lock order: venue row `FOR UPDATE`, then the request row. Two bookings conflict when `a.start_date <= b.end_date AND b.start_date <= a.end_date AND a.start_minute < b.end_minute AND b.start_minute < a.end_minute`. SCRUM-20 adds the venue's padding inside this function. Refusal codes and the 409 response are unchanged.
- **Migration number:** `0050` (0048 and 0049 are Heng Rui's).

### Actors and relationship permissions

Unchanged from SCRUM-32 and SCRUM-15: the Coordinator currently assigned to the event submits; Venue Staff decide.

### State transitions, persistence and atomicity

No new statuses. The approval check, the refusal record and the status change stay in one transaction under the venue lock (SCRUM-15). The conversion runs in one transaction: either every booking is converted or none is.

### Assumptions and open questions

| ID | Assumption or question | Cases |
| --- | --- | --- |
| A1 | Times are whole minutes from midnight (as SCRUM-59 and SCRUM-20 use), so 24:00 is 1440 and needs no special type. The screens show HH:MM. | AC1 |
| A2 | A multi-day booking uses the same times on each date. Different times on different days are separate bookings. | AC1, AC2 |
| A3 | During the transition a booking's derived slots may be wider than its time (11:00–13:00 shows as AM, PM) on slot-based screens until Sprint 4. | AC1-P1 |
| Q1 | SCRUM-20's helper compares single dates (`on_date`). Bookings keep date ranges (AC1), so its integration compares date ranges. To agree with Koei. | AC2 |

## Test-case matrix

### Specification (slice 1)

Times are written as HH:MM; the API and database carry minutes after midnight.

| ID | AC | Test scenario | Technique | Pre-conditions | Test steps | Test data | Expected result | Forbidden side effects | Layer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AC1-H1 | AC1 | An assigned Coordinator submits a timed booking | Happy | Venue V; Coordinator assigned to event E | POST /booking-requests | 2026-11-02, 10:00–12:00 | 201; pending; `start_minute` 600, `end_minute` 720; `slots` [AM] | — | API |
| AC1-B1 | AC1 | Window limits | Boundary | As AC1-H1 | Submit each | 07:00–08:00 and 23:45–24:00 accepted; 06:45–08:00 and 23:00–24:15 refused | 201 / 422 `outside_operating_window` | Nothing saved on 422 | API |
| AC1-B2 | AC1 | The shortest booking is one step | Boundary | As AC1-H1 | Submit each | 10:00–10:15 accepted; 10:00–10:00 and 10:15–10:00 refused | 201 / 422 `end_not_after_start` | Nothing saved on 422 | API |
| AC1-N1 | AC1 | Off the 15-minute step | Negative | As AC1-H1 | Submit each | 10:10–12:00; 10:00–11:59 | 422 `off_step` | Nothing saved | API |
| AC1-N2 | AC1 | Old or missing fields | Negative | As AC1-H1 | Submit | `slots` instead of times; no `end_minute` | 422 | Nothing saved | API |
| AC1-P1 | AC1 | Derived slots during the transition | Partition | — | Build a booking | 07:00–12:00 → AM; 11:00–13:00 → AM, PM; 17:00–19:00 → PM, NIGHT; 07:00–24:00 → AM, PM, NIGHT | As listed | — | Unit |
| AC1-X1 | AC1 | The database refuses bad times from any caller | Cross-cutting | Shared schema | Direct insert (rolled back) | 10:10–12:00; 06:45–08:00; 12:00–12:00 | Check violation (23514) for each; a valid row gets its `slots` from the trigger | No row kept | DB |
| AC2-H1 | AC2 | Back-to-back bookings both approve | Happy | Approved 10:00–12:00 on 2026-11-02 at V | Approve a pending 12:00–14:00 that day | — | Approved | No refusal recorded | API, DB |
| AC2-B1 | AC2 | One step of overlap conflicts | Boundary | As AC2-H1 | Approve 11:45–14:00 | — | 409 `booking_conflict` with the approved id; stays pending | Status unchanged; one refusal recorded | API, DB |
| AC2-P1 | AC2 | Same old slot, no time overlap | Partition | Approved 08:00–10:00 | Approve 10:00–12:00 (both AM) | — | Approved (the slot rule would have refused) | — | API, DB |
| AC2-P2 | AC2 | Dates must share a day | Partition | Approved 2026-11-02 10:00–12:00 | Approve 2026-11-03 10:00–12:00; then 2026-11-01 to 2026-11-02 at 11:00–13:00 | — | First approved; second 409 `booking_conflict` | — | API, DB |
| AC2-X1 | AC2 | Blocks still refuse by the touched slots | Cross-cutting | Active PM block on 2026-11-02 | Approve 11:00–13:00; approve 08:00–10:00 | — | 409 `active_block`; approved | — | API, DB |
| AC5-H1 | AC5 | Conversion keeps every booking | Happy | Shared bookings | Run `0050`, then read every row | AM, PM, NIGHT, AM+PM, all three | 07:00–12:00, 12:00–18:00, 18:00–24:00, 07:00–18:00, 07:00–24:00; ids, dates, status, links and slots unchanged | No row added or removed | DB |
| AC5-N1 | AC5 | Non-consecutive slots stop the conversion | Negative | — | Convert {AM, NIGHT} | — | Error naming the row; nothing converted | No partial conversion | DB |

### Existing tests that this story must change

Slice 1 replaces `slots` with times in the booking-request create payloads used by SCRUM-32, SCRUM-15 and SCRUM-61 tests. Their expected outcomes are unchanged.

## Latest execution record

Slice 1, branch `feat/scrum-65-time-model`, 20 October 2026. Windows 11, Python 3.12.

| Cases | Layer | Command | Result | Notes |
| --- | --- | --- | --- | --- |
| AC1-H1, AC1-B1, AC1-B2, AC1-N1, AC1-N2, AC1-P1, AC2-H1, AC2-B1, AC2-P1, AC2-P2, AC2-X1, AC5-H1 (model mirror), AC5-N1 (helper) | Unit / API (in-memory stores) | `pytest tests/test_booking_times.py` in `backend/venueService` | 27 passed | Red first: collection failed on the missing `slots_to_range`; after the model change AC2-P1 still failed (409, slot rule) until the approval check compared times. Then green |
| SCRUM-32, 15, 23, 61 regression | Unit / API | `pytest` in `backend/venueService` | 480 passed; `ruff check .` clean | SCRUM-32 submit cases now send times (AC1-H4, AC1-P4 to P6, AC1-N14 to N18 updated; outcomes unchanged) |
| Cross-service | Unit | `pytest` in `backend/equipmentService` | 333 passed | No change needed |
| AC1-X1, AC1-P1, AC2-H1, AC2-B1, AC2-P1, AC2-P2, AC2-X1, AC5-H1, AC5-N1 | Shared development DB, rolled back | `0050` + `verify_venue_booking_times.sql` in one transaction ending in `ROLLBACK`, via Supabase MCP | Passed; afterwards no time columns, no new functions and no test venue on shared | First run stopped at AC2-X1 because `venue_blocks.created_by` needs a real auth user (fixture fault, fixed). The verifier was written after the migration, so it has no separate Red run. `0050` is **not applied** to shared |

**Shared rollout, 20 October 2026 (Claude for Jaren):** after PR #73 merged (`a14ed6d`), `0050` was applied to shared development as `20261020113931`. Pre-check: the live `decide_venue_booking_request` matched `0024` (md5); 5 bookings, none non-consecutive. Post-check: the 5 bookings hold 07:00-12:00 (AM) or 12:00-18:00 (PM) with unchanged slots; the function bodies match the merged file; `verify_venue_booking_times.sql` (AC1-X1, AC1-P1, AC2-H1, AC2-B1, AC2-P1, AC2-P2, AC2-X1, AC5-H1, AC5-N1) passed, rolled back; `service_role`-only execute; no test rows left. No separate Red run on shared: before `0050` the verifier cannot run, because the time columns do not exist.

Not run: the frontend (unchanged in slice 1) and a browser journey.

Known flake, not from this story: `test_venue_setup_turnaround.py::test_update_changes_both_times_only` (SCRUM-59) sometimes fails on Windows because two `updated_at` values share a microsecond. It fails the same way on unchanged `dev`.
