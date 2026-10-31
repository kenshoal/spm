# SCRUM-18 — Place a Tentative Venue Hold

**Jira:** [SCRUM-18](https://is212g9t4.atlassian.net/browse/SCRUM-18)

**User story:** As an Event Coordinator, I want to place a tentative hold on a venue while an event is being finalised, so that the space is protected before the booking is confirmed.

## Story contract review

The acceptance criteria were updated on 23 October 2026 for Week 7 Customer Change #4 (*Tentative Venue Holds Expire*: each hold has an expiry, the venue becomes available afterwards, the coordinator is informed before or when it expires, and an expired hold is never a confirmed booking). The PO's review proposed the six criteria below; the 7-day maximum, the 24-hour reminder and the conversion behaviour are team design proposals agreed with the PO (discussion #39 left duration to the team).

| Jira criterion | Outcome | Reason |
| --- | --- | --- |
| (place) The assigned coordinator holds a venue before confirmation, in 15-minute times, with an expiry at most 7 days ahead. | Keep → AC1 | "Before the event is confirmed" is implemented as **Approved, Planning or Safety Review**: venues are identified and requested after the request is approved (briefing steps 5–7), and holds stay out of the request-review page. |
| (conflict) An active, unexpired hold prevents overlapping holds and booking approvals with the same padding; check and write together. | Keep → AC2 | Also event reschedules (SCRUM-35, 0059): the shared guard reports holds to every caller, and eventRequestService returns `hold_conflict` as booking-conflict evidence. A hold never blocks its own event's bookings (Heng Rui's review, 30 October). |
| (expiry) At or after expiry a hold stops protecting and cannot be converted or treated as a booking, even before cleanup. | Keep → AC3 | One rule everywhere: active, unexpired, and the event not Cancelled or Rejected (PO decision 3 below). |
| (notice) 24 hours before (or at once) and on expiry, each sent once even if retried. | Keep → AC4 | Fixed `event_id` per hold and kind; notificationService stores one per recipient and event_id; a notice is recorded only after delivery. |
| (release and convert) Release frees the time; convert creates a pending request through Venue Staff, protected until decided or expired, not conflicting with its own hold. | Keep → AC5 | Approval ends the hold as `converted`, rejection as `released`. |
| (availability) Calendar shows "tentatively held", distinct from booked; expired and released holds do not block. | Keep → AC6 | Calendar precedence blocked > booked > held, and held time is not free (agreed with Kennedy, SCRUM-69). Search keeps excluding blocked and booked venues and returns a venue free except for holds as "Tentatively held"; the availability check reports `hold_conflict`. |

## Product Owner decisions (30 October 2026)

1. **Holds only while the event is Approved, Planning or in Safety Review.** This matches "before the event is confirmed", keeps SCRUM-17's review page read-only and is the window in which a coordinator is assigned.
2. **Notices go to the event's current coordinator**, the latest assignment, as SCRUM-38 and SCRUM-19 use. The same rule applies to release and convert: a reassigned coordinator can act on the hold and the previous one cannot.
3. **A hold of a Cancelled or Rejected event stops protecting at once**, not after up to 7 days. The guard reads the event's status with the hold (no trigger writes to holds), so the lock order stays venue, hold, event. No notice is sent for it.

Also from Heng Rui's review (30 October): an event's own hold, converted or not, never blocks that event's approval or reschedule. The guard skips holds of every event that owns a booking in `p_exclude_ids`.

## Increment scope

- **Included:** migration `0066_venue_holds.sql` (table, guard, approval, place/release/convert, sweep and notice record); venueService hold store, endpoints, expiry sweep and notices; holds in search (`tentatively_held`), the availability check, the calendar and memory-mode approval; the coordinator's holds panel, calendar state, search label, refusal and notification text; a SCRUM-18 database job in Backend CI.
- **Excluded:** Venue Staff placing holds (the ticket's actor is the coordinator); a hold for several venues at once (one hold per venue, as bookings).
- **Dependencies:** SCRUM-20 (0054 guard), SCRUM-35 (0056 booking creation, 0059 reschedule), SCRUM-65 (times), SCRUM-69 (calendar on times), SCRUM-57 notifications.
- **Locks:** every hold writer locks the venue first, then the hold, then the event, as approval (0054), booking creation (0056) and reschedules (0059) do; the sweep locks hold rows only and skips locked ones.

## Acceptance criteria

- **AC1 (place):** The event's current coordinator can hold a venue for it while it is Approved, Planning or in Safety Review, using 15-minute times within 07:00–24:00 and an expiry in the future and at most 7 days ahead.
- **AC2 (conflict):** An active, unexpired hold refuses overlapping holds, and other events' booking approvals and reschedules at that venue (`hold_conflict`), with setup and turnaround padding; it never blocks its own event. A hold over an approved booking is refused (`booking_conflict`). Check and write happen under the venue lock.
- **AC3 (expiry):** At or after its expiry, or once its event is Cancelled or Rejected, a hold no longer protects its time and cannot be released or converted; the sweep marks expired holds `expired`.
- **AC4 (notice):** The coordinator gets one "expiring" notice 24 hours before expiry (at once if less remains) and one "expired" notice; a failed delivery is retried, never duplicated.
- **AC5 (release and convert):** The event's current coordinator can release an active hold, freeing its time; converting creates a pending booking request linked to the hold, which keeps protecting the time until Venue Staff decide (approval → `converted`, rejection → `released`) or it expires.
- **AC6 (availability):** The calendar shows an active hold as "Tentatively held" (with padding, below blocks and bookings, not free); search shows a venue that is free except for active holds as "Tentatively held" (with only a date: when holds take all its free time that day), and keeps excluding blocked and booked venues; the availability check reports it.

## Test-case specification

The venue has 30 minutes setup and 45 turnaround. Case IDs are per layer.

### Database (`database/verify_venue_holds.sql`)

| ID | AC | Scenario | Expected |
| --- | --- | --- | --- |
| AC1-H1 | AC1 | Coordinator holds 10:00–12:00 on D | Placed, stored active with the coordinator and event |
| AC1-B1 | AC1 | Expiry exactly 7 days ahead; 7 days + 1 s; now | Placed; `22023`; `22023` |
| AC1-N1 | AC1 | Another user; a Confirmed event; an event Under Review; an off-step time | `P0003`; `P0004`; `P0004`; `22023` |
| AC2-H1 | AC2 | Hold 12:15–13:00 next to the active hold | Refused `hold_conflict` with that hold |
| AC2-B1 | AC2 | Hold 13:15–14:00 (exact gap) | Placed |
| AC2-P1 | AC2 | Same time at another venue | Placed |
| AC2-H2 | AC2 | Approve another event's pending 11:00–12:00 request | Refused `hold_conflict`, recorded with `conflicting_hold_ids`, stays pending |
| AC2-P2 | AC2 | Guard for the hold's own event's booking (as approval and 0059 call it) | No `hold_conflict` |
| AC2-H3 | AC2 | Guard for any caller (incl. 0059) | `hold_conflict` |
| AC2-H4 | AC2 | Hold over an approved booking | Refused `booking_conflict` |
| AC3-B1 | AC3 | Hold expiring at `now()`; at `now()` + 1 ms | Does not protect; protects |
| AC3-N1 | AC3 | Release or convert an expired hold | `55000` |
| AC3-P1 | AC3 | Cancel the hold's event | Hold stops protecting at once; release `55000`; no notice due |
| AC3-B3 | AC3, AC4 | Venue Staff approve, or reject, a converted request after its hold expired, before the sweep | Hold stays for the sweep: then `expired` with one "expired" notice, never `converted` or `released` |
| AC4-H1 | AC4 | Sweep 25 h before expiry; 23 h before | No notice; one "expiring" notice to the current coordinator |
| AC4-P1 | AC4 | Sweep again after recording it | Not listed |
| AC3-H1, AC4-H2 | AC3, AC4 | Sweep after expiry; again after recording | Marked expired with one "expired" notice; not listed again |
| AC5-N1 | AC5 | Another user releases | `P0003` |
| AC5-H1 | AC5 | Convert; convert again; approve | Pending request linked, hold still protects; `55000`; approved and hold `converted` |
| AC5-H2 | AC5 | Convert then reject | Hold `released` |
| AC5-H3 | AC5 | Release | Released and the time is free |
| AC5-P2 | AC5 | Reassign the event; old then new coordinator releases | `P0003`; released |
| DB-1 | — | Grants | Only `service_role` reads holds or runs the functions |

### Concurrency (`database/tests/test_venue_hold_concurrency.py`, disposable database only)

| ID | AC | Scenario | Expected |
| --- | --- | --- | --- |
| AC2-X1 | AC2 | Two padded-overlapping holds | Second waits on the venue lock, then refused `hold_conflict`; one hold |
| AC2-X2 | AC2 | Another event's approval racing an in-flight hold | Waits, then refused `hold_conflict`; stays pending |
| AC5-X1 | AC5 | Hold waiting on a release of the same time | Placed after the release commits |

### API and unit (`backend/venueService/tests/test_venue_holds.py`)

| ID | AC | Scenario | Expected |
| --- | --- | --- | --- |
| AC1-H1 | AC1 | Coordinator places a hold | 201 with the hold |
| AC1-B1a–c | AC1 | Expiry just under 7 days; just over; in the past | 201; 422; 422 |
| AC1-N1 | AC1 | Other coordinator; Venue Staff; Confirmed; Under Review; off-step | 404; 403; 409; 409; 422; nothing stored |
| AC2-H1, AC2-B1 | AC2 | Overlapping hold; exact gap | 409 `hold_conflict` with the hold; 201 |
| AC2-H2 | AC2 | Venue Staff approve another event's request over the hold | 409 `hold_conflict` with the hold; pending |
| AC2-P2 | AC2 | Approve the hold's own event's request | 200 |
| AC2-H3 | AC2 | Hold over an approved booking | 409 `booking_conflict` |
| AC3-H1, AC3-N1 | AC3 | Expired hold; release or convert it | Time free; 409 |
| AC3-B3 | AC3, AC4 | Approve or reject a converted request after its hold expired (memory store) | 200; hold left active, then the sweep expires it with its notice |
| AC4-H1, AC4-B1, AC4-H2, AC4-P1 | AC4 | Sweep before and within 24 h; hold with 3 h left; expired hold; failed delivery | One "expiring" notice with `hold-expiring:<id>`; sent on placing; one "expired"; retried next sweep |
| AC5-H1, AC5-N1 | AC5 | Release; other coordinator | Time free; 404 |
| AC5-P2 | AC5 | Event reassigned; old then new coordinator releases | 404; 200 |
| AC5-H2, AC5-H3, AC5-P1 | AC5 | Convert then approve; convert then reject; list | Pending request, hold protects, approve → `converted`; reject → `released`; holds oldest first |
| AC6-H1, AC6-H2, AC6-P1 | AC6 | Search and availability check over a hold, and at a free time; calendar; booking over hold, released and expired | `tentatively_held` true, then false; `hold_conflict`; held 09:30–12:45 not free; booked then held, ended holds hidden |
| AC6-P2 | AC6 | Search a booked time; a held time, then after release; an expired hold's time | Booked venue excluded; `tentatively_held` true, then false; false |
| AC6-B1 | AC6 | Date-only search on a day fully held (setup and turnaround to the window edges); a day partly held | `tentatively_held` true; false |
| AC1-X1 | AC1–AC4 | Supabase store | Calls `place_venue_hold`, `sweep_venue_holds`, `release_venue_hold`; maps results and `55000` |
| AC3-P2 | AC3 | Supabase store reads holds for a venue | Only holds whose event is not Cancelled or Rejected |
| AC2-X3 | AC2 | eventRequestService: reschedule onto another event's hold (`backend/eventRequestService/tests/test_event_change_date_approval.py`) | 409 `BOOKING_CONFLICT` with `hold_conflict` evidence (502 "decision unavailable" on `dev`) |

### Frontend (`frontend/__tests__/venue-holds.test.tsx`) and E2E (`frontend/e2e/venue-holds.spec.ts`)

| ID | AC | Scenario | Expected |
| --- | --- | --- | --- |
| AC1-H2, AC1-B2 | AC1 | Parse the form; bad expiry, venue or dates | Minutes and `+08:00` expiry; field errors |
| AC1-H3, AC2-H5 | AC1, AC2 | Place; place a clash | One POST and refresh; booking-refusal wording for `hold_conflict` |
| AC5-N2, AC5-H4, AC3-B2 | AC3, AC5 | Release ended hold; list; hold past expiry | Explained; Request booking only when not yet requested; Expired, no actions |
| AC6-H3, AC4-H3 | AC4, AC6 | Calendar; notices | "Tentatively held"; plain messages linking to the event |
| AC6-H4 | AC6 | Search results with one held and one free venue | "Tentatively held" on the held venue's card only |
| AC1-E1, AC5-E1, AC6-E1 | AC1, AC5, AC6 | Browser: hold, see it on the event, calendar and search, release | Held, "Tentatively held 09:30–12:45", search card "Tentatively held"; Released, gone from the calendar and the search label |

## Latest execution record

Build: `feat/scrum-18-tentative-holds` working tree merged onto `dev` `5601fd9` (after PR #103) in a scratch copy, 30 October 2026. Executed with Claude Code, pending human review.

| Check | Command and environment | Result | Remarks |
| --- | --- | --- | --- |
| Database | `verify_venue_holds.sql` on a disposable PostgreSQL 16 built by `bootstrap_event_change_approval.py` | Red before 0066 (`venue_holds` missing); passed after | Same steps as the new CI job `scrum18-database-verify` |
| Database regression | SCRUM-20, -35, -63, -64, -65 verifiers after 0066 | Passed | Includes `verify_event_change_date_approval.sql` (reschedules share the guard); the SCRUM-20 guard verifier now ignores the new `conflicting_hold_ids` key |
| Database (AC3-B3) | `verify_venue_holds.sql` with the decision fix taken out of 0066 | Red (`AC3-B3: a decision closed an expired hold`); passed with it | |
| Concurrency | `test_venue_hold_concurrency.py` | 3 passed | Real lock waits via `pg_stat_activity` |
| venueService | `pytest`, `ruff check .` in `python:3.12-slim` | 686 passed; clean | 31 new; the new file cannot load on `dev` (Red); AC3-B3 Red without the memory-store fix; AC6-H1, AC6-P2, AC6-B1 Red against search before `tentatively_held` |
| eventRequestService | `pytest`, `ruff check .` | 976 passed, 1 skipped; clean | `hold_conflict` accepted in `EventChangeBookingConflict`; AC2-X3 Red on `dev` (502) |
| Containers | `docker build .` for venueService and eventRequestService | Built | |
| Frontend | `vitest run`, lint, typecheck | 563 passed; clean | 13 new; AC6-H4 Red before the search label |
| Build and E2E | `next build`, `npx playwright test` with `CI=1` | Build passed; 52/52 | The hold journey's search step failed before the search label (Red). An earlier run had one SCRUM-17 journey time out on its first page load and pass on retry; it then passed 3/3 with no retries, and the final run needed no retries |

## After merge

PR #117 was merged into `dev` on 31 October 2026. Jaren's follow-up `b1d76ee` added `GRANT UPDATE (status, closed_at, closed_by) ON public.venue_holds TO service_role` to 0066: `decide_venue_booking_request` runs as its caller, venueService calls it as `service_role`, and Postgres checks the privilege even when no hold matches, so without the grant every booking decision was refused. The database checks above call the functions as the table owner, so they could not see it.

| Check | Command and environment | Result | Remarks |
| --- | --- | --- | --- |
| Decisions as `service_role` | Rolled-back script that approves and rejects requests and places, converts, releases and sweeps holds as `service_role`, on a disposable PostgreSQL 16 built like shared (`bootstrap_event_change_approval.py` without 0064, 0066 and 0068) | Red with the 0066 merged in PR #117 (`permission denied for table venue_holds`, even with no hold); passed with `b1d76ee` | `verify_venue_holds.sql` passed on both. With `b1d76ee` on that database the guard, decision, booking creation, date change and timing verifiers and the concurrency test also passed. Executed with Claude Code |
| Shared rollout | SQL Editor on shared development, `dev` `d522315`; Koei, 31 October 2026 | Passed | Read-only pre-check: 0066 and 0068 not applied; the 0054 guard, decision function, 0056 booking creation, booking times and venue padding present. Applied 0066, then `verify_venue_holds.sql`, `verify_venue_booking_conflict_guard.sql`, `verify_venue_booking_decisions.sql` and the `service_role` script passed. Read-only post-check: RLS on; `service_role` reads holds and updates only the three columns, with no insert or delete; browser roles have no access; the hold functions are `service_role` only; one version each of the guard and decision function, the decision with both `expires_at > now()` checks; no rows left behind |

Not yet done: setting `VENUE_HOLD_SWEEP_SECONDS` if the default 60 seconds is not wanted.
