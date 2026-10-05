# SCRUM-32 Test Cases: Submit a Venue Booking Request

Last reviewed: 5 October 2026

Status: **the AC review below was approved as proposed by the story owner (Kennedy) on 4 October 2026, and Kennedy approved the API test cases on 5 October 2026** (assumptions A1 to A9 and questions Q1 and Q2 are not separately confirmed). The database layer passed on 4 October 2026. The API and service layer was built Red first on 5 October 2026, and its local results are recorded below. Nothing here has been through pull-request CI or the integrated stack yet.

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
| Excluded | A frontend screen | None built yet (Q4: to confirm with the team, as for SCRUM-12) |

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

### Specification: API and service layer (proposed 5 October 2026, awaiting approval)

Endpoints under test, all in venueService:

| Endpoint | Caller | Purpose |
| --- | --- | --- |
| `POST /booking-requests` | `event_coordinator` | Submit a request. Body: `venue_id`, `event_request_id`, `start_date`, `end_date`, `slots`. Returns 201 with the pending request |
| `GET /booking-requests?status=` | `venue_staff` | The queue. `status` is `pending` (default), `approved` or `rejected`, oldest first |
| `GET /booking-requests/mine` | `event_coordinator` | The caller's own requests, newest first |
| `GET /booking-requests/{id}` | `venue_staff` (any), `event_coordinator` (own only) | One request with its current status |

Submission order: authenticate (401), check the role (403), validate the body (422), find the venue (404), confirm with eventRequestService that the caller is the event's current Coordinator (404, 401 or 502), read the event for the snapshot, insert. `requested_by` comes from the verified token; the body may not carry `requested_by`, `status` or any snapshot field. eventRequestService is called with the caller's own token and replaced by a fake in the API tests; the store is the in-memory store, and the Supabase store is tested against a mocked transport.

"Nothing stored" in a case means the store holds no booking request and no call other than the listed ones was made.

| ID | AC | Test scenario | Technique | Pre-conditions | Test steps | Test data | Expected result | Forbidden side effects | Layer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AC1-H3 | AC1 | The assigned Coordinator submits a single-day, one-slot request | Happy | Venue exists; fake event assigned to the caller | `POST /booking-requests` | 2030-01-10 to 2030-01-10, `[AM]` | 201; status `pending`; `venue_id`, `event_request_id`, dates and slots echoed; `requested_by` is the caller's id from the token; one stored row | No second row | API |
| AC1-H4 | AC1 | A multi-day request with all three slots is stored | Happy | As AC1-H3 | `POST /booking-requests` | 2030-01-10 to 2030-01-12, `[AM, PM, NIGHT]` | 201; both dates and all three slots returned | none | API |
| AC1-B4 | AC1 | An end date one day before the start is refused | Boundary | As AC1-H3 | `POST /booking-requests` | start 2030-01-10, end 2030-01-09 | 422 on `body.end_date` | Nothing stored | API |
| AC1-B5 | AC1 | An end date equal to the start is accepted (inclusive) | Boundary | As AC1-H3 | `POST /booking-requests` | start and end 2030-02-01 | 201 | none | API |
| AC1-B6 | AC1 | An end date one day after the start is accepted | Boundary | As AC1-H3 | `POST /booking-requests` | start 2030-02-01, end 2030-02-02 | 201 | none | API |
| AC1-P4 to AC1-P6 | AC1 | Each slot value alone is accepted (AM, PM, NIGHT) | Partition | As AC1-H3 | `POST /booking-requests` | one slot per case | 201; that slot returned | none | API |
| AC1-P7 | AC1 | A request for dates in the past is accepted (A1) | Partition | As AC1-H3 | `POST /booking-requests` | 2020-01-10 to 2020-01-10 | 201, status `pending` | none | API |
| AC1-P8 | AC1 | A request for a blocked venue is accepted (A1) | Partition | Venue status `blocked` | `POST /booking-requests` | valid body | 201, status `pending` | none | API |
| AC1-N11 to AC1-N13 | AC1 | The body may not set `requested_by`, `status` or a snapshot field | Negative | As AC1-H3 | `POST /booking-requests` | valid body plus `requested_by`, or `status` "approved", or `event_name` | 422, error type `extra_forbidden` | Nothing stored; no event lookup | API |
| AC1-N14 | AC1 | An empty slot list is refused | Negative | As AC1-H3 | `POST /booking-requests` | `slots` `[]` | 422 on `body.slots` | Nothing stored | API |
| AC1-N15 | AC1 | A duplicate slot is refused | Negative | As AC1-H3 | `POST /booking-requests` | `[AM, AM]` | 422 on `body.slots` | Nothing stored | API |
| AC1-N16 | AC1 | An unknown slot value is refused | Negative | As AC1-H3 | `POST /booking-requests` | `[MORNING]` | 422, error type `enum` | Nothing stored | API |
| AC1-N17, AC1-N18 | AC1 | Slots that are null or missing are refused | Negative | As AC1-H3 | `POST /booking-requests` | `slots` null; `slots` omitted | 422 | Nothing stored | API |
| AC1-N19, AC1-N20 | AC1 | A missing start date or end date is refused | Negative | As AC1-H3 | `POST /booking-requests` | `start_date` omitted; `end_date` omitted | 422 | Nothing stored | API |
| AC1-N21 | AC1 | A date that does not exist is refused | Negative | As AC1-H3 | `POST /booking-requests` | `start_date` "2030-02-30" | 422 | Nothing stored | API |
| AC1-N22, AC1-N23 | AC1 | A missing venue or event reference is refused | Negative | As AC1-H3 | `POST /booking-requests` | `venue_id` omitted; `event_request_id` omitted | 422 | Nothing stored | API |
| AC1-N24 | AC1 | An event reference that is not a UUID is refused before any lookup | Negative | As AC1-H3 | `POST /booking-requests` | `event_request_id` "not-a-uuid" | 422 | Nothing stored; no call to eventRequestService | API |
| AC1-N25 | AC1 | An unknown venue returns 404 | Negative | No venue with that id | `POST /booking-requests` | random `venue_id` | 404, detail "Venue not found" | Nothing stored | API |
| AC1-N26 | AC1 | A request without a bearer token is refused | Negative | Venue exists | `POST /booking-requests` with no `Authorization` | valid body | 401, detail "Authentication required" | Nothing stored; no event lookup | API |
| AC1-X2 | AC1 | The Supabase store posts the row to `venue_booking_requests` and returns what it stored | Cross-cutting | Mocked PostgREST transport | `create` | a request | `POST /rest/v1/venue_booking_requests` with `Prefer: return=representation`; the returned row is parsed | none | Unit |
| AC2-H2 | AC2 | The snapshot is copied from the event, not from the caller | Happy | Fake event named "Annual Gala", attendance 120, venue requirements "Stage and projector" | `POST /booking-requests` | valid body | 201 with `event_name`, `expected_attendance`, `requirements_note` equal to the event's values | none | API |
| AC2-P2 | AC2 | An event with no name, attendance or requirements still yields a request | Partition | Fake event with all three missing | `POST /booking-requests` | valid body | 201 with the three snapshot fields null | none | API |
| AC2-X1 | AC2 | The snapshot does not change when the event is edited afterwards | Cross-cutting | A request exists; the fake event is then renamed and its attendance changed | `GET /booking-requests/{id}` | the request id | The original name and attendance are returned | none | API |
| AC3-H2 | AC3 | A submitted request appears in the pending queue with status pending | Happy | One submitted request | `GET /booking-requests` as `venue_staff` | none | 200, one item, status `pending`, same id | none | API |
| AC3-H3 | AC3 | The queue is oldest first | Happy | Three requests submitted in turn | `GET /booking-requests` | none | Items in submission order | none | API |
| AC3-P1 | AC3 | The default queue excludes approved and rejected requests | Partition | One pending, one approved, one rejected (seeded in the store) | `GET /booking-requests` | none | Only the pending request | none | API |
| AC3-P2 | AC3 | `status=approved` returns only approved requests | Partition | As AC3-P1 | `GET /booking-requests?status=approved` | none | Only the approved request | none | API |
| AC3-B1 | AC3 | An empty queue returns an empty list | Boundary | No requests | `GET /booking-requests` | none | 200, `[]` | none | API |
| AC3-N1 | AC3 | An unknown status filter is refused | Negative | none | `GET /booking-requests?status=cancelled` | none | 422 | none | API |
| AC3-N2, AC3-N3 | AC3 | Coordinators and organisers cannot read the queue | Negative | A pending request exists | `GET /booking-requests` | caller role `event_coordinator`; caller role `event_organiser` | 403, detail "Insufficient permissions" | No data returned | API |
| AC3-X2 | AC3 | An unauthenticated caller cannot read the queue | Cross-cutting | A pending request exists | `GET /booking-requests` with no token | none | 401 | No data returned | API |
| AC3-X3 | AC3 | The Supabase store asks for pending rows oldest first | Cross-cutting | Mocked PostgREST transport | `list(status="pending")` | none | `GET` with `status=eq.pending` and `order=created_at.asc,id.asc` | none | Unit |
| AC4-H2 | AC4 | Two identical pending requests from one Coordinator coexist | Happy | As AC1-H3 | Submit the same body twice | identical bodies | Both 201 with different ids; both in the queue | No uniqueness error | API |
| AC4-H3 | AC4 | Pending requests from two Coordinators for the same venue, dates and slots coexist | Happy | Two events, one per Coordinator | Each submits the same venue, dates and slots | identical venue, dates, slots | Both 201; both pending | Neither request blocks the other | API |
| AC4-X2 | AC4 | Submitting leaves the venue unchanged and writes nothing but the request | Cross-cutting | Venue captured first | Submit three requests | n/a | `GET /venues/{id}` identical before and after; the store holds exactly three requests | No venue update, block or booking | API |
| AC5-H1 | AC5 | A Coordinator sees only their own requests, newest first | Happy | Two requests by this Coordinator, one by another | `GET /booking-requests/mine` | none | The two own requests, newest first, each with its status | The other Coordinator's request is absent | API |
| AC5-H2 | AC5 | A Coordinator opens their own request and sees its status | Happy | One own request | `GET /booking-requests/{id}` | the id | 200, status `pending` | none | API |
| AC5-P4 | AC5 | An approved request shows as approved | Partition | An approved request seeded for this Coordinator | `GET /booking-requests/{id}` | the id | 200, status `approved`, decider and time present, no reason | none | API |
| AC5-P5 | AC5 | A rejected request shows its reason and suggested alternative | Partition | A rejected request seeded for this Coordinator | `GET /booking-requests/{id}` | the id | 200, status `rejected`, reason and alternative present | none | API |
| AC5-N14 | AC5 | Another Coordinator's request returns 404, the same as an unknown id | Negative | A request by Coordinator A | `GET /booking-requests/{id}` as Coordinator B | A's request id | 404, detail "Booking request not found", identical to the unknown-id response | The request's existence and contents are not revealed | API |
| AC5-N15 | AC5 | An unknown id returns 404 | Negative | none | `GET /booking-requests/{id}` | random uuid | 404, detail "Booking request not found" | none | API |
| AC5-N16 | AC5 | A malformed id returns 404, not 500 | Negative | none | `GET /booking-requests/{id}` | "not-a-uuid" | 404 | none | API |
| AC5-N17 | AC5 | Organisers cannot read booking requests | Negative | A request exists | `GET /booking-requests/mine` and `GET /booking-requests/{id}` as `event_organiser` | the id | 403 for both | No data returned | API |
| AC5-X1 | AC5 | Venue Staff can open any request | Cross-cutting | A request by a Coordinator | `GET /booking-requests/{id}` as `venue_staff` | the id | 200 | none | API |
| AC5-X2 | AC5 | An unauthenticated caller is refused on every read | Cross-cutting | A request exists | `GET` the queue, `/mine` and `/{id}` with no token | none | 401 for all three | No data returned | API |
| AC5-X3 | AC5 | The Supabase store asks for a requester's rows newest first | Cross-cutting | Mocked PostgREST transport | `list_for_requester` | a user id | `requested_by=eq.<id>` and `order=created_at.desc,id.desc` | none | Unit |
| AC5-N18 | AC5 | The Supabase store treats a malformed id as absent without a request | Negative | Mocked transport that fails on any call | `get("not-a-uuid")` | n/a | Returns nothing | No call to Supabase | Unit |
| AC6-X4 | AC6 | A Coordinator not assigned to the event is refused | Cross-cutting | The fake event is assigned to another Coordinator | `POST /booking-requests` | valid body | 404, detail "Event request not found" | Nothing stored | API |
| AC6-X5 | AC6 | Venue Staff cannot submit | Cross-cutting | Caller role `venue_staff` | `POST /booking-requests` | valid body | 403 | Nothing stored; no event lookup | API |
| AC6-X6 | AC6 | An organiser cannot submit, even for their own event | Cross-cutting | Caller role `event_organiser` | `POST /booking-requests` | valid body | 403 | Nothing stored; no event lookup | API |
| AC6-N1 | AC6 | An event that does not exist is refused | Negative | The fake event service answers 404 | `POST /booking-requests` | valid body | 404, detail "Event request not found" | Nothing stored | API |
| AC6-N2 | AC6 | An unavailable event service gives 502, not a stored request | Negative | The fake raises a connection error; also a timeout; also a 500 reply | `POST /booking-requests` | valid body | 502, detail "Event request service unavailable" | Nothing stored | API |
| AC6-N3 | AC6 | A malformed reply from the event service gives 502 | Negative | The fake returns a body with no `coordinator_id` | `POST /booking-requests` | valid body | 502 | Nothing stored | API |
| AC6-N4 | AC6 | A 401 from the event service is passed on as 401 | Negative | The fake answers 401 | `POST /booking-requests` | valid body | 401, detail "Invalid session" | Nothing stored | API |
| AC6-X7 | AC6 | The event service is called with the caller's own token and the assignment is compared to the caller's id | Cross-cutting | `httpx.MockTransport` | Run the event client | token "abc" | `GET /event-requests/{id}/coordinator` then `GET /event-requests/{id}`, each with `Authorization: Bearer abc`; a different `coordinator_id` is reported as not assigned | No service-level credential is used | Unit |
| AC6-X8 | AC6 | A store failure gives 502 and nothing is reported as created | Cross-cutting | The store raises `SupabaseRepositoryError` | `POST /booking-requests` | valid body | 502 | No 201 returned | API |

### Assumptions added for the API layer

| ID | Assumption or question | Used by |
| --- | --- | --- |
| A5 | Venue Staff may list any status; the default is `pending`. The Jira criteria only name the pending queue. | AC3-P1, AC3-P2, AC3-N1 |
| A6 | A venue that does not exist is refused before eventRequestService is called. | AC1-N25 |
| A7 | The role check (403) happens before body validation (422). | AC6-X5, AC6-X6 |
| A8 | Errors for a request that is not the caller's, and for an unknown request, are identical (404), as the security standard asks. | AC5-N14 |
| A9 | `GET /booking-requests/{id}` and `/mine` are open to Venue Staff and Coordinators only; organisers never see booking requests. | AC5-N17 |
| Q2 | Should a request for a blocked venue or past dates be refused at submission instead of at decision time (A1)? | AC1-P7, AC1-P8 |
| Risk | The Coordinator is checked through eventRequestService just before the insert. A reassignment in the milliseconds between the check and the insert cannot be tested at this layer; the decision step re-reads the event, so it is recorded as a known limit, not a case. | AC6 |

### Latest execution record

| ID | Automation status | Actual result | Execution status | Build or commit | Remarks and evidence |
| --- | --- | --- | --- | --- | --- |
| AC1-H1 to AC6-X3 (all 44 database cases) | Green | Red run stopped at the first insert (`42P01`). After `0018` was applied the script ran to the end with no error, and the SQL Editor reported "Success. No rows returned" | Pass (inferred, see remarks) | Uncommitted draft | Run by Kennedy on 4 October 2026 in the Supabase SQL Editor on the shared development project. The editor does not display the final `RAISE NOTICE`, so the pass is inferred from the absence of an error: every case raises on failure. AC6-X1 was also confirmed independently through the Data API. |
| AC1-H3, AC1-H4, AC1-B4 to AC1-B6, AC1-P4 to AC1-P8 | Red then Green | Red: the suite failed to import the missing booking modules. Green: as expected | Pass (local, in-memory store, faked event service) | merge `06d82d6` + working tree | `tests/test_booking_requests_submit.py`: `test_assigned_coordinator_submits_a_pending_request`, `test_multi_day_request_with_all_slots_is_stored`, `test_end_date_boundary`, `test_each_slot_alone_is_accepted`, `test_past_dates_are_accepted`, `test_blocked_venue_is_accepted` |
| AC1-N11 to AC1-N26 | Red then Green | As expected | Pass (local) | as above | `test_server_owned_fields_cannot_be_set_by_the_caller`, `test_invalid_fields_are_refused`, `test_event_reference_must_be_a_uuid`, `test_unknown_venue_returns_404`, `test_submit_requires_authentication` |
| AC2-H2, AC2-P2 | Red then Green | As expected | Pass (local) | as above | `test_snapshot_is_copied_from_the_event`, `test_event_without_snapshot_values_still_yields_a_request` |
| AC2-X1 | Red then Green | Red: 404 on the missing read endpoint. Green: as expected | Pass (local) | as above | `tests/test_booking_requests_read.py::test_snapshot_is_unaffected_by_later_event_edits` |
| AC3-H2, AC3-H3, AC3-P1, AC3-P2, AC3-B1, AC3-N1 to AC3-N3, AC3-X2 | Red then Green | Red: 404 and 405 on the missing endpoints. Green: as expected | Pass (local) | as above | `tests/test_booking_requests_read.py` (queue tests). The first Green run failed `AC3-X2` because of a test set-up fault (the staff-role override was left in place); the test was fixed, not the service |
| AC4-H2, AC4-H3, AC4-X2 | Red then Green | As expected | Pass (local) | as above | `test_identical_pending_requests_coexist`, `test_requests_from_two_coordinators_coexist`, `test_submitting_leaves_the_venue_unchanged` |
| AC5-H1, AC5-H2, AC5-P4, AC5-P5, AC5-N14 to AC5-N17, AC5-X1, AC5-X2 | Red then Green | As expected | Pass (local) | as above | `tests/test_booking_requests_read.py` (read tests) |
| AC6-X4 to AC6-X6, AC6-N1 to AC6-N4, AC6-X7, AC6-X8 | Red then Green (the event-client unit tests in `tests/test_event_client.py` were written after the client, so not Red first) | As expected | Pass (local) | as above | `test_unassigned_coordinator_is_refused`, `test_only_coordinators_can_submit`, `test_unknown_event_is_refused`, `test_unavailable_event_service_gives_502`, `test_malformed_event_reply_gives_502`, `test_event_service_401_is_passed_on`, `test_callers_token_is_forwarded_to_the_event_service`, `test_store_failure_gives_502`; `tests/test_event_client.py` |
| AC1-X2, AC3-X3, AC5-X3, AC5-N18 | Red then Green | Red: the Supabase store module did not exist. Green: as expected | Pass (local, mocked Data API) | as above | `tests/test_supabase_booking_repository.py` |

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

**API and service layer, 5 October 2026.** Run from `backend/venueService` on Kennedy's machine (Python 3.13, `.venv`) by Claude Code, on the merge commit `06d82d6` plus the uncommitted SCRUM-32 working tree. The store is the in-memory store, authService is overridden, and eventRequestService is faked at the HTTP boundary, so the real client runs but the real services were **not** involved.

| Check | Command | Result |
| --- | --- | --- |
| Lint | `ruff check .` | All checks passed |
| New SCRUM-32 tests | `pytest tests/test_booking_requests_submit.py tests/test_booking_requests_read.py tests/test_supabase_booking_repository.py tests/test_event_client.py -q` | 79 passed |
| Whole venueService suite | `pytest -q` | 146 passed, 10 skipped (the skips are the untracked, live-database `tests/test_supabase_schema.py`) |

**Mutation check (manual, 5 October 2026).** Nine one-line faults were injected into the new code one at a time, and the whole suite was run for each. Every mutant made at least one test fail.

| Mutant | First failing test |
| --- | --- |
| M1 assignment compared with `==` instead of `!=` | `test_submitted_request_appears_in_the_pending_queue` |
| M2 request body accepts extra fields | AC1-N11 |
| M3 coordinator role check removed | `test_organisers_cannot_read_booking_requests` |
| M4 ownership check removed on read-one | AC5-N14 |
| M5 end date may not equal start | `test_submitted_request_appears_in_the_pending_queue` |
| M6 default queue status changed to approved | `test_submitted_request_appears_in_the_pending_queue` |
| M7 requirements note not copied | AC2-H2 |
| M8 my requests oldest first | AC5-H1 |
| M9 token not forwarded to the event service | AC6-X7 |

The suite was run with `-x`, so each row shows the first failure in file order, not necessarily the dedicated test.

**Not yet evidenced:** pull-request CI, and the integrated stack. No real eventRequestService, authService or Supabase `venue_booking_requests` row has been exercised through the new endpoints; the Compose file now passes `EVENT_REQUEST_API_URL` to venueService, which is also untested.

## Disclosures

- The migration and verification script were drafted by Claude Code and then run by Kennedy (Red, then Green, 4 October 2026). The Green result is inferred from the absence of an error. The test-design review is **pending (Kennedy)**.
- The AC review above was **approved as proposed by Kennedy on 4 October 2026**. Assumptions A1 to A4 and question Q1 were presented with it and are not separately confirmed.
- The API tests and code were drafted by Claude Code. The API test cases were approved by Kennedy on 5 October 2026 before any code was written, and the tests were written Red first, except the event-client unit tests, which were written after the client.
- The role check on submit (403) runs before body validation (422), and an unassigned Coordinator gets 404, as proposed (A7 and AC6-X4). Past dates and blocked venues are accepted at submission (A1, Q2 open).
- A reassignment between the assignment check and the insert cannot be caught at this layer. It is a known limit, not a tested case.
