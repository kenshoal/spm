# SCRUM-61 Test Cases: Book Several Venues for One Event

Last reviewed: 17 October 2026

Status: **approved by the story owner (Kennedy) on 17 October 2026**, including assumptions A1 to A8 (A1 to A6 as proposed; Q1 and Q2 left open: the request form stays a stretch goal and cancellations send no notification). Nothing has been built yet; results are recorded below as work proceeds.

## Story

| Field | Value |
| --- | --- |
| Jira key | SCRUM-61 |
| Title | Book Several Venues for One Event |
| Sprint | Sprint 3 (ends 22 October 2026) |
| Points | 5 (pre-planning estimate) |
| User story | As a coordinator, I want to book more than one venue for the same event, so that a large event can use several rooms at once. |
| Source | Week 7 Customer Change #3, Multiple Venues for One Event. SCRUM-32 stays Done. |
| Blocks | SCRUM-63, Replace a Venue for an Affected Booking (Sprint 4) |

## Story contract

The four live Jira criteria (read on 17 October 2026) were reviewed with the vocabulary in `docs/standards/testing.md` §1.

| ID | Criterion | Review outcome | Reason |
| --- | --- | --- | --- |
| AC1 | The coordinator can request another venue for an event that already has one. | **Keep** | The SCRUM-32 submit endpoint already allows several requests per event (`event_request_id` is not unique). This AC is proved with tests and needs no new rule. |
| AC2 | Each venue is checked on its own (big enough, free, no clashes), and venue staff approve each one separately. | **Clarify, Split** | Two parts. (a) Each venue is judged on its own: suitability (SCRUM-12), blocks and operating slots (SCRUM-23), and clashes with other approved bookings at approval (SCRUM-15) are already per venue or per request. (b) Staff decide one request at a time. Both are proved by independence tests. Clash detection that also reads holds and setup or turnaround time is SCRUM-20 and SCRUM-59, not this story. |
| AC3 | The event page lists all of its venue bookings and where each one stands. | **Clarify** | "The event page" is the coordinator's event page (`/coordination/requests/{id}`). Needs a new read of an event's bookings and a panel on that page. Status is shown in words. |
| AC4 | Changing or cancelling one venue booking leaves the others as they are. | **Clarify, Split** | "Cancelling" is new: booking requests have no cancel today. "Changing" is taken as cancel plus a new request (A1); replacing a venue after a block is SCRUM-63. |

Expected change to scope: a new `cancelled` status (migration), one new read and one new action in venueService, and one panel on an existing page.

### Included and excluded behaviour

| | Behaviour | Jira |
| --- | --- | --- |
| Included | Proving that an event can hold several booking requests for different venues, each judged and decided on its own | SCRUM-61 |
| Included | `GET /booking-requests/event/{event_request_id}`: all bookings of one event | SCRUM-61 |
| Included | `POST /booking-requests/{id}/cancel`: cancel one pending or approved booking | SCRUM-61 |
| Included | A "Venue bookings" panel on the coordinator's event page, with a Cancel action | SCRUM-61 |
| Stretch | A "Request a venue" form in that panel. SCRUM-32 has no submit screen, so without it AC1 is API-only. Dropped first if time runs short | SCRUM-61 |
| Excluded | Replacing a venue after it becomes unavailable | SCRUM-63 |
| Excluded | Holds that expire, and clash checks against holds | SCRUM-18, SCRUM-20 |
| Excluded | Setup and turnaround time | SCRUM-59 |
| Excluded | "Needs review" flags on bookings after an event change | SCRUM-64 |
| Excluded | Notifying venue staff or the coordinator of a cancellation | SCRUM-37 |
| Excluded | The venue availability calendar | SCRUM-31 |

### Actors and relationship permissions

- Event Coordinator: lists and cancels the bookings of an event **only while currently assigned to it**, checked through eventRequestService with the caller's token on every call. A coordinator who submitted a request but was later reassigned loses access; the new coordinator gains it (decision 8 of SCRUM-32).
- Venue Staff: read any event's bookings. They do not cancel.
- Event Organisers and every other role: no access to booking requests.

### State transitions, persistence and atomicity

- New transitions: `pending` to `cancelled` and `approved` to `cancelled`. `rejected` and `cancelled` are final.
- Cancelling an approved booking frees its venue slots at once, because the approval and block checks only count `approved` requests.
- A cancelled request keeps who cancelled it and when. Its earlier decision fields stay as they were.
- Cancellation is one conditional update inside a database function that locks the request row, so two cancels, or a cancel racing an approval, cannot both succeed.
- `pending` to `cancelled` is refused for a request that has meanwhile been decided, and the reverse: a cancelled request can no longer be decided (the decide function already refuses anything that is not `pending`).

### Assumptions and open questions

| ID | Assumption or question | Used by |
| --- | --- | --- |
| A1 | "Changing" a booking means cancelling it and requesting again. Editing dates or slots in place is not built. | AC4 |
| A2 | Both pending and approved bookings can be cancelled. Rejected and cancelled ones cannot (409). | AC4-N1, AC4-N2 |
| A3 | Only Venue Staff and the event's currently assigned Coordinator can read an event's bookings. Organisers cannot. | AC3-N2 |
| A4 | There is no limit on the number of venues per event, and the same venue may be requested twice for different dates. | AC1 |
| A5 | A cancellation sends no notification (SCRUM-37 is out of scope). | none |
| A6 | A cancel needs no reason. | AC4 |
| A7 | The decide function reports a cancelled request as "already decided" (409), as it does for any request that is no longer pending. | AC4-X1 |
| A8 | The migration is split in two files because Postgres cannot use a new enum value in the transaction that adds it. Numbers 0041 and 0042 are claimed because open PRs already use 0029 to 0040. | AC4 |
| Q1 | Should the form to request a venue be part of this story (stretch), or is the API enough as for SCRUM-32? | AC1 |
| Q2 | Should venue staff be told when an approved booking is cancelled? | none |

## Test-case matrix

### Specification

| ID | AC | Test scenario | Technique | Pre-conditions | Test steps | Test data | Expected result | Forbidden side effects | Layer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AC1-H1 | AC1 | A second request for a different venue is accepted for an event that already has one | Happy | Event E assigned to the caller; venue A has a request for E | Submit a request for venue B and event E | valid body | 201, `pending`; E now has two requests; A's request unchanged | A's request is not touched | API |
| AC1-P1 | AC1 | The same venue can be requested again for other dates (A4) | Partition | As AC1-H1 | Submit for venue A, other dates | valid body | 201 | none | API |
| AC1-B1 | AC1 | Three venues for one event are all accepted | Boundary | As AC1-H1 | Submit for venues A, B and C | valid bodies | Three 201s; the event lists three requests | none | API |
| AC2-H1 | AC2 | Suitability is judged separately for each venue | Happy | Venue A capacity 50, venue B capacity 500, both with a request for the event | Run the suitability check against each | attendance 120 | A not suitable (capacity), B suitable | Neither venue changed | API |
| AC2-H2 | AC2 | Approving one booking leaves the other pending | Happy | Pending requests for A and B | Venue Staff approve A | decision approved | A `approved`, B still `pending` | B's fields unchanged | API |
| AC2-P1 | AC2 | Rejecting one booking, with a reason, leaves the other as it was | Partition | Requests for A and B | Venue Staff reject A | reason "Under repair" | A `rejected`; B unchanged | B not rejected | API |
| AC2-N1 | AC2 | A booking that cannot be approved (venue blocked) does not stop the other being approved | Negative | Active block on A; pending requests for A and B | Approve A; approve B | decision approved | A refused 409 and stays pending; B `approved` | A not approved | API |
| AC2-X1 | AC2 | Two venues can be approved for the same dates and slots (no cross-venue clash) | Cross-cutting | Requests for A and B, same dates and slots | Approve both | decision approved | Both `approved` | none | API |
| AC3-H1 | AC3 | An assigned coordinator lists every booking of an event, oldest first, each with its status | Happy | Event E with three requests | `GET /booking-requests/event/{E}` as the assigned coordinator | none | 200, three items oldest first, each with `status` | none | API |
| AC3-H2 | AC3 | Venue Staff list the bookings of any event | Happy | As AC3-H1 | Same call as `venue_staff` | none | 200, three items | none | API |
| AC3-P1 | AC3 | All four statuses are listed | Partition | Event with a pending, an approved, a rejected and a cancelled request | List | none | Four items with their four statuses | none | API |
| AC3-P2 | AC3 | Only the named event's bookings are returned | Partition | Two events, each with requests | List for E1 | E1 | Only E1's | E2's absent | API |
| AC3-B1 | AC3 | An event with no bookings returns an empty list | Boundary | E has no requests | List | E | 200, `[]` | none | API |
| AC3-N1 | AC3 | A coordinator not assigned to the event is refused | Negative | E assigned to someone else | List as another coordinator | E | 404 "Event request not found" | No bookings returned | API |
| AC3-N2 | AC3 | Organisers cannot read an event's bookings (A3) | Negative | Requests exist | List as `event_organiser` | E | 403 | No bookings returned | API |
| AC3-N3 | AC3 | A malformed event id is refused | Negative | none | List | "not-a-uuid" | 422 | none | API |
| AC3-N4 | AC3 | An unavailable event service gives 502, not an empty list | Negative | Event service fails (connect, timeout, 500) | List as a coordinator | E | 502 "Event request service unavailable" | No bookings returned | API |
| AC3-N5 | AC3 | A 401 from the event service is passed on | Negative | Event service answers 401 | List as a coordinator | E | 401 "Invalid session" | none | API |
| AC3-X1 | AC3 | A request without a token is refused | Cross-cutting | none | List with no `Authorization` | E | 401 | none | API |
| AC3-X2 | AC3 | The Supabase store asks for one event's rows oldest first | Cross-cutting | Mocked PostgREST transport | `list_for_event` | event id | `event_request_id=eq.<id>`, `order=created_at.asc,id.asc` | none | Unit |
| AC3-U1 | AC3 | The panel shows each booking's venue, dates, slots and status in words | Happy | Three bookings | Render the panel | statuses pending, approved, cancelled | One row per booking; status written out, not colour only | none | Component |
| AC3-U2 | AC3 | An event with no bookings says so | Boundary | No bookings | Render | none | "No venue bookings yet." | none | Component |
| AC3-U3 | AC3 | A failed load shows an error and never an empty list | Negative | The read fails | Render | none | Alert; no "No venue bookings yet." | none | Component |
| AC3-E1 | AC3 | In a browser a coordinator sees both of an event's bookings and their statuses | Happy | Event with two bookings, coordinator signed in | Open the event page | none | Both rows visible with their statuses | none | E2E |
| AC4-H1 | AC4 | Cancelling a pending booking leaves the others as they are | Happy | Pending requests for A and B | Cancel A as the assigned coordinator | A's id | 200, A `cancelled` with `cancelled_by` and `cancelled_at`; B unchanged | B's fields unchanged | API |
| AC4-H2 | AC4 | Cancelling an approved booking frees its slots and leaves the sibling approved | Happy | Approved A and B; a new pending request C for A's venue, dates and slots | Cancel A; approve C | A's id; decision approved | A `cancelled`; B still `approved`; C approves (200) | B unchanged | API |
| AC4-N1 | AC4 | A rejected booking cannot be cancelled (A2) | Negative | A rejected request | Cancel | its id | 409 | Status unchanged | API |
| AC4-N2 | AC4 | A cancelled booking cannot be cancelled again | Negative | A cancelled request | Cancel | its id | 409 | `cancelled_at` unchanged | API |
| AC4-N3 | AC4 | A coordinator not assigned to the event cannot cancel | Negative | E assigned to someone else | Cancel as another coordinator | its id | 404 "Event request not found" | Status unchanged | API |
| AC4-N4 | AC4 | Venue Staff and organisers cannot cancel | Negative | A pending request | Cancel as `venue_staff`; as `event_organiser` | its id | 403 for both | Status unchanged | API |
| AC4-N5 | AC4 | An unknown or malformed id returns 404 | Negative | none | Cancel | random uuid; "not-a-uuid" | 404 "Booking request not found" | none | API |
| AC4-N6 | AC4 | Cancel follows the current assignment, not the requester | Negative | Coordinator X submitted; the event is then reassigned to Y | Cancel as X; as Y | its id | X gets 404 and nothing changes; Y gets 200 | X's attempt changes nothing | API |
| AC4-N7 | AC4 | An unavailable event service gives 502 and cancels nothing | Negative | Event service fails | Cancel | its id | 502 | Status unchanged | API |
| AC4-X1 | AC4 | A cancelled booking can no longer be decided | Cross-cutting | A cancelled request | Venue Staff approve it | decision approved | 409 | Status stays `cancelled` | API |
| AC4-X2 | AC4 | A request without a token is refused | Cross-cutting | none | Cancel with no `Authorization` | its id | 401 | Status unchanged | API |
| AC4-X3 | AC4 | The staff queue and the approved list exclude cancelled requests | Cross-cutting | A cancelled request | `GET /booking-requests` and `?status=approved` | none | It is in neither; `?status=cancelled` lists it | none | API |
| AC4-X4 | AC4 | The Supabase store calls the cancel function and maps its errors | Cross-cutting | Mocked PostgREST transport | `cancel` | id, caller | `POST /rest/v1/rpc/cancel_venue_booking_request`; not found, not cancellable and failure map to their errors | none | Unit |
| AC4-D1 to AC4-D4 | AC4 | The table accepts `cancelled` only with `cancelled_by` and `cancelled_at`, and refuses them on other statuses | Negative | Migrations applied | Insert rows | cancelled without by; without at; pending with `cancelled_by`; cancelled with `decision_reason` | Each refused with 23514 | No row stored | DB |
| AC4-D5 | AC4 | The cancel function cancels a pending and an approved request, refuses the rest, and is server-only | Cross-cutting | Migrations applied | Run the function for each status; check `EXECUTE` grants | five statuses | Pending and approved cancel; rejected and cancelled raise 55000; unknown raises P0002; browser roles cannot execute | Refused calls change nothing | DB |
| AC4-D6 | AC4 | The existing booking-request cases still pass after the migration | Cross-cutting | Migrations applied | Run `verify_venue_booking_requests.sql` | none | All earlier cases pass. AC5-N13 used `cancelled` as its unknown status and is changed to another unknown value | none | DB |
| AC4-U1 | AC4 | Cancel is offered only for pending and approved bookings | Partition | Bookings in each status | Render | four statuses | A Cancel button on pending and approved rows only | none | Component |
| AC4-U2 | AC4 | The cancel action sends one POST and refreshes the panel | Happy | A pending booking | Submit Cancel | its id | One `POST .../cancel`; panel revalidated | No other call | Unit |
| AC4-U3 | AC4 | Failures are explained and 401 goes to sign-in | Negative | The API answers 404, 409, 403, 5xx and 401 | Submit Cancel | each status | A specific message for each; 401 redirects to `/auth` | No stale success message | Unit |
| AC4-E1 | AC4 | In a browser, cancelling one of two bookings leaves the other showing | Happy | Event with two bookings | Cancel the first | none | First shows `cancelled`; second unchanged | none | E2E |

### Existing tests that this story must change

- SCRUM-32 `AC3-N1` (`test_unknown_status_filter_is_refused` in `tests/test_booking_requests_read.py`) uses `status=cancelled` as its invalid value. `cancelled` becomes valid, so the test moves to another unknown value.
- SCRUM-32 DB case `AC5-N13` in `database/verify_venue_booking_requests.sql` uses `cancelled` as its unknown status. Same change.

### Latest execution record

Nothing has been run for this story yet.

## Disclosures

- This document, its assumptions and the cases were drafted by Claude Code on 17 October 2026 and **approved by the story owner the same day**, before any code was written.
- Reads of Jira and the repository on 17 October 2026 found no existing branch, code or migration for SCRUM-61.
