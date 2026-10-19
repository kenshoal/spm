# SCRUM-20 — Detect Venue Booking Conflicts

**Jira:** [SCRUM-20](https://is212g9t4.atlassian.net/browse/SCRUM-20)

**User story:** As a Venue Staff member, I want the system to detect overlapping or incompatible venue bookings, so that a venue is never double-booked.

## Story contract review

The acceptance criteria (as reworded on 18 October 2026 for the 15-minute booking unit) were reviewed against Week 7 Customer Change #1 (*Venue Setup and Turnaround Time*), GitHub Discussions #120 and #131, the change impact analysis for the 15-minute unit (18 October 2026), SCRUM-59 (`0043_venue_setup_turnaround.sql`), SCRUM-15 (`0024_venue_booking_decisions.sql`) and SCRUM-64 (`arrangement_reviews`). The Product Owner (Jaren) approved the outcomes below on 19 October 2026. The AC6 design was agreed with Heng Rui (SCRUM-64 owner) on 19 October 2026. On 20 October 2026 the Product Owner confirmed the padding rule, which bookings AC6 flags, and that bookings which have already ended are not flagged.

| Original criterion | Outcome | Reason |
| --- | --- | --- |
| Given a booking or hold request for a venue and time that overlaps an existing hold or confirmed booking, when submitted, then the system blocks it and reports the conflict. | Narrow → AC1 | Only approved bookings count, as in SCRUM-15. Holds are out of scope until SCRUM-18 exists. |
| Overlap is evaluated on time ranges in 15-minute steps within the 07:00–24:00 operating window. | Keep → AC2 | Storing bookings as times is SCRUM-65. |
| Conflict detection respects the venue's recorded setup/turnaround requirements between consecutive events. | Clarify → AC3 | Each booking occupies its start minus setup to its end plus turnaround; padded ranges must not overlap. Padding stays inside the operating window (PO decision). |
| The system prevents incompatible overlaps rather than only warning. | Merge → AC1 | AC1 already blocks the request. |
| (change) Given an event change/reschedule moves it onto an already-booked time, when applied, then the conflict is detected and the change cannot be confirmed until resolved. | Narrow → AC4 | SCRUM-20 provides the check; SCRUM-35's change flow calls it. SCRUM-35's change decisions are still deferred. |
| (boundary) Given two consecutive bookings separated by less than the venue's turnaround time, when the second is requested, then it is flagged as conflicting. | Clarify → AC5 | The required gap is turnaround plus setup; a gap exactly equal to it is allowed. |
| *(new)* Bookings affected by a venue setup or turnaround change. | Add → AC6 | SCRUM-59 handed this to SCRUM-20 ("SCRUM-20 marks any that now overlap"); Q&A #120 and Week 7 Change #1 require affected bookings to be identified, not removed. Reuses SCRUM-64's review flag. |

## Increment scope

- **Sprint 3 increment (this branch):** the conflict rules as a pure venueService module with unit tests: valid booking times, padded ranges, overlap, finding conflicts, the reschedule check and the bookings affected by a timing change. No database, endpoint, frontend or slot code changes.
- **Sprint 4 (after SCRUM-65):** applying the rules in booking approval (`0024` approval function) and submission, in availability and dated search, the SCRUM-35 hookup (also blocked by SCRUM-35), AC6 storage, flags and notifications, and the frontend messages. The story carries into Sprint 4 and is not Done until then.
- **Excluded:** holds (SCRUM-18); the event change flow (SCRUM-35); storing bookings and blocks as times and converting existing rows (SCRUM-65); block overlap rules (SCRUM-23, moving to times in SCRUM-65).
- **Dependencies:** SCRUM-65 (bookings as times) for every AC in use; SCRUM-64 (merged 19 October 2026) for AC6 flags; SCRUM-35 for AC4 wiring.
- **Actors and access:** unchanged from SCRUM-15 and SCRUM-59. Venue Staff decide booking requests and change venue times; Event Coordinators submit requests and receive notices.
- **Rules:**
  - A booking is one date with a start and an end time (SCRUM-65 AC1), in Singapore local time.
  - Times fall on 15-minute steps from 07:00 to 24:00, and the end is after the start.
  - Setup and turnaround are the venue's (SCRUM-59), so both bookings at a venue use the same values.
  - Ranges are half-open: a range ending at 12:00 and one starting at 12:00 do not overlap.
  - Only approved bookings conflict. Pending, rejected and cancelled (SCRUM-61) requests never do.
- **AC6 design (agreed with Heng Rui):** each saved timing change gets its own record (venue, old and new setup and turnaround, actor, time) with a UUID used as `trigger_id`, and `trigger_type = 'venue_timing_change'` in `arrangement_reviews`. New migrations only. The existing `arrangement_needs_review` notice is kept and checked for both the Event Coordinator and Venue Staff. The timing update, change record, flags and notification jobs are saved atomically; an unchanged save creates nothing and a retry creates no duplicates. Booking approvals, event statuses and existing review records are unchanged. Heng Rui reviews compatibility. If AC6 cannot be built before 22 October it moves to Sprint 4 with SCRUM-65 (PO).
- **Decisions (Product Owner, 20 October 2026):**
  - Setup and turnaround padding must stay inside 07:00–24:00. This is a team decision, not confirmed with the customer, and can be relaxed if the customer rules otherwise.
  - AC6 flags both bookings of each newly conflicting pair, because either Event Coordinator may need to move, plus any booking whose new padding falls outside the window (Q&A #120: identify for review and notify, do not cancel).
  - AC6 does not flag bookings that have already ended (date before today), the same rule SCRUM-23 uses for block alerts. Only approved bookings that have not ended are considered.
- **Open question:** how SCRUM-65 converts multi-day and multi-slot bookings is not yet decided. The rules here work per date.

## Acceptance criteria

- **AC1 (conflict):** Given an approved booking for a venue, when another booking request for that venue overlaps it, then the system blocks the request and reports the conflicting booking. Only approved bookings count; pending, rejected and cancelled requests never conflict. The system prevents the overlap rather than only warning.
- **AC2 (time ranges):** Overlap is evaluated on start and end times in 15-minute steps within the 07:00–24:00 operating window.
- **AC3 (setup and turnaround):** Given a venue with setup and turnaround times (SCRUM-59), each booking occupies the venue from its start minus setup to its end plus turnaround, and two bookings conflict if these padded ranges overlap. Padding must also stay within 07:00–24:00.
- **AC4 (change):** Given an event change or reschedule that moves a booking onto a time that conflicts under AC1–AC3, then the conflict is reported and the change cannot be confirmed until resolved. SCRUM-20 provides the check; SCRUM-35's change flow calls it.
- **AC5 (boundary):** Given two consecutive bookings, when the gap between them is less than the venue's turnaround plus setup, then the second is flagged as conflicting. A gap exactly equal to it is allowed.
- **AC6 (venue timing change):** Given Venue Staff change a venue's setup or turnaround time, when existing approved bookings at that venue that have not yet ended now conflict, then both bookings of each newly conflicting pair, and any booking whose new padding falls outside 07:00–24:00, are flagged for review, and their Event Coordinators and Venue Staff are notified. Bookings that ended before today are not flagged. No booking, approval or event status is changed or removed. The update, change record, flags and notifications are saved together; an unchanged save creates nothing and a retry creates no duplicates.

## Test-case specification

### Sprint 3: conflict rules (unit)

Times below are on one date at one venue unless stated. "30 / 45" means setup 30 minutes, turnaround 45 minutes.

| ID | AC | Test scenario | Technique | Pre-conditions | Test steps | Test data | Expected result | Forbidden side effects | Layer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AC2-H1 | AC2 | A booking on 15-minute steps inside the window is valid | Happy | — | Validate the time | 10:00–12:00 | Valid | — | Unit |
| AC2-B1 | AC2 | Window limits | Boundary | — | Validate each time | 07:00–08:00, 23:45–24:00 valid; 06:45–08:00, 23:00–24:15 refused | As listed; the refusal names the window | — | Unit |
| AC2-B2 | AC2 | The shortest booking is one step | Boundary | — | Validate | 10:00–10:15 valid; 10:00–10:00 and 10:15–10:00 refused | As listed | — | Unit |
| AC2-N1 | AC2 | Off-step times are refused | Negative | — | Validate | 10:10–12:00; 10:00–11:05 | Refused; the refusal names the 15-minute step | — | Unit |
| AC3-H1 | AC3 | The Week 7 example | Happy | Venue 30 / 45 | Pad the booking | 10:00–12:00 | Occupies 09:30–12:45 | — | Unit |
| AC3-P1 | AC3 | No setup or turnaround leaves the time as booked | Partition | Venue 0 / 0 | Pad | 10:00–12:00 | Occupies 10:00–12:00 | — | Unit |
| AC3-B1 | AC3 | Setup must stay inside the window | Boundary | Venue 30 / 0 | Validate the padded booking | 07:30–09:00 valid; 07:15–09:00 refused | As listed; the refusal names the setup | — | Unit |
| AC3-B2 | AC3 | Turnaround must stay inside the window | Boundary | Venue 0 / 45 | Validate the padded booking | 22:00–23:15 valid; 22:00–23:30 refused | As listed; the refusal names the turnaround | — | Unit |
| AC3-H2 | AC1, AC3 | Padding creates a conflict the booked times alone would not | Happy | Venue 30 / 45; approved A 10:00–12:00 | Check request B | 12:15–13:00 | Conflict with A | — | Unit |
| AC1-H1 | AC1 | An overlapping approved booking is a conflict | Happy | Venue 0 / 0; approved A 10:00–12:00 | Check request | 11:00–13:00 | Conflict listing A | — | Unit |
| AC1-H2 | AC1 | A free time has no conflict | Happy | Venue 0 / 0; approved A 10:00–12:00 | Check request | 13:00–14:00 | No conflicts | — | Unit |
| AC1-H3 | AC1 | Every clashing booking is reported, in start order | Happy | Venue 0 / 0; approved A 09:00–10:00, B 11:00–12:00, C 14:00–15:00 | Check request | 09:30–11:30 | Conflicts A, B (not C) | — | Unit |
| AC1-P1 | AC1 | Only approved bookings count | Partition | Venue 0 / 0; one pending, one rejected, one cancelled request at 10:00–12:00 | Check request | 10:00–12:00 | No conflicts | — | Unit |
| AC1-P2 | AC1 | Other venues and other dates never conflict | Partition | Approved 10:00–12:00 at another venue; approved 10:00–12:00 at this venue on the next day | Check request | 10:00–12:00 | No conflicts | — | Unit |
| AC1-B1 | AC1 | Touching bookings do not overlap; one step of overlap does | Boundary | Venue 0 / 0; approved A 10:00–12:00 | Check requests | 12:00–13:00; 11:45–13:00 | No conflict; conflict with A | — | Unit |
| AC5-B1 | AC5 | A gap equal to turnaround plus setup is allowed; one step less is not | Boundary | Venue 30 / 45; approved A 10:00–12:00 | Check requests | 13:15–14:00 (gap 75); 13:00–14:00 (gap 60) | No conflict; conflict with A | — | Unit |
| AC5-B2 | AC5 | The same boundary applies before an existing booking | Boundary | Venue 30 / 45; approved A 14:00–15:00 | Check requests | 11:00–12:45 (gap 75); 11:00–13:00 (gap 60) | No conflict; conflict with A | — | Unit |
| AC5-P1 | AC5 | Turnaround only, and setup only | Partition | Venue 0 / 45, then 30 / 0; approved A 10:00–12:00 | Check requests | 0 / 45: 12:45 allowed, 12:30 conflicts; 30 / 0: 12:30 allowed, 12:15 conflicts | As listed | — | Unit |
| AC4-H1 | AC4 | Moving a booking onto a booked time reports the conflict | Happy | Venue 0 / 0; approved A 10:00–12:00 and B 14:00–15:00 | Check B moved | 11:00–12:00 | Conflict with A | — | Unit |
| AC4-P1 | AC4 | A booking never conflicts with itself | Partition | Venue 0 / 0; approved B 14:00–15:00 | Check B moved | 14:00–16:00 | No conflicts | B not reported against itself | Unit |
| AC4-H2 | AC4 | Moving to a free time is allowed | Happy | Venue 0 / 0; approved A 10:00–12:00 and B 14:00–15:00 | Check B moved | 16:00–17:00 | No conflicts | — | Unit |
| AC6-H1 | AC6 | Raising turnaround finds bookings that now conflict | Happy | Venue 0 / 0; approved A 10:00–12:00, B 12:30–14:00, C 16:00–17:00 | Change to 0 / 45 | — | A and B affected; C not | — | Unit |
| AC6-P1 | AC6 | An unchanged save affects nothing | Partition | Venue 30 / 45 with approved bookings | Change to 30 / 45 | — | Nothing affected | — | Unit |
| AC6-P2 | AC6 | Lowering the times affects nothing | Partition | Venue 30 / 45; approved A 10:00–12:00, B 13:15–14:00 | Change to 0 / 0 | — | Nothing affected | — | Unit |
| AC6-P3 | AC6 | Only newly conflicting bookings are affected | Partition | Venue 0 / 30; approved A 10:00–12:00, B 12:15–13:00 (already conflicting), C 13:30–14:00 | Change to 0 / 45 | — | B and C affected (B now clashes with C); A–B already conflicted and is not counted again | — | Unit |
| AC6-B1 | AC6 | A booking pushed outside the window by new padding is affected | Boundary | Venue 0 / 0; approved A 07:00–08:00 | Change to 30 / 0 | — | A affected | — | Unit |
| AC6-P4 | AC6 | Only approved bookings are considered | Partition | Venue 0 / 0; pending request 10:00–12:00 and approved A 12:15–13:00 | Change to 0 / 45 | — | Nothing affected | — | Unit |
| AC6-B2 | AC6 | Bookings that have already ended are not flagged; today's still are | Boundary | Today is 20 Oct; venue 0 / 0; approved A 10:00–12:00 and B 12:30–14:00 on 19 Oct; approved C 10:00–12:00 and D 12:30–14:00 on 20 Oct | Change to 0 / 45 | — | C and D affected; A and B not | — | Unit |

### Sprint 4: applying the rules (planned, after SCRUM-65)

Designed in detail when SCRUM-65's time model is merged. Planned coverage:

- **AC1, AC3, AC5 (API + DB):** approval refuses a padded overlap with `booking_conflict` and the conflicting IDs, records the refusal and leaves the request pending; two concurrent approvals of overlapping requests cannot both succeed; submission refuses a conflicting request.
- **AC2, AC3 (API):** availability and dated search treat padded times as taken.
- **AC4 (API):** SCRUM-35's change flow refuses a conflicting reschedule through the check.
- **AC6 (API + DB):** the timing update, change record, flags and notification jobs are atomic; an unchanged save writes nothing; a retry creates no duplicate flags or notices; the Event Coordinator and Venue Staff both receive `arrangement_needs_review`; bookings, approvals, event statuses and existing review records are unchanged; non-Venue-Staff callers get 403.
- **E2E:** a refused approval explains the clash, including setup and turnaround; flagged bookings appear for review.

## Latest execution record

Build: Sprint 3 increment (conflict rules) as an uncommitted working tree on `feat/scrum-20-venue-booking-conflicts` at `29e535b` (20 October). Executed with Claude Code, pending human review. Code: `backend/venueService/app/time_conflicts.py`; tests: `backend/venueService/tests/test_time_conflicts.py`.

| ID | Automation status | Actual result | Execution status | Build or commit | Executed by and date | Remarks and evidence |
| --- | --- | --- | --- | --- | --- | --- |
| AC2-H1, AC2-B1, AC2-B2, AC2-N1 | Green | 10:00–12:00, 07:00–08:00, 23:45–24:00 and 10:00–10:15 valid; 06:45 and 24:15 refused `outside_operating_window`; equal or reversed times refused `end_not_after_start`; 10:10 and 11:05 refused `off_step` | Pass | 29e535b + working tree, local | Claude Code, 20 Oct 2026 | `check_booking_time` |
| AC3-H1, AC3-P1, AC3-B1, AC3-B2, AC3-H2 | Green | 10:00–12:00 with 30 / 45 occupies 09:30–12:45; 0 / 0 leaves it unchanged; 07:30 start with 30 setup valid, 07:15 refused `setup_outside_window`; 23:15 end with 45 turnaround valid, 23:30 refused `turnaround_outside_window`; 12:15 request conflicts with 10:00–12:00 only when padded | Pass | same | same | `padded_range`, `check_booking_time`, `find_conflicts` |
| AC1-H1, AC1-H2, AC1-H3, AC1-P1, AC1-P2, AC1-B1 | Green | Overlap reported; free time clear; several conflicts returned in start order; pending, rejected and cancelled ignored; other venues and dates ignored; touching at 12:00 clear, 11:45 conflicts | Pass | same | same | `find_conflicts` |
| AC5-B1, AC5-B2, AC5-P1 | Green | With 30 / 45, a 75-minute gap is allowed and 60 conflicts, after and before an existing booking; turnaround-only and setup-only boundaries hold | Pass | same | same | `find_conflicts` |
| AC4-H1, AC4-P1, AC4-H2 | Green | A moved booking conflicts with another booking, never with itself, and a free time is clear | Pass | same | same | `find_conflicts(..., exclude_id=...)` |
| AC6-H1, AC6-P1, AC6-P2, AC6-P3, AC6-P4, AC6-B1, AC6-B2 | Green | Raising turnaround returns both bookings of the new pair; unchanged and lowered times return nothing; an already-conflicting pair is not counted again; pending ignored; a 07:00 booking pushed outside the window by 30 setup is returned; yesterday's bookings ignored, today's returned | Pass | same | same | `affected_by_timing_change` |

### Local validation evidence

| Check | Command and environment | Result | Remarks |
| --- | --- | --- | --- |
| Story tests | `pytest tests/test_time_conflicts.py` in `python:3.12-slim` | 37 passed (30 tests, 28 case IDs) | Red first: collection failed because `app.time_conflicts` did not exist. The Red was at module level, not per case |
| Backend regression | `pytest` (whole venueService suite) in `python:3.12-slim` | 490 passed | No existing code changed |
| Lint | `ruff check .` | All checks passed | — |

Not yet run: database, API, frontend and pull-request CI (Sprint 4, after SCRUM-65).
