# SCRUM-32 Test Cases: Submit a Venue Booking Request

Last reviewed: 4 October 2026

Status: **the AC review below was approved as proposed by the story owner (Kennedy) on 4 October 2026.** Only the database layer is designed and written so far, and its Red and Green runs are recorded below (4 October 2026): the migration was applied to the shared development project and the script then passed. The API and service cases are listed as planned and will be designed before the API work starts. The test-design review is pending.

## Story

| Field | Value |
| --- | --- |
| Jira key | SCRUM-32 |
| Title | Submit a Venue Booking Request |
| Sprint | Sprint 2 |
| User story | As an Event Coordinator, I want to submit a booking request for a chosen venue, so that Venue Staff can assess and decide on it for my event. |

## Story contract

The four live Jira criteria (read on 4 October 2026) were reviewed with the vocabulary in `docs/standards/testing.md` §1. Jira's criteria 1 to 4 became AC1 to AC6 here; the mapping is in the last column.

| ID | Criterion | Review outcome | Jira criterion |
| --- | --- | --- | --- |
| AC1 | Given a Coordinator currently assigned to an event, when they submit a request for a venue with a start date, an end date (inclusive; equal for a single day) and one or more slots, then a request is created with status pending, linked to that event and recorded as requested by that Coordinator. | **Clarify, Narrow** | 1 |
| AC2 | Given a request created for an event, then it stores the requested dates and slots and a snapshot taken from the event at submission: event name, expected attendance and venue-requirements text. | **Clarify** | 2 |
| AC3 | Given a created request, when Venue Staff list the pending queue, then it appears with status pending. | **Split** (part 1) | 3 |
| AC4 | Given any submission, then no confirmed booking or block is created and no slot is reserved; two pending requests for the same venue, dates and slots can coexist. | **Split** (part 2); whether other code treats a pending slot as unconfirmed belongs to SCRUM-15 and SCRUM-23 | 3 |
| AC5 | Given requests submitted by a Coordinator, when they list or open one of their own requests, then it shows its current status (pending, approved or rejected); another Coordinator's request returns not found. | **Clarify** | 4 |
| AC6 | Given a caller who is not the Coordinator currently assigned to the event, when they submit, then the submission is refused and nothing is stored. | **Add** | none |

### Decisions agreed with the SCRUM-15 and SCRUM-23 owner (koei), 4 October 2026

1. Submit creates the pending request and reserves nothing. An approved request is the booking; there is no separate allocation table. Pending requests never block each other, and the first approval wins.
2. Start and end dates are inclusive. Slot validation matches `venue_blocks`: at least one slot, no duplicates, no NULL.
3. Approving a request and creating a block both lock the same `venues` row, so neither can bypass the other's checks. Both run as a single database function, because a lock cannot span separate Data API calls.
4. Creating a block over an approved booking is allowed. The block flow identifies the affected confirmed upcoming events for notification; it does not reject the block or cancel the booking. If the block exists first, a later conflicting approval fails.
5. `decision_reason` is required to reject; `suggested_alternative` is optional.
6. `event_request_id` is required. venueService validates it against eventRequestService (a foreign key would cross a service boundary) by calling `GET /event-requests/{id}/coordinator` with the caller's token and comparing the returned `coordinator_id` to the caller. A 200 from `GET /event-requests/{id}` alone is not enough: the owning organiser also receives it.
7. Submission is not restricted by event status until a requirement is agreed.
8. Notifications use `requested_by` for decisions and the event's current Coordinator for later block alerts, so `coordinator_id` is not stored.

### Included and excluded behaviour

| | Behaviour | Jira |
| --- | --- | --- |
| Included | The `venue_booking_requests` table, its constraints and server-only access; then the submit, queue and status-read endpoints | SCRUM-32 |
| Excluded | Approving or rejecting a request, the venue-row lock, and creating the decision | SCRUM-15 |
| Excluded | Block creation and the affected-events lookup | SCRUM-23 |
| Excluded | Availability and conflict detection against confirmed bookings | SCRUM-31, SCRUM-20 |
| Excluded | Notifications | SCRUM-37 |
| Excluded | A frontend screen | None built yet |

### Actors and relationship permissions

- Event Coordinator: submits, and sees only their own requests. Must be the Coordinator currently assigned to the event.
- Venue Staff: lists the pending queue and can open any request.
- Nobody else, and no browser role, reaches the table directly.

### State transitions, persistence and atomicity

- This story creates rows in `pending` only. Moving to `approved` or `rejected` is SCRUM-15; the table's constraint keeps the decision fields consistent with the status.
- Submission is a single-row insert, so it is atomic by itself. The approve and block functions carry the venue-row lock.

### Assumptions and open questions

| ID | Assumption or question | Used by |
| --- | --- | --- |
| A1 | Submission does not refuse past dates, blocked venues or duplicate requests; the decision step handles them. Proposed with the plan, not stated in the Jira criteria. | AC1, AC4 |
| A2 | The snapshot copies the event's venue-requirements text only, not its accessibility needs. | AC2 |
| A3 | Dates are calendar dates with no time zone, and NIGHT belongs to its starting date, as for blocks. | AC1 |
| A4 | `requested_by` and `decided_by` are plain `uuid` columns with no foreign key to `auth.users`, as in the equipment and `staff_roles` tables. | AC1, AC5 |
| Q1 | Should the snapshot also keep the event's accessibility needs? | AC2 |

## Test-case matrix

A row with an ID range is a loop in the verification script whose cases carry those IDs.

### Specification: database layer

All rows run in [`database/verify_venue_booking_requests.sql`](../../database/verify_venue_booking_requests.sql), which needs `0016_venues.sql` and `0018_venue_booking_requests.sql` applied and rolls back every row it writes.

| ID | AC | Test scenario | Technique | Pre-conditions | Test steps | Test data | Expected result | Forbidden side effects | Layer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AC1-H1 | AC1 | A single-day, one-slot request is stored and defaults to pending | Happy | A venue exists | Insert omitting `status` | 2030-01-10 to 2030-01-10, slot AM | Row stored with status `pending`, `created_at` set, all four decision fields NULL | none | DB |
| AC1-H2 | AC1 | A multi-day request with all three slots is stored | Happy | A venue exists | Insert | 2030-01-10 to 2030-01-12, AM, PM, NIGHT | Row stored | none | DB |
| AC1-B1 | AC1 | An end date one day before the start is refused | Boundary | A venue exists | Insert | start 2030-01-10, end 2030-01-09 | Refused, `check_violation` (23514) | No row stored | DB |
| AC1-B2 | AC1 | An end date equal to the start is accepted (inclusive) | Boundary | A venue exists | Insert | start and end 2030-02-01 | Row stored | none | DB |
| AC1-B3 | AC1 | An end date one day after the start is accepted | Boundary | A venue exists | Insert | start 2030-02-01, end 2030-02-02 | Row stored | none | DB |
| AC1-P1 to AC1-P3 | AC1 | Each slot value alone is accepted (AM, PM, NIGHT) | Partition | A venue exists | Insert | one slot per case | Row stored | none | DB |
| AC1-N1 | AC1 | An empty slot list is refused | Negative | A venue exists | Insert | slots `[]` | 23514 | No row stored | DB |
| AC1-N2 | AC1 | A slot list containing NULL is refused | Negative | A venue exists | Insert | slots `[AM, NULL]` | 23514 | No row stored | DB |
| AC1-N3 | AC1 | A duplicate slot is refused | Negative | A venue exists | Insert | slots `[AM, AM]` | 23514 | No row stored | DB |
| AC1-N4 | AC1 | An unknown slot value is refused | Negative | A venue exists | Insert | slots `[MORNING]` | `invalid_text_representation` (22P02) | No row stored | DB |
| AC1-N5 | AC1 | A request for an unknown venue is refused | Negative | No venue with that id | Insert | random `venue_id` | `foreign_key_violation` (23503) | No row stored | DB |
| AC1-N6 | AC1 | A missing requester is refused | Negative | A venue exists | Insert | `requested_by` NULL | `not_null_violation` (23502) | No row stored | DB |
| AC1-N7 | AC1 | A missing event is refused | Negative | A venue exists | Insert | `event_request_id` NULL | 23502 | No row stored | DB |
| AC1-N8 | AC1 | A missing start date is refused | Negative | A venue exists | Insert | `start_date` NULL | 23502 | No row stored | DB |
| AC1-N9 | AC1 | A missing end date is refused | Negative | A venue exists | Insert | `end_date` NULL | 23502 | No row stored | DB |
| AC1-N10 | AC1 | A missing slot list is refused | Negative | A venue exists | Insert | `slots` NULL | 23502 | No row stored | DB |
| AC1-X1 | AC1 | A venue that has requests cannot be deleted | Cross-cutting | A request exists for the venue | Delete the venue | the venue's id | 23503 | The venue and its requests remain | DB |
| AC2-H1 | AC2 | The snapshot is stored exactly as given | Happy | A venue exists | Insert, read back | name "Annual Gala", attendance 120, note "Stage and projector" | The three values are returned unchanged | none | DB |
| AC2-P1 | AC2 | A snapshot with no values is accepted, because the source event may lack them | Partition | A venue exists | Insert | all three snapshot fields NULL | Row stored | none | DB |
| AC3-H1 | AC3 | A pending request is in the pending queue and an approved one is not | Happy | A pending and an approved request exist | Query `status = 'pending'` | the two ids | The pending id is returned; the approved id is not | none | DB |
| AC3-X1 | AC3 | The lookup indexes exist | Cross-cutting | Migration applied | Query `pg_indexes` | the four index names | All four present | none | DB |
| AC4-H1 | AC4 | Two identical pending requests coexist | Happy | A venue exists | Insert twice | same venue, dates and slots | Both rows stored; no uniqueness error | none | DB |
| AC4-X1 | AC4 | Submitting requests leaves the venue row unchanged | Cross-cutting | The venue row is captured first | Insert several requests | n/a | The venue row is identical before and after | No venue write or booking row | DB |
| AC5-P1 | AC5 | An approved request with a decider and time is accepted | Partition | A venue exists | Insert | status approved, `decided_by`, `decided_at` | Row stored | none | DB |
| AC5-P2 | AC5 | A rejected request with a reason and no alternative is accepted | Partition | A venue exists | Insert | status rejected, decider, time, reason | Row stored | none | DB |
| AC5-P3 | AC5 | A rejected request with a reason and an alternative is accepted | Partition | A venue exists | Insert | as AC5-P2 plus `suggested_alternative` | Row stored | none | DB |
| AC5-N1 to AC5-N4 | AC5 | A pending request with any one decision field set is refused | Negative | A venue exists | Insert | pending plus `decided_by`, or `decided_at`, or `decision_reason`, or `suggested_alternative` | 23514 | No row stored | DB |
| AC5-N5 | AC5 | An approved request without a decider is refused | Negative | A venue exists | Insert | approved, `decided_at` only | 23514 | No row stored | DB |
| AC5-N6 | AC5 | An approved request without a decision time is refused | Negative | A venue exists | Insert | approved, `decided_by` only | 23514 | No row stored | DB |
| AC5-N7 | AC5 | An approved request with a reason is refused | Negative | A venue exists | Insert | approved with decider, time and reason | 23514 | No row stored | DB |
| AC5-N8 | AC5 | An approved request with an alternative is refused | Negative | A venue exists | Insert | approved with decider, time and alternative | 23514 | No row stored | DB |
| AC5-N9 | AC5 | A rejected request with no reason is refused | Negative | A venue exists | Insert | rejected with decider and time, no reason | 23514 | No row stored | DB |
| AC5-N10 | AC5 | A rejected request with a blank reason is refused | Negative | A venue exists | Insert | rejected, reason of three spaces | 23514 | No row stored | DB |
| AC5-N11 | AC5 | A rejected request without a decider is refused | Negative | A venue exists | Insert | rejected with reason and time, no decider | 23514 | No row stored | DB |
| AC5-N12 | AC5 | A rejected request without a decision time is refused | Negative | A venue exists | Insert | rejected with reason and decider, no time | 23514 | No row stored | DB |
| AC5-N13 | AC5 | An unknown status value is refused | Negative | A venue exists | Insert | status `cancelled` | 22P02 | No row stored | DB |
| AC6-X1 | AC6 | Browser roles have no direct privilege on the table | Cross-cutting | Migration applied | Check `anon` and `authenticated` for SELECT, INSERT, UPDATE, DELETE | n/a | All eight checks are false | none | DB |
| AC6-X2 | AC6 | Row-level security is enabled | Cross-cutting | Migration applied | Read `relrowsecurity` | n/a | true | none | DB |
| AC6-X3 | AC6 | The service role can read, insert and update | Cross-cutting | Migration applied | Check `service_role` for SELECT, INSERT, UPDATE | n/a | All three are true | none | DB |

### Planned: API and service layer (not yet designed)

To be written as concrete cases before the API work starts on 5 October 2026, then added to this matrix:

- **Submission:** the happy path; each partition of caller (the assigned Coordinator; a different Coordinator; the owning organiser alone; Venue Staff; an unauthenticated caller); the event lookups failing (not found, not assigned, eventRequestService unavailable); a malformed body; the snapshot taken from the event and not from the request body.
- **Queue and reads:** Venue Staff see pending requests only; a Coordinator sees only their own; another Coordinator's request returns 404; refused calls store and change nothing.
- **Cross-cutting:** missing and expired tokens; reassignment between the lookup and the insert.

### Latest execution record

| ID | Automation status | Actual result | Execution status | Build or commit | Remarks and evidence |
| --- | --- | --- | --- | --- | --- |
| AC1-H1 to AC6-X3 (all 44 database cases) | Green | Red run stopped at the first insert (`42P01`). After `0018` was applied the script ran to the end with no error, and the SQL Editor reported "Success. No rows returned" | Pass (inferred, see remarks) | Uncommitted draft | Run by Kennedy on 4 October 2026 in the Supabase SQL Editor on the shared development project. The editor does not display the final `RAISE NOTICE`, so the pass is inferred from the absence of an error: every case raises on failure. AC6-X1 was also confirmed independently through the Data API. |

## Latest verification

**Red run, 4 October 2026.** Kennedy pasted `database/verify_venue_booking_requests.sql` into the Supabase SQL Editor on the shared development project before applying `0018`. It stopped with:

```text
ERROR:  42P01: relation "public.venue_booking_requests" does not exist
CONTEXT:  PL/pgSQL function inline_code_block line 26 at SQL statement
```

That is the statement for AC1-H1, the first insert into the new table. It shows that the temporary table, the three helper functions and the throwaway venue insert into the live `venues` table all ran before the failure. It proves no behaviour: no case was reached, so nothing in the matrix has passed.

The SQL Editor raised two warnings before running (an `UPDATE` without a `WHERE`, and a table created without row-level security). Both refer to the one-row `TEMP` table `verify_ctx`, which only this session can see and which is dropped on rollback, so the script was run without enabling RLS.

**Cleanup check, 4 October 2026.** A read-only Data API query found no venue named `VERIFY venue` after the aborted run, and the Data API returned 404 for `venue_booking_requests`, which confirms the table does not exist yet.

**Migration, 4 October 2026.** Kennedy applied `database/migrations/0018_venue_booking_requests.sql` in the SQL Editor on the shared development project. The editor reported "Success. No rows returned".

**Green run, 4 October 2026.** Kennedy ran `database/verify_venue_booking_requests.sql` again. The editor reported "Success. No rows returned", with no error. Every case in the script raises an exception when it fails, so a run that ends without one means all 44 cases passed. The editor does not show the closing notice, so this is an inference and not a printed confirmation.

**Independent checks through the Data API, 4 October 2026** (read-only, run from the development session):

| Check | Result |
| --- | --- |
| Service role reads `venue_booking_requests` | 200, 0 rows, so the table exists and the rolled-back run left no rows (AC6-X3, partly) |
| Venues named `VERIFY venue` | 0, so the throwaway venue was rolled back |
| Browser role (publishable key) reads `venue_booking_requests` | 401, code `42501`, "permission denied for table venue_booking_requests" (AC6-X1 through the real API path) |

**Noted outside this story.** The same browser-role query on `venues` returns 200 with no rows while the service role sees 1 row. Row-level security is hiding the rows, but the browser role still holds a table privilege there, unlike `0016_venues.sql`, which revokes it. No data is exposed while RLS stays on with no policy; it is a gap between that migration and the live table.

**Not yet evidenced:** the API layer (planned, not designed), pull-request CI, and the integrated stack.

## Disclosures

- The migration and verification script were drafted by Claude Code and then run by Kennedy (Red, then Green, 4 October 2026). The Green result is inferred from the absence of an error. The test-design review is **pending (Kennedy)**.
- The AC review above was **approved as proposed by Kennedy on 4 October 2026**. Assumptions A1 to A4 and question Q1 were presented with it and are not separately confirmed.
