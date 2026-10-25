# SCRUM-63 Test Cases: Replace a Venue for an Affected Booking

Last reviewed: 24 October 2026

Status: **AC1 to AC5 approved by the story owner (Kennedy) on 24 October 2026, including AC5** (which goes beyond the two Jira criteria; see the review table). Assumptions A1 to A5 are proposals. Q1 to Q3 are still open with the Product Owner (Jaren) and Heng Rui; if Q1 is answered "no", AC5 falls back as described there. Nothing has been built. Test cases may change when the open questions are answered.

## Story

| Field | Value |
| --- | --- |
| Jira key | SCRUM-63 |
| Title | Replace a Venue for an Affected Booking |
| Sprint | Sprint 4 (22 October to 5 November 2026) |
| Points | 5 (estimated 22 October 2026) |
| User story | As a coordinator, I want to ask for a replacement venue when a booked venue becomes unavailable, so that my event can still go ahead without starting over. |
| Source | Week 7 Customer Change #2, Venue Becomes Unavailable After Booking (discussions #120 and #122). SCRUM-23 already blocks a venue and alerts affected coordinators, and stays Done. |
| Depends on | SCRUM-61 (Done: several venue bookings per event, cancel one), SCRUM-65 (Done: bookings and blocks in 15-minute times), SCRUM-20 (Done: conflict guard), SCRUM-64 (Done: arrangement reviews, the "needs review" flags) |

## Story contract

The two live Jira criteria (read 22 October 2026) were reviewed with the vocabulary in `docs/standards/testing.md` §1.

| Jira criterion | Review outcome | Reason |
| --- | --- | --- |
| When a venue is blocked, its affected bookings are marked as needing a new venue, and the event itself isn't cancelled (discussions #120 and #122). | **Split** into AC1, AC2, AC3 | Three independently testable parts: the marking (a database write inside the block), what must stay untouched (the event and the booking itself), and that the coordinator can see the marking. "Affected" is not defined in Jira, so AC1 defines it by the rule SCRUM-23 already uses for its alert. |
| The coordinator can search for and request a replacement venue linked to the affected booking, and the event's details are kept. | **Clarify, Split** into AC4, AC5 | "Search" is the existing venue search (SCRUM-12), not new behaviour. "Request ... linked" is AC4. What happens to the old booking when the replacement is decided is not stated in Jira; AC5 proposes it (Q1). |

Expected change to scope: migration `0064` (flag on block; further migrations for the link column, the replacement function and the AC5 decision change will take the next free numbers), one new endpoint in venueService, one new `trigger_type` in the arrangement-review readers (eventRequestService and frontend), and a panel change on the coordinator's event page.

### Acceptance criteria (proposed)

- **AC1:** Given an approved booking at a venue that has not ended (its `end_date` is today or later, Singapore time) and a new block on that venue whose dates and times overlap the booking, when Venue Staff create the block, then in the same transaction the booking receives one open arrangement-review flag (`arrangement` = `venue_booking`, `trigger_type` = `venue_block`) with a reason naming the venue and blocked dates and times. Bookings that do not overlap, have ended, are pending, rejected or cancelled, are at another venue, or belong to a Draft, Completed, Cancelled or Rejected event are not flagged. If any step fails, neither the block nor any flag is saved.
- **AC2:** Given a flagged booking, then the event's status, the booking's own status, dates, times and decision fields, and every other booking of the event are unchanged. The coordinator is told through the existing review notice (SCRUM-64 and SCRUM-37), not a new channel.
- **AC3:** Given an event with a flagged booking, when its currently assigned coordinator opens the event page, then that booking shows "Needs a new venue" in words, with its reason, next to its status. Bookings without an open flag show nothing extra, and a failed load is an error, never an empty list.
- **AC4:** Given a flagged, approved booking, when the event's currently assigned coordinator requests a replacement at a different venue, then a new **pending** booking request is stored for the same event, dates and times, linked to the flagged booking, with the event's details copied as in a normal request (SCRUM-32). The request is refused, and nothing is written, if: the booking has no open flag, is not approved, or already has an active replacement; the chosen venue is the blocked venue or does not exist; the caller is not the event's current coordinator; or the event changed since the page loaded.
- **AC5:** Given a pending replacement, when Venue Staff decide it, then the usual checks apply (suitability, blocks, conflicts: SCRUM-12, 15, 20). On approval, the replaced booking is cancelled and its flag cleared in the same transaction as the approval (Q1). On rejection or cancellation of the replacement, the flagged booking and its flag stay as they were, so the coordinator can try another venue.

### Included and excluded behaviour

| | Behaviour | Jira |
| --- | --- | --- |
| Included | Flagging affected approved bookings when a block is created | SCRUM-63 |
| Included | "Needs a new venue" shown on the event's venue bookings | SCRUM-63 |
| Included | `POST /booking-requests/{id}/replacement` with a venue id | SCRUM-63 |
| Included | A replacement link on the booking request and its effect on approval | SCRUM-63 |
| Included | A "Request replacement" action in the existing Venue bookings panel | SCRUM-63 |
| Excluded | Blocking a venue and the SCRUM-23 notice itself | SCRUM-23 |
| Excluded | Choosing new dates or times for the replacement (it keeps the old ones, A3) | A later story if wanted |
| Excluded | A new venue search that checks every day of a multi-day booking (the existing search is per date, A5) | SCRUM-12, SCRUM-31 |
| Excluded | Pending bookings on a blocked venue (approval already refuses them with `active_block`, A1) | SCRUM-15, SCRUM-23 |
| Excluded | Equipment or safety reviews | SCRUM-64 |
| Excluded | Tentative holds | SCRUM-18 |

### Actors and relationship permissions

- Venue Staff: create blocks (existing). They decide replacement requests (existing decision endpoint). They cannot request replacements.
- Event Coordinator: requests a replacement **only while currently assigned to the event**, checked through eventRequestService with the caller's token on every call, as in SCRUM-61's cancel. A coordinator who is not assigned gets 404 (the event's existence is not revealed).
- Venue Staff and the Safety Officer can read an event's bookings, flags included (existing `GET /booking-requests/event/{id}`).
- Every other role: no access.

### State transitions, persistence and atomicity

- No new booking status. A flag is an `arrangement_reviews` row, written by a private database function, never directly by the service (SCRUM-64 pattern, as in 0033 and 0055).
- Block creation: the block insert and all flags are one transaction under the existing venue row lock (`create_venue_block`).
- Replacement creation: one database function that locks the original booking, checks flag, status, venue and coordinator-supplied event version, and inserts the linked pending request. A partial unique index allows at most one active (pending or approved) replacement per replaced booking.
- AC5 approval: the existing decision function also cancels the replaced booking and clears its flag in the same transaction, after the approval is accepted. Lock order stays venue row, then request row; the replaced booking is locked last.
- Deploy order: the arrangement-review readers (eventRequestService model and frontend labels) must accept `venue_block` **before** the migration runs, as 0055 required for `venue_timing_change`.

### Assumptions and open questions

| # | Assumption or question | Status |
| --- | --- | --- |
| A1 | "Affected" means the same as SCRUM-23 AC3: an **approved** booking that has not ended and overlaps the block in dates and times, **whose event is not Draft, Completed, Cancelled or Rejected** (the rule 0033 uses for equipment, so a finished or cancelled event is not asked for a new venue). Pending bookings are not flagged because approval refuses them onto a block (`active_block`). | Proposed |
| A2 | Overlap is half-open on time (a booking ending at 11:00 is not affected by a block starting at 11:00) and uses the booked time only, not setup and turnaround padding (the block check ignores padding today; SCRUM-66 is the padding story). | Proposed |
| A3 | A replacement keeps the original dates and times. The coordinator chooses only the venue. | Proposed |
| A4 | A replacement cannot be at the same venue as the blocked one, and a flag exists only for a block on that booking's venue. | Proposed |
| A5 | "Search" reuses the existing venue search, prefilled with the booking's first date and times. It does not check every day of a multi-day booking; the approval guard is the authority. | Proposed |
| A6 | The existing SCRUM-23 notice to the coordinator stays unchanged. | **Q3** |
| Q1 | When a replacement is approved, is the old booking cancelled automatically (proposed), or does the coordinator cancel it by hand with SCRUM-61's Cancel? Automatic touches `decide_venue_booking_request` (Koei's 0054); the fallback keeps AC5 to "the flag stays until the coordinator cancels the old booking, which clears it". | **Open, Jaren** |
| Q2 | May a coordinator request a replacement as soon as the block exists (proposed), or only after Venue Staff acknowledge it? | **Open, Jaren** |
| Q3 | The block already sends a SCRUM-23 notice, and each flag queues a SCRUM-64 review notice, so a coordinator may get two for one block. Keep both, or retire the SCRUM-23 notice? | **Open, Jaren, Heng Rui** |
| Q4 | May a block that overlaps no booking still be created and flag nothing (proposed, yes)? | Proposed |

## Test cases (specification)

Fixed test data: today is **2030-03-04** (frozen clock, Singapore); venue **V1** (blocked), venue **V2** (replacement), event **E1** assigned to coordinator **C1**; **B1** approved at V1 on 2030-03-10 to 2030-03-10, 540 to 720 (09:00 to 12:00). Block times are minutes after midnight.

| ID | AC | Test scenario | Technique | Pre-conditions | Test steps | Test data | Expected result | Forbidden side effects | Layer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AC1-H1 | AC1 | The basic rule: a block over an approved booking flags it | Happy | B1 approved at V1 | Venue Staff create a block at V1 | 2030-03-10, 600 to 660 | Block stored (201). One open `venue_booking` / `venue_block` flag for B1 with a reason naming V1, the date and the time | No flag for any other booking | API, DB |
| AC1-H2 | AC1 | One block flags every affected booking, each once | Happy | B1 and B2 (same venue, 2030-03-10, 780 to 900) approved at V1 | Create a block covering both | 2030-03-10, 540 to 900 | A flag on B1 and one on B2; creating the same block twice never gives a booking two flags for one block | Duplicate flags | DB |
| AC1-P1 | AC1 | A pending booking is not flagged | Partition | B3 pending at V1 overlapping the block | Create the block | as AC1-H1 | No flag for B3 | A flag or any change to B3 | DB |
| AC1-P2 | AC1 | A rejected booking is not flagged | Partition | B4 rejected at V1 overlapping | Create the block | as AC1-H1 | No flag | Flag on B4 | DB |
| AC1-P3 | AC1 | A cancelled booking is not flagged | Partition | B5 cancelled at V1 overlapping | Create the block | as AC1-H1 | No flag | Flag on B5 | DB |
| AC1-P4 | AC1 | A booking at another venue is not flagged | Partition | B6 approved at V2, same date and time | Create the block at V1 | as AC1-H1 | No flag for B6 | Flag on B6 | DB |
| AC1-P5 | AC1 | A booking of a cancelled event is not flagged | Partition | B11 approved at V1 for a Cancelled event | Create the block | as AC1-H1 | No flag for B11 | Flag on B11 | DB |
| AC1-B1 | AC1 | A block that ends exactly where the booking starts does not affect it | Boundary | B1 starts 540 | Block 480 to 540 on 2030-03-10 | 480 to 540 | No flag | Flag on B1 | DB, unit |
| AC1-B2 | AC1 | A block that overlaps by one 15-minute step does affect it | Boundary | B1 ends 720 | Block 705 to 765 | 705 to 765 | Flag on B1 | None | DB, unit |
| AC1-B3 | AC1 | A block that starts exactly where the booking ends does not affect it | Boundary | B1 ends 720 | Block 720 to 780 | 720 to 780 | No flag | Flag on B1 | DB, unit |
| AC1-B4 | AC1 | A booking ending today is still affected | Boundary | B7 approved at V1 on 2030-03-04 (today), 540 to 720 | Block today 600 to 660 | 2030-03-04 | Flag on B7 | None | DB |
| AC1-B5 | AC1 | A booking that ended yesterday is not affected | Boundary | B8 approved at V1 on 2030-03-03 | Block 2030-03-03, 600 to 660 | 2030-03-03 | No flag | Flag on B8 | DB |
| AC1-B6 | AC1 | A multi-day booking is flagged when the block meets any one of its days | Boundary | B9 approved 2030-03-10 to 2030-03-12, 540 to 720 | Block only 2030-03-12, 600 to 660 | 2030-03-12 | Flag on B9 | None | DB |
| AC1-N1 | AC1 | A block over nothing flags nothing and still saves | Negative | No booking at V1 on the block's dates | Create the block | 2030-04-01 | 201, block stored, zero flags | Error response | API, DB |
| AC1-N2 | AC1 | A failure while flagging saves neither block nor flags | Negative | Force the flag insert to fail (fault in the test database) | Create the block | as AC1-H1 | Error returned; no block row, no flag rows | A saved block with no flags, or flags with no block | DB |
| AC1-N3 | AC1 | A booking whose event no longer exists cannot carry a flag and does not stop the block | Negative | B10 approved, its event row missing (venue bookings have no foreign key) | Create the block | as AC1-H1 | Block saved and returned; no flag for B10 (the function keeps its return type, so nothing is reported) | Failed block | DB |
| AC1-X1 | AC1 | Only Venue Staff create blocks (existing) and a non-staff caller flags nothing | Cross-cutting | B1 approved | A coordinator, an organiser and no token each try to create a block | as AC1-H1 | 403, 403, 401 | Block or flag written | API |
| AC1-X2 | AC1 | Browser roles cannot write flags | Cross-cutting | Real database | `anon` and `authenticated` try to insert into `arrangement_reviews` and call the flag function | none | Permission denied | A flag row | DB |
| AC2-H1 | AC2 | Flagging leaves the event and the booking as they were | Happy | B1 flagged by AC1-H1 | Read E1 and B1 | none | E1 status unchanged; B1 still `approved`, same dates, times, `decided_by`, `decided_at` | Any change to E1 or B1 | API, DB |
| AC2-H2 | AC2 | Other bookings of the event are untouched | Happy | E1 also has B6 (V2) approved | Block V1 | as AC1-H1 | B6 and its dates unchanged; no flag on B6 | Change to B6 | API |
| AC2-H3 | AC2 | The coordinator is told through the existing review notice | Happy | Notification outbox available | Create the block | as AC1-H1 | One `arrangement_needs_review` notice queued for the flag, sent to E1's coordinator | A second new channel; a notice for an unflagged booking | DB |
| AC3-H1 | AC3 | The event page marks the flagged booking | Happy | B1 flagged; C1 assigned | C1 opens E1's page | none | B1 shows "Needs a new venue" and its reason beside "Approved" | Colour-only status | UI |
| AC3-P1 | AC3 | An unflagged booking shows nothing extra | Partition | B6 not flagged | Open the page | none | B6 has no flag text | Flag text on B6 | UI |
| AC3-P2 | AC3 | A cleared flag is not shown | Partition | B1's flag cleared (cancelled or cleared) | Open the page | none | No "Needs a new venue" | Stale flag shown | UI |
| AC3-N1 | AC3 | A failed flag load is an error, not "no flags" | Negative | Review endpoint returns 502 | Open the page | none | An alert that flags could not be loaded; bookings still listed | An empty-looking flag state | UI |
| AC3-X1 | AC3 | Venue Staff and the Safety Officer can read the flags; an unassigned coordinator cannot | Cross-cutting | B1 flagged | Read the event's bookings as venue staff, safety officer, unassigned coordinator, organiser | none | 200, 200, 404, 403 | Flag details to an unassigned coordinator | API |
| AC3-X2 | AC3 | The coordinator's review read accepts a flag raised by a venue block | Cross-cutting | A `venue_block` review row for E1 | C1 reads E1's arrangement reviews | the row | 200 with the row and its `trigger_type` `venue_block`; nothing changed | A 500 from an unknown cause | API |
| AC3-X3 | AC3 | The review list names the cause in words and keeps its ordinary controls | Cross-cutting | A `venue_block` review | Render the list as read-only | the row | "Venue blocked", the reason and both references shown; no Mark reviewed control | Label missing; the row mutated | UI |
| AC4-H1 | AC4 | The assigned coordinator requests a replacement | Happy | B1 flagged; V2 exists | C1 `POST /booking-requests/{B1}/replacement` | `{"venue_id": V2}` | 201; a new `pending` request at V2 for E1, 2030-03-10, 540 to 720, `replaces_booking_id` = B1, event name and attendance copied | Change to B1, its flag or E1 | API, DB |
| AC4-N1 | AC4 | An unflagged booking cannot be replaced | Negative | B6 approved, no flag | Request replacement for B6 | V1 | 409 `not_flagged` | A new request | API, DB |
| AC4-N2 | AC4 | A booking that is not approved cannot be replaced | Negative | B3 pending with a flag forced in the test database | Request replacement | V2 | 409 | A new request | DB |
| AC4-N3 | AC4 | The blocked venue is refused as the replacement | Negative | B1 flagged | Request replacement at V1 | `{"venue_id": V1}` | 422 `same_venue` | A new request | API, DB |
| AC4-N4 | AC4 | An unknown venue is refused | Negative | B1 flagged | Request replacement | unknown id | 404 "Venue not found" | A new request | API |
| AC4-N5 | AC4 | A second replacement while one is active is refused | Negative | B1 has an active pending replacement | Request another at V3 | V3 | 409 `replacement_exists` | A second request | API, DB |
| AC4-N6 | AC4 | The event changed since the page loaded | Negative | E1 updated after the page loaded | Request with the old event version | stale `updated_at` | 409 "Event request changed; refresh" | A new request | API, DB |
| AC4-N7 | AC4 | An unassigned coordinator cannot request | Negative | C2 not assigned to E1 | C2 requests | V2 | 404 | A new request; any disclosure of B1 | API |
| AC4-N8 | AC4 | A coordinator reassigned between page load and request is refused | Negative | C1 reassigned after the page loaded | C1 requests | V2 | 404 | A new request | API |
| AC4-N9 | AC4 | An unknown booking id | Negative | none | Request replacement for an unknown id | random uuid | 404 "Booking request not found" | A new request | API |
| AC4-P1 | AC4 | Roles other than coordinator are refused | Partition | B1 flagged | Venue staff, safety officer, organiser, no token | V2 | 403, 403, 403, 401 | A new request | API |
| AC4-X1 | AC4 | Two coordinators racing for the same flag give exactly one replacement | Cross-cutting | B1 flagged; two sessions | Both request at the same time | V2 and V3 | One 201, one 409 | Two active replacements | DB (two connections) |
| AC4-X2 | AC4 | The panel offers "Request replacement" only for a flagged approved booking | Cross-cutting | A mix of bookings | Open the page | none | The action appears for B1 only, with an accessible name; keyboard operable | Action on unflagged or non-approved bookings | UI |
| AC5-H1 | AC5 | Approving the replacement cancels the old booking and clears its flag | Happy | A pending replacement R1 of B1 at V2, no conflicts | Venue Staff approve R1 | `{"decision":"approved"}` | R1 `approved`; B1 `cancelled` with the approver recorded; B1's flag cleared; all in one transaction | B1 left approved with a cleared flag, or the reverse | API, DB |
| AC5-N1 | AC5 | Rejecting the replacement leaves the old booking and flag | Negative | R1 pending | Venue Staff reject R1 with a reason | `{"decision":"rejected","reason":"..."}` | R1 `rejected`; B1 still `approved`; flag still open; a new replacement can be requested | B1 cancelled; flag cleared | API, DB |
| AC5-N2 | AC5 | A replacement that now clashes is refused and changes nothing | Negative | Another approved booking now occupies V2 at that time | Venue Staff approve R1 | as AC5-H1 | Refused `booking_conflict`; R1 pending or as the guard defines; B1 and its flag unchanged | B1 cancelled | API, DB |
| AC5-N3 | AC5 | The coordinator cancelling the replacement leaves the old booking and flag | Negative | R1 pending | C1 cancels R1 (SCRUM-61) | none | R1 `cancelled`; B1 and flag unchanged; a new replacement is allowed | B1 cancelled | API, DB |
| AC5-N4 | AC5 | A failure while cancelling the old booking undoes the approval | Negative | Force the cancel step to fail | Approve R1 | as AC5-H1 | Error; R1 still pending; B1 and flag unchanged | R1 approved while B1 stays approved | DB |
| AC5-X1 | AC5 | Approving a replacement and cancelling the original at the same moment cannot both win | Cross-cutting | R1 pending; two sessions | Approve R1 while C1 cancels B1 | none | One consistent outcome; no booking left with a dangling link | A cancelled B1 with an approved R1 and an open flag | DB (two connections) |
| AC5-X2 | AC5 | The earlier criteria still hold: ordinary approvals behave as before | Cross-cutting | A normal pending request with no replacement link | Approve it | none | Approved exactly as before; no booking cancelled | Any cancellation | API (regression) |

Not yet in this table, to add once the open questions are answered: the fallback cases for Q1 (flag clears when the old booking is cancelled by hand), the duplicate-notice cases for Q3, and an end-to-end journey (block a venue, coordinator requests a replacement, staff approve, old booking cancelled).

## Latest execution record

| ID | Automation status | Actual result | Execution status | Build or commit | Executed by and date | Remarks and evidence |
| --- | --- | --- | --- | --- | --- | --- |
| AC3-X2 (API) | Green | `pytest -q` in `backend/eventRequestService`: 773 passed, 1 skipped; `ruff check .` clean. Red before: 1 failed (`venue_block` not in the response model's allowed causes) | Pass | branch `feat/scrum-63-replace-venue` on `dev` `9276da2` (uncommitted), local venv, repository doubled | Claude for Kennedy, 24 Oct 2026 | `tests/test_arrangement_reviews.py` |
| AC3-X3 (UI) | Green | `npx vitest run`: 62 files, 498 tests passed; `npm run lint` and `npm run typecheck` clean. Red before: 1 failed (label missing) | Pass | as above, local | Claude for Kennedy, 24 Oct 2026 | `frontend/__tests__/arrangement-review-venue-block.test.tsx` |
| AC1-H1, H2, P1 to P5, B1 to B6, N1 to N3, X2; AC2-H1, H3 (DB) | Green | `ALL SCRUM-63 VENUE BLOCK BOOKING REVIEW VERIFICATIONS PASSED`. Red before `0064`: the first check failed (`flags not as expected`). `0064` re-applied twice without error | Pass | **disposable local PostgreSQL 16** (docker `postgres:16`, database `scrum48_t63`) built by `database/tests/bootstrap_event_change_approval.py` (dev's migrations through `0059`, Auth doubled) then `0064` | Claude for Kennedy, 24 Oct 2026 | `psql -f database/verify_venue_block_booking_reviews.sql`. Nine one-line faults in `create_venue_block` were each caught (pending flagged, today's booking excluded, inclusive time overlap at either end, cancelled event flagged, other venue flagged, date overlap tested on the wrong end, ended booking flagged, no time test). Two first survived because the verifier compared a missing array with `<>`, which is NULL, not true; fixed with `IS DISTINCT FROM`. AC1-H2 is checked as two bookings of two events under one block; AC1-X1 (HTTP roles) and AC2-H2 are not in the SQL and stay with the API layer |
| Existing database verifiers (regression) | Green | Passed on the same database after `0064`: `verify_venue_block_times`, `verify_venue_booking_decisions`, `verify_venue_booking_conflict_guard`, `verify_venue_timing_change_reviews`, `verify_arrangement_review_flags`, `verify_versioned_venue_booking_creation` | Pass | as above | Claude for Kennedy, 24 Oct 2026 | `0064` replaces `create_venue_block`; the others still hold |
| AC1-X1, AC2-H2, AC3-H1, AC3-P1, AC3-P2, AC3-N1, AC3-X1, AC4 (all), AC5 (all) | Planned | Not run | Not executed | none | none | Not built yet. Also not run: PR CI, shared development, a browser journey. `0064` is **not applied to shared development**. Q1 to Q3 still open |
