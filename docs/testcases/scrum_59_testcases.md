# SCRUM-59 — Set a Venue's Setup and Turnaround Time

**Jira:** [SCRUM-59](https://is212g9t4.atlassian.net/browse/SCRUM-59)

**User story:** As venue staff, I want to record how long each venue needs to be set up before an event and reset after it, so that bookings leave enough time for both.

## Story contract review

The acceptance criteria were reviewed against Week 7 Customer Change #1 (*Venue Setup and Turnaround Time*), GitHub Discussions #43, #120, #123 and #131, the venue catalogue schema (`0016_venues.sql`) and the venueService code. The story owner approved this contract on 13 October 2026, choosing to follow #131 (15-minute increments) now and to leave the Product Owner and Scrum Master review of the wider 15-minute conversion for a later discussion.

| Original criterion | Outcome | Reason |
| --- | --- | --- |
| Venue staff can set and change each venue's setup and turnaround time, in the unit the customer confirms (open question: whole AM / PM / Night slots per discussion #123, or minutes). | Clarify | #131 (Professor, 9 October 2026) settles the unit: minutes in 15-minute increments. The Week 7 example (30 minutes setup, 45 minutes turnaround) agrees. |
| Staff who plan events can see these times next to the venue's other details. | Clarify | Names the actors: Event Coordinators and Venue Staff, the roles that can already read venues. |
| Changing the times doesn't change or delete existing bookings. SCRUM-20 marks any that now overlap. | Narrow | This story keeps bookings and blocks unchanged. Marking bookings that now overlap is SCRUM-20 and is not claimed here. |
| Existing venues start with no setup or turnaround time until staff set one (team proposal). | Keep | Stored as 0 minutes. |

## Increment scope

- **Included:** two venue attributes, `setup_minutes` and `turnaround_minutes`; setting them on create and changing them on update; returning them wherever a venue is returned; migration `0026_venue_setup_turnaround.sql`.
- **Excluded:** using the times in availability or conflict checks, and marking bookings that now overlap (SCRUM-20); converting bookings, blocks and operating slots from AM / PM / Night to 15-minute times (a separate backlog item, #131). Bookings and blocks remain slot-based until that item is done.
- **Actors and access:** only Venue Staff can create a venue or change its times (403 otherwise). Event Coordinators and Venue Staff can read them (existing venue read access). Browser roles still have no direct table access.
- **Persistence:** both columns are `integer NOT NULL DEFAULT 0` with a check constraint; the API applies the same rule and returns 422 before anything is stored.
- **Team proposals:** values are 0 to 1020 minutes (the 07:00–24:00 operating window from #131) in 15-minute steps; 0 means none and the UI shows "None"; existing venues start at 0.
- **Hand-off to SCRUM-20:** a booking occupies `start − setup_minutes` to `end + turnaround_minutes` (Week 7 example: 10:00–12:00 with 30 / 45 occupies 09:30–12:45); after a venue's times change, existing bookings that now conflict are identified, not removed (#120). Open question for SCRUM-20: setup that would start before 07:00.

## Acceptance criteria

- **AC1:** Given a venue, when Venue Staff create it or change it with a setup time and a turnaround time, then both are saved in minutes. Each must be a multiple of 15 from 0 to 1020; any other value, a non-number or `null` returns 422 and changes nothing. A caller who is not Venue Staff gets 403 and nothing changes.
- **AC2:** Given a venue, when an Event Coordinator or Venue Staff member reads it (venue detail, venue list or venue search), then its setup and turnaround times are shown with its other details.
- **AC3:** Given a venue with existing booking requests and blocks, when Venue Staff change its setup or turnaround time, then those booking requests and blocks are unchanged.
- **AC4:** Given a venue whose times were never set (created before this story, or created without them), when it is read, then both times are 0.

## Test-case specification

| ID | AC | Test scenario | Technique | Pre-conditions | Test steps | Test data | Expected result | Forbidden side effects | Layer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AC1-H1 | AC1 | Venue Staff create a venue with both times | Happy | Signed in as Venue Staff | `POST /venues` with both times | 30, 45 | 201; body and stored venue have 30 and 45 | — | API |
| AC1-H2 | AC1 | Venue Staff change both times | Happy | Venue with 30 / 45 | `PATCH /venues/{id}` | 0, 15 | 200; times are 0 and 15; other attributes unchanged; `updated_at` advances | — | API |
| AC1-P1 | AC1 | Changing one time keeps the other | Partition | Venue with 30 / 45 | `PATCH` setup only; then turnaround only | 60; 90 | Only the sent field changes | The other time unchanged | API |
| AC1-B1 | AC1 | Valid values at and next to the limits | Boundary | Signed in as Venue Staff | Create with each value as setup and as turnaround | 0, 15, 1005, 1020 | 201; value stored | — | API + unit |
| AC1-N1 | AC1 | Out-of-range and off-step values are refused | Negative / Boundary | Signed in as Venue Staff | Create with each value | -15, -1, 1, 14, 20, 1021, 1035 | 422 | No venue stored | API + unit |
| AC1-N2 | AC1 | Non-numbers and `null` are refused on update | Negative | Venue with 30 / 45 | `PATCH` with each value | `"thirty"`, `null`, `20` | 422 | Venue unchanged | API |
| AC1-X1 | AC1 | Only Venue Staff can set or change the times | Cross-cutting | Venue with 30 / 45 | `PATCH` as Event Coordinator, Event Organiser, Attendee | 60, 60 | 403 | Venue unchanged | API |
| AC1-H3 | AC1 | The database store sends and reads the times | Happy | Fake Supabase Data API | Create; update setup only | 30 / 45; 60 | Insert body has both; PATCH body has `setup_minutes` only; rows parse to the model | — | Unit |
| AC2-H1 | AC2 | Coordinators see the times wherever a venue is read | Happy | Venue with 30 / 45; signed in as Event Coordinator | `GET /venues/{id}`, `GET /venues`, `GET /venues/search` | — | Each response has `setup_minutes` 30 and `turnaround_minutes` 45 | — | API |
| AC3-H1 | AC3 | Changing the times leaves bookings and blocks alone | Happy | Venue with an approved request, a pending request and an active block | `PATCH` both times | 60, 60 | 200 | Both requests and the block are identical before and after | API |
| AC4-H1 | AC4 | A venue created without the times starts at 0 | Happy | Signed in as Venue Staff | `POST /venues` without either time | — | 201; both 0 | — | API |
| AC4-DB1 | AC1, AC4 | The migration defaults existing venues and enforces the rule | Happy / Negative | Throwaway `postgres:16-alpine` with 0016 and an existing venue row | Apply 0026 twice; update the row | 30 / 45; 20; -15; 1035 | Existing row reads 0 / 0; 30 / 45 accepted; 20, -15 and 1035 refused by the check constraints | Re-run raises no error | DB |

Frontend cases (form, display and end-to-end) are added with the frontend increment.

## Latest execution record

Build: backend increment as an uncommitted working tree on `feat/scrum-59-venue-setup-turnaround` at `11dae05` (13 October). Executed with Claude Code, pending human review. Frontend cases are not executed yet.

| ID | Automation status | Actual result | Execution status | Build or commit | Executed by and date | Remarks and evidence |
| --- | --- | --- | --- | --- | --- | --- |
| AC1-H1, AC1-H2, AC1-P1 | Green | Create stores 30 / 45; update to 0 / 15 changes only the times and advances `updated_at`; a one-field update keeps the other time | Pass | 11dae05 + working tree, local | Claude Code, 13 Oct 2026 | Red first (`KeyError: 'setup_minutes'`), then Green: `tests/test_venue_setup_turnaround.py` |
| AC1-B1, AC1-N1 | Green | 0, 15, 1005, 1020 accepted for both fields; -15, -1, 1, 14, 20, 1021, 1035 refused with 422 and no venue stored | Pass | same | same | Red first (201 instead of 422), then Green |
| AC1-N2 | Green | `"thirty"`, `null` and 20 on update return 422; venue unchanged | Pass | same | same | Red first (200 instead of 422), then Green |
| AC1-X1 | Green | Event Coordinator, Event Organiser and Attendee get 403; venue unchanged | Pass | same | same | Passed before the change: `PATCH /venues/{id}` was already Venue Staff only. Kept as a guard |
| AC1-H3 | Green | Supabase store inserts both times, PATCH sends only `setup_minutes` and `updated_at`, rows parse with the times | Pass | same | same | Fake Data API, no network |
| AC2-H1 | Green | Event Coordinator sees 30 / 45 on detail, list and search | Pass | same | same | Red first (`KeyError`), then Green |
| AC3-H1 | Green | Approved and pending requests and the active block are identical before and after the update | Pass | same | same | Also passed before the change, because unknown fields were ignored; meaningful once the fields exist |
| AC4-H1 | Green | A venue created without the times reads 0 / 0 | Pass | same | same | Red first (`KeyError`), then Green |
| AC4-DB1 | Green | Before 0026 the script stopped at the first read of the new columns (Red); 0026 applied twice without error; the pre-existing venue reads 0 / 0; 30 / 45, 0 and 1020 stored; 20, -15 and 1035 refused; all rolled back | Pass | same | same | Throwaway `postgres:16-alpine` with 0016 and one existing venue; `database/verify_venue_setup_turnaround.sql` |

### Local validation evidence

| Check | Command and environment | Result | Remarks |
| --- | --- | --- | --- |
| Story tests | `pytest tests/test_venue_setup_turnaround.py` in `python:3.12-slim` | 39 passed | Before the change: 35 failed, 4 passed (AC1-X1 × 3, AC3-H1) |
| Backend regression | `pytest` (whole venueService suite) in `python:3.12-slim` | 399 passed | Includes SCRUM-12, 15, 23, 30 and 32 tests |
| Lint | `ruff check .` in `python:3.12-slim` | All checks passed | — |
| Database | `postgres:16-alpine` throwaway container; 0016, 0026 (twice); `verify_venue_setup_turnaround.sql` | Passed | Not yet applied to shared development |

Shared development, browser, pull-request CI and reviewer approval: not yet run.
