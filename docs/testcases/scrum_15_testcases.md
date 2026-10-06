# SCRUM-15 — Decide on a Venue Booking Request

**Jira:** [SCRUM-15](https://is212g9t4.atlassian.net/browse/SCRUM-15)

**User story:** As a Venue Staff member, I want to approve or reject a venue booking request and optionally suggest an alternative, so that only viable venue commitments proceed.

## Story contract review

The acceptance criteria were reviewed against the customer briefing (*Venue Booking Approval*, §6 Notifications), the backlog (M3-2, C-6, M5-1, C-9a) and the SCRUM-32 schema (`0018_venue_booking_requests.sql`). The story owner approved this contract on 7 October 2026, choosing to record every refused approval in a log table (AC5) and to notify the requesting Coordinator (AC4).

| Original criterion | Outcome | Reason |
| --- | --- | --- |
| Venue Staff can approve or reject a pending booking request for a specific venue and date-slot. | Clarify | States the refusal for a request that is no longer pending and for non-staff. |
| On rejection, staff can record a reason and optionally suggest an alternative venue or arrangement. | Clarify | 0018 requires a non-blank reason to reject; the alternative is optional free text. |
| Given an approval, when granted, then the venue/slot is marked booked and availability is updated to prevent conflicts. | Keep | An approved request is the booking (0018); availability must treat it as taken. |
| The requesting Coordinator is notified of the decision; any resulting changes are made by the Coordinator. | Clarify | The recipient is `requested_by`; delivery failures never undo a decision. |
| Given the venue becomes blocked/unavailable for the slot before a decision, when the request is assessed, then it cannot be approved and the reason is recorded. | Clarify | "Recorded" means every refused approval is stored with who, when and the reasons. |
| Given another booking has confirmed the same slot since the request was raised, when approval is attempted, then it is refused as a conflict. | Narrow | Exact date and slot overlap only; setup and turnaround gaps stay in M5-1. |

## Increment scope

- **Included in this increment:** the decision API and its database function (AC1, AC2, AC3 booking, AC5, AC6), the refusal log, and the venue-row lock shared by approval and block creation.
- **Following increments:** the AC4 notification; the Venue Staff "Booking requests" page; booked slots in search, the availability check and the calendar (rest of AC3, and SCRUM-23 AC2b).
- **Excluded:** setup and turnaround gaps (M5-1); notifying a reassigned Coordinator or the Organiser (C-9a; eventRequestService refuses Venue Staff on `GET /event-requests/{id}/coordinator`); the Coordinator submission form (SCRUM-32).
- **Actors and access:** only Venue Staff can decide or read the refusal log (403 otherwise). Any Venue Staff member may decide any pending request.
- **Transitions:** `pending → approved` and `pending → rejected`, once. A refused approval leaves the request `pending`.
- **Persistence and atomicity:** `decide_venue_booking_request` locks the venue row, then the request row, re-checks status, venue status, operating slots, active blocks and approved overlapping requests, and writes either the decision or one refusal-log row. `create_venue_block` takes the same venue lock, so a block and an approval cannot both succeed for overlapping periods. Browser roles have no access to either table or function.
- **Assumptions:** dates are inclusive and NIGHT belongs to its starting date (as agreed in 0018). Past dates are not refused because no AC requires it.

## Acceptance criteria

- **AC1:** Given a pending booking request, when Venue Staff approve or reject it, then the decision, the deciding user and the time are saved. A request that is no longer pending is refused with 409 and stays unchanged; an unknown request returns 404; a non-Venue-Staff caller gets 403.
- **AC2:** Given a pending request, when Venue Staff reject it, then a non-blank reason is required and an optional suggested alternative (free text) is saved. An approval carries neither; supplying either, or rejecting without a reason, returns 422 and changes nothing.
- **AC3:** Given an approval is granted, then the request becomes the confirmed booking for its venue, dates and slots, and later approvals that overlap it are refused (see AC6). Showing booked slots in search and the calendar follows in a later increment.
- **AC4 (later increment):** Given a decision is saved, then the requesting Coordinator receives an in-app notification with the decision, reason and alternative; a notification failure never undoes the decision.
- **AC5:** Given the venue is blocked as a whole, the slot is outside its operating slots, or an active block overlaps the request when approval is attempted, then approval is refused with 409 and the reason codes (`venue_unavailable`, `outside_operating_slots`, `active_block`), the request stays pending, and the refusal is recorded with who, when, the reasons and the conflicting block IDs.
- **AC6:** Given another approved request for the same venue overlaps on any date and slot, when approval is attempted, then it is refused with 409 and `booking_conflict` listing the conflicting booking IDs, and the refusal is recorded. Pending or rejected requests, other venues and non-overlapping dates or slots do not conflict.

## Test-case specification

| ID | AC | Test scenario | Technique | Pre-conditions | Test steps | Test data | Expected result | Forbidden side effects | Layer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AC1-H1 | AC1, AC3 | Approving a free slot books it | Happy | Pending request; venue available, no blocks or bookings | `POST /booking-requests/{id}/decision` `{"decision":"approved"}` | 20–21 Oct, AM | 200; status `approved`, `decided_by` = caller, `decided_at` set; no reason or alternative | No refusal row | API |
| AC1-H2 | AC1, AC2 | Rejecting records reason and alternative | Happy | Pending request | Reject with reason and alternative | "Hall under repair", "Try Orchard Studio" | 200; status `rejected` with trimmed reason and alternative | — | API |
| AC1-N1 | AC1 | A decided request cannot be decided again | Negative | Request already approved / rejected | Approve or reject again | — | 409 "already been decided" | Status, reason and decider unchanged | API |
| AC1-N2 | AC1 | Unknown request | Negative | — | Decide an unknown or malformed id | — | 404 | Nothing written | API |
| AC1-X1 | AC1 | Only Venue Staff can decide | Cross-cutting | Pending request | Decide as Event Coordinator, Event Organiser, Attendee | — | 403 | Request unchanged; no refusal row | API |
| AC2-N1 | AC2 | Rejecting needs a non-blank reason | Negative | Pending request | Reject without reason; with blank reason | `null`, `"   "` | 422 | Request stays pending | API + unit |
| AC2-N2 | AC2 | An approval carries no reason or alternative | Negative | Pending request | Approve with a reason or alternative | "ok" | 422 | Request stays pending | API + unit |
| AC2-P1 | AC2 | The alternative is optional | Partition | Pending request | Reject with a reason only | — | 200; alternative `null` | — | API |
| AC5-H1 | AC5 | An overlapping active block refuses approval and is recorded | Happy | Active block 21 Oct AM on the venue | Approve 20–21 Oct AM | — | 409 `active_block` with the block ID; one refusal row (who, when, codes, block IDs) | Request stays pending | API |
| AC5-P1 | AC5 | A venue blocked in the catalogue refuses approval | Partition | Venue `status = blocked` | Approve | — | 409 `venue_unavailable`; recorded | Request stays pending | API |
| AC5-P2 | AC5 | A slot the venue does not operate refuses approval | Partition | Venue operates AM, PM only | Approve a NIGHT request | — | 409 `outside_operating_slots`; recorded | Request stays pending | API |
| AC5-P3 | AC5 | Lifted blocks and non-overlapping blocks do not refuse | Partition | Lifted block on the slot; active block on another slot or date | Approve | — | 200 approved | No refusal row | API |
| AC5-B1 | AC5 | Block date boundaries are inclusive | Boundary | Block ends on the request's first day / starts the day after it ends | Approve | 20 Oct vs 19–20 Oct; 22 Oct | Refused when sharing 20 Oct; approved when the block starts 22 Oct | — | API |
| AC5-X1 | AC5 | Only Venue Staff can read the refusal log | Cross-cutting | One refusal recorded | `GET /booking-requests/{id}/refusals` as each role | — | Staff 200 with the row; others 403 | — | API |
| AC6-H1 | AC6, AC3 | An approved overlapping booking refuses approval | Happy | Request A approved 20–21 Oct AM | Approve request B 21 Oct AM | — | 409 `booking_conflict` listing A; recorded | B stays pending; A unchanged | API |
| AC6-P1 | AC6 | Pending and rejected requests never conflict | Partition | Overlapping requests pending / rejected | Approve | — | 200 | — | API |
| AC6-P2 | AC6 | Other venues and non-overlapping slots do not conflict | Partition | Approved booking on another venue / PM only | Approve AM | — | 200 | — | API |
| AC6-B1 | AC6 | Booking date boundaries are inclusive | Boundary | A approved 20–21 Oct | Approve B 21–22 Oct; C 22–23 Oct | — | B refused; C approved | — | API |
| AC6-X1 | AC3, AC6 | Two simultaneous approvals of overlapping requests cannot both succeed | Cross-cutting | Two pending overlapping requests | Approve both concurrently | — | Exactly one approved; the other refused `booking_conflict` | Never two approved overlapping rows | API (threads) + DB |
| DB-1 | AC1–AC3, AC5, AC6 | The database function enforces the same rules atomically | Cross-cutting | Fresh Postgres with 0016, 0018, 0023, 0024 | Run `database/verify_venue_booking_decisions.sql` | — | Every scenario passes; transaction rolled back | Browser roles cannot execute the functions or read the log | DB |
| DB-2 | AC5, AC6 | Block creation takes the venue lock | Cross-cutting | 0024 applied | Create a block through `create_venue_block` | — | Block inserted; unknown venue raises `P0002` | — | DB + API |
| SB-1 | AC1, AC5, AC6 | venueService maps the database function's outcomes | Cross-cutting | Fake Data API | Approve / reject / refused / not pending / not found | — | 200, 409 with codes, 409, 404 | Errors expose no database detail | Unit |

## Latest execution record

Unit-level rule cases in `backend/venueService/tests/test_booking_decisions.py` carry their own IDs: AC1-H3, AC1-N3, AC1-N4, AC1-N5, AC1-X2, AC2-P2, AC2-P3, AC2-P4, AC2-N3, AC5-H2, AC5-P4, AC5-P5, AC5-N1, AC6-H2, AC6-B2, AC6-P3, AC6-P4.

Build: uncommitted working tree on `feat/venue-booking-decision` at `5fc13ee`. Executed with Claude Code on 7 October 2026, pending human review.

| ID | Automation status | Actual result | Execution status | Build or commit | Executed by and date | Remarks and evidence |
| --- | --- | --- | --- | --- | --- | --- |
| AC1-H1, AC1-H2, AC2-P1 | Green | Approval and rejection saved with decider, time, trimmed reason and optional alternative | Pass | 5fc13ee + working tree, local | Claude Code, 7 Oct 2026 | `tests/test_booking_decision_api.py` |
| AC1-N1, AC1-N2, AC1-X1 | Green | 409 already decided (unchanged); 404 unknown; 403 for coordinator, organiser, attendee (unchanged, no refusal) | Pass | same | same | `tests/test_booking_decision_api.py` |
| AC2-N1, AC2-N2, AC2-N3 | Green | Rejection without or with blank reason, approval with details, unknown decision and client-set decider all 422; request stays pending | Pass | same | same | Red observed first for the rule change (2 cases accepted a reasonless rejection), then Green: `tests/test_booking_decisions.py` |
| AC5-H1, AC5-P1–P3, AC5-B1, AC5-X1 | Green | Block, catalogue status and non-operating slot refuse with the right codes and are recorded; lifted/non-overlapping blocks do not; inclusive boundaries; refusal log Venue Staff only | Pass | same | same | `tests/test_booking_decision_api.py` |
| AC6-H1, AC6-P1, AC6-P2, AC6-B1 | Green | Approved overlap refused as `booking_conflict` with its id and recorded; pending/rejected, other venues and slots do not conflict; inclusive boundaries | Pass | same | same | `tests/test_booking_decision_api.py` |
| AC6-X1 | Green | Two simultaneous overlapping approvals: one 200, one 409; never two approved | Pass | same | same | With the venue lock replaced by a no-op (scratch copy only) the same test failed with `[200, 200]`, proving it detects double booking |
| DB-1 | Green | `verify_venue_booking_decisions.sql` passed on a throwaway `postgres:16-alpine` after 0016, 0018, 0023, 0024 (0024 applied twice); before 0024 it stopped at the missing function (valid Red) | Pass | same | same | Two-session test: session 2 waited ~2 s for session 1's venue lock, then was refused `booking_conflict` and recorded; exactly one approved |
| DB-2 | Green | `create_venue_block` inserts under the venue lock and trims detail; unknown venue raises `P0002` | Pass | same | same | DB verification script; API path through `SupabaseBlockRepository` covered by `tests/test_database_storage.py` |
| SB-1 | Green | RPC call shape, refused outcome mapping, `P0002`/`55000`/other codes mapped without leaking detail, malformed id skips the call, refusal log query | Pass | same | same | `tests/test_supabase_booking_decision_store.py` |
| AC4 and later increments | — | — | Not executed | — | — | Notification, booking-requests page and booked slots in search/calendar follow. |

**Red phase:** the rule change and the database script were observed failing first for the missing behaviour. The API and Supabase-store tests were written before their code but were not run in between, so no separate Red is claimed for them; the concurrency test was instead shown to fail without the lock.

### Local validation evidence

| Boundary | Command or environment | Result | Limitation |
| --- | --- | --- | --- |
| Backend | `ruff check .`; `pytest` in `python:3.12-slim` | Lint clean; 338 passed (78 SCRUM-15) | In-memory stores and a fake Data API. |
| Database | `postgres:16-alpine` throwaway container; migrations 0016, 0018, 0023, 0024; `verify_venue_booking_decisions.sql`; two concurrent `psql` sessions | Passed | 0024 is **not** applied to shared development. |
| Frontend | `npx vitest run`, `npm run typecheck`, `npm run lint` | 236 passed; clean | No frontend change in this increment. |

Pull-request CI and reviewer approval: not yet run.
