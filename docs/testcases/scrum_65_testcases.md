# SCRUM-65 Test Cases: Book Venues in 15-Minute Increments

Last reviewed: 20 October 2026

Status: **contract approved by the story owner and Product Owner (Jaren) on 20 October 2026**, with the decisions below. Slice 1 is merged (PR #73) and applied to shared (`0050`). Slice 2 (blocks, search, suitability, calendar, screens) is on `feat/scrum-65-blocks-search-screens`.

## Story

| Field | Value |
| --- | --- |
| Jira key | SCRUM-65 |
| Title | Book Venues in 15-Minute Increments |
| Sprint | Sprint 3 (ends 22 October 2026): slice 1, and slice 2 pulled forward by the Product Owner on 20 October 2026 |
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
3. **Sprint split:** slice 1 in Sprint 3; the rest in Sprint 4. **Changed 20 October 2026 (Product Owner):** slice 2 is pulled into Sprint 3 as well.
4. **SCRUM-31's calendar stays on slots** (Kai Jie's story): its slot states read the derived `slots` column. Its "Not offered" state still follows the venue's old operating slots, which no longer limit booking or search; Kai Jie to decide how the calendar moves to times.

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

Not run: the frontend (unchanged in slice 1) and a browser journey.

Known flake, not from this story: `test_venue_setup_turnaround.py::test_update_changes_both_times_only` (SCRUM-59) sometimes fails on Windows because two `updated_at` values share a microsecond. It fails the same way on unchanged `dev`.

## Slice 2: blocks, search, suitability, calendar and screens

### Design

- **Database `0051_venue_block_times.sql`:** `venue_blocks.start_minute` and `end_minute` with the same checks as bookings; existing blocks convert with the slice 1 ranges (a non-consecutive block stops the migration); `0050`'s trigger keeps `slots` derived. `create_venue_block` takes the times instead of slots (same venue lock, `service_role` only). `decide_venue_booking_request` compares blocks by time and no longer refuses on the venue's operating slots (decision 2); `outside_operating_slots` stays an allowed code for old refusals.
- **venueService:** blocks are created with times (422 codes as in AC1, `slots` refused); approval, block alerts, `POST /venues/{id}/availability` and search compare by date and time. Search takes `date`, `start_minute`, `end_minute` (times need a date: `date_required`, `times_incomplete`); with only a date, a venue needs some free time in 07:00-24:00. Suitability takes `required_start_minute` / `required_end_minute` (422 when invalid); the `operating_slot` mismatch is retired. Decision and block notices add the time ranges.
- **Frontend:** a shared start/end time picker (15-minute steps, 07:00-24:00). The block form, search and suitability check use it; the block list, the Venue Staff calendar (one row per date listing blocked and booked times), booking lists, the coordinator's bookings panel, the Safety Officer page and notifications show times (older notices without times still show their slots). The venue form no longer edits operating slots.

### Specification (slice 2)

| ID | AC | Test scenario | Technique | Expected result | Layer |
| --- | --- | --- | --- | --- | --- |
| AC3-H1 | AC3 | Venue Staff block 12:30-14:00 | Happy | 201; times stored; `slots` [PM] | API, DB |
| AC3-N1 | AC3 | Off step, outside 07:00-24:00, end not after start | Negative | 422 with the code; nothing stored | API, DB |
| AC3-N2 | AC3 | The retired `slots` field | Negative | 422 | API |
| AC3-B1 | AC3 | Booking 11:00-12:45 vs block 12:30-14:00; 11:00-12:30; 14:00-15:00 | Boundary | `active_block`; approved; approved | API, DB |
| AC3-H2 | AC3 | Search a blocked time and a later time that day | Happy | Not offered; offered | API |
| AC3-X1 | AC3 | A new block alerts only time-overlapping approved bookings | Cross-cutting | One notice, with both time ranges | API, unit |
| AC4-H1 | AC4 | Search around an approved booking; a pending one | Happy | Overlap hidden; adjacent and pending-only offered | API |
| AC4-B1 | AC4 | Date-only search: 07:00-24:00 fully taken vs 15 minutes free | Boundary | Hidden; offered | API |
| AC4-B2 | AC4 | Venue Staff calendar day: full-day block, blocks meeting end to end, 15 minutes free at either end or between, none | Boundary | "No free time" only when 07:00-24:00 is fully covered; otherwise "Other times available" | Unit (`__tests__/block-calendar.test.ts`) |
| AC4-N1 | AC4 | Invalid search times; times without a date | Negative | 422 with the code | API, unit |
| AC4-H2 | AC4 | Availability check reports the overlapping part in time | Happy | Block 12:30-14:00 and booking 12:00-13:00 parts | API |
| AC4-P1 | AC4 | A free time | Partition | Available, no reasons | API |
| AC4-H3, AC4-N2 | AC4 | Suitability with a valid time; invalid or partial time; old slot field | Happy, negative | 200 suitable; 422 | API, unit |
| AC4-P3 | AC4 | A PM-time booking at a venue whose old operating slots are AM only | Partition | Approved (fixed window) | DB |
| AC5-H2 | AC5 | Existing blocks hold their slots' range | Happy | No mismatches | DB |
| AC6-H1, AC6-B1, AC6-H2, AC6-N1 | AC6 | Time labels, 15-minute choices, form parsing and its messages | Happy, boundary, negative | As in `__tests__/time-range.test.ts` | Unit |

### Existing tests changed (AC7)

Converted from slots to the times they stand for (AM 07:00-12:00, PM 12:00-18:00, NIGHT 18:00-24:00) with outcomes unchanged, through `tests/time_support.py`: SCRUM-23 (`test_block_*`, `test_venue_blocks.py`), SCRUM-15 (`test_booking_decision*`, `test_booked_availability.py`), SCRUM-12 (`test_suitability.py`, `test_venues_suitability.py`), SCRUM-31 (`test_venue_calendar.py`, block helper only), SCRUM-59, SCRUM-60 and the frontend tests of the same screens. Cases whose rule changed by decision 2 now assert the new rule and say so: SCRUM-15 AC5-P2 and AC5-P4b, SCRUM-23 AC2-P5, P6, P7 and P9, SCRUM-12 AC3-P6 to P8 and AC3-X1, and the SCRUM-31 cross-check, which leaves out a partial-hours venue until its calendar moves to times.

### Execution record (slice 2, 20 October 2026, Windows 11)

| Layer | Command | Result | Notes |
| --- | --- | --- | --- |
| venueService | `pytest`, `ruff check .` | 548 passed; clean | Red first: 21 of the 25 new cases failed before the change (the other 4 refused for other reasons) |
| equipmentService | `pytest` | 333 passed | |
| Frontend unit | `npm test`, `npm run typecheck`, `npm run lint` | 419 passed; clean | Red first: the 8 time-helper cases failed before `venue-options.ts` had them |
| Frontend browser | `npm run test:e2e` (mock services) | 45 passed | The mock venue API mirrors the time rules |
| Frontend build | `npm run build` | Passed | |
| Shared database | `0051` + `verify_venue_block_times.sql` + `verify_venue_booking_times.sql`, rolled back | **Not run yet** | The MCP declined the dry run (it contains `DROP FUNCTION` and `UPDATE`) and needs the owner's confirmation. `0051` is not applied |

### Integrated real-app check (20 October 2026, Windows 11)

Local stack (`docker compose up --build`, `npm --prefix frontend run dev`) against shared development after `0051`, signed in as the seeded Venue Staff account, on the `KOEI BLOCK TEST` venue.

| Step | Result |
| --- | --- |
| Calendar shows the converted existing blocks | Passed: 4-5 Oct 07:00-18:00, 14-22 Oct 07:00-24:00 |
| Block 28 Oct 2026, 12:30-14:00, Maintenance | Passed: created, listed as "28 Oct 2026 · 12:30-14:00 · Maintenance · Active", calendar row 12:30-14:00 Blocked |
| Search 28 Oct, 12:00-13:00 | Passed: venue not offered |
| Search 28 Oct, 14:00-15:00 (adjacent) | Passed: venue offered |
| Fully blocked day label | **Failed, fixed (AC4-B2):** 07:00-24:00 days said "Other times available"; now "No free time". Rechecked in the browser after the fix |

The 28 Oct test block remains on `KOEI BLOCK TEST` (no lift action in the app).
