# SCRUM-9 — Search and Filter Venues

**Jira:** [SCRUM-9](https://is212g9t4.atlassian.net/browse/SCRUM-9)

**User story:** As an Event Coordinator, I want to search and filter venues by an event's requirements, so that I can shortlist the venues that can hold the event.

**How this document was made.** The story was built in Sprint 1 (done on 19 September 2026) and this record was written afterwards, on 1 November 2026. The acceptance criteria below are the Jira text as it stands today; the review is a proposal that the story owner or Product Owner has not approved yet. Nearly all of the automated tests existed before this document, so none of them was seen failing first (`testing.md` §5). The tests marked "new" were written for this document; they all passed on first run, so they found no defect and fill gaps in the record. One discrepancy was found and is recorded under *Open questions*.

## Story contract review

The acceptance criteria were checked against Week 4 core feature 10 (*Venue Search and Filtering*), Week 7 Customer Change #1, GitHub Discussions #112 (capacity varies by room layout), #131 (15-minute booking unit, 07:00–24:00 window) and #134 (no fixed list of facilities or accessibility features), and against the venueService code.

| Original criterion | Outcome | Reason |
| --- | --- | --- |
| AC1. The Event Coordinator can filter venues by: date and time range, required capacity, location, accessibility, supported layout, required facilities. | Clarify | "Date and time range" is one date with a start and an end time in 15-minute steps (#131); a date alone asks for some free time that day; times without a date are refused. "Location" is part of the name, ignoring case. Facilities and accessibility are lists of which every requested item must be offered (#134: no fixed list). |
| AC2. The search shows only the venues that match all the filters that the Event Coordinator applied. | Keep | Testable as written. |
| AC3. Each result shows the venue's name, location, maximum capacity, supported layouts, facilities and accessibility. | Keep | Results also carry setup and turnaround time (SCRUM-59) and a held-tentatively marker (SCRUM-18); those are owned by those stories. |
| AC4. The search does not show a venue with a maximum capacity less than the required capacity. | Clarify | When a layout is chosen, that layout's own capacity is used instead of the maximum (Q&A #112, hotfix 12). |
| AC5. The search does not show a venue that is unavailable, or that has a block or an approved booking in the requested time range. | Clarify | "In the requested time range" includes the venue's setup and turnaround time around an approved booking (SCRUM-59, SCRUM-66). A pending, rejected or cancelled request, a lifted block and a tentative hold do not hide a venue. |
| AC6. Only Event Coordinators, Venue Staff members and Safety Officers can search venues. The system refuses a search from any other role. | Clarify | The service refuses with 403 for a signed-in user with none of those roles and 401 with no session. The web page admits only Event Coordinators and Venue Staff (see *Open questions*). |

Approval of this review: **not recorded.** Replace this line with the approver and date once the story owner or Jaren (Product Owner) has approved it.

## Increment scope

- **Included:** `GET /venues/search` in venueService with its filters and result shape; the venue search page and its query building (`frontend/app/venues/search`, query building in `frontend/lib/venue-form.ts`).
- **Excluded:** the suitability check on a result (SCRUM-12); the availability calendar (SCRUM-31); booking requests (SCRUM-32); tentative holds (SCRUM-18); blocks (SCRUM-23); setup and turnaround time (SCRUM-59, SCRUM-66). Their tests are cited below only where they prove an AC of this story. Saved searches and sorting are a UI question (Discussion #27) and are not required.
- **Actors and access:** Event Coordinator, Venue Staff and Safety Officer can search. Every other role gets 403 and nothing is returned; a request with no session gets 401.
- **State and persistence:** none. A search only reads; it never changes a venue, block, booking or hold.
- **Team proposals:** location is a case-insensitive "contains" match; a required capacity of zero or less is refused with 422 (the story does not say so; raise it at the review).

## Acceptance criteria

- **AC1:** Given an Event Coordinator, Venue Staff member or Safety Officer, when they search, then they can narrow the venues by any combination of a date with a start and end time (15-minute steps, 07:00–24:00), required capacity, location, accessibility features, a supported layout and required facilities.
- **AC2:** Given several filters, when a search runs, then only venues that match every filter applied are shown; with no filter, every available venue is shown.
- **AC3:** Given a search result, when it is shown, then it has the venue's name, location, maximum capacity, supported layouts, facilities and accessibility features.
- **AC4:** Given a required capacity, when a search runs, then no venue below it is shown: a venue of exactly that capacity is shown; with a layout chosen, that layout's capacity is the one compared.
- **AC5:** Given a date and time range, when a search runs, then a venue that is out of service, or has an active block or an approved booking (with its setup and turnaround time) overlapping that range, is not shown.
- **AC6:** Given a signed-in user, when they search, then it is allowed only for an Event Coordinator, Venue Staff member or Safety Officer (alone or with other roles); any other role is refused and nothing is returned.

## Test-case specification

Tests that belong to other stories keep the case IDs they were written under; they are cited by file and name.

| ID | AC | Test scenario | Technique | Pre-conditions | Test steps | Test data | Expected result | Forbidden side effects | Layer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AC1-H1 | AC1 | The form sends every filter | Happy | Search form | Fill all six filters; build the query | date, times, capacity 120, "marina", ramp, theatre, projector, stage | Every filter is in the query; list filters repeated | — | UI unit |
| AC1-H2 | AC1, AC5 | A date and time range hides a venue only for the overlapping time | Happy | Venue with a block or approved booking 10:00–12:00 | Search 10:00–12:00, then 13:00–15:00 | Same day | Hidden at 10:00–12:00; offered at 13:00–15:00 | — | API |
| AC1-P1 | AC1 | Location matches part of a name, ignoring case | Partition | "Marina Bay" and "Tampines" | `GET /venues/search?location=marina` | "marina" | Only Marina Bay | — | API |
| AC1-P2 | AC1 | Layout keeps only venues that support it | Partition | Theatre and boardroom venues | `?layout=theatre` | theatre | Only the theatre venue | — | API |
| AC1-P3 | AC1 | Every requested facility must be offered | Partition | One venue with both, one with one | `?facility=projector&facility=microphone` | projector, microphone | Only the venue with both | — | API |
| AC1-P4 | AC1 | Every requested accessibility feature must be offered | Partition | One venue with both, one with one | `?accessibility=ramp&accessibility=hearing_loop` | ramp, hearing_loop | Only the venue with both | — | API |
| AC1-P5 | AC1, AC4 | Required capacity hides a smaller venue | Partition | 50 and 300 | `?required_capacity=100` | 100 | Only the 300 venue | — | API |
| AC1-P6 | AC1 | A time range does not exclude a venue by its old operating slots | Partition | Venues with NIGHT only and AM only slots | Search 18:00–20:00 on one date | — | Both offered (every venue runs 07:00–24:00, #131) | — | API |
| AC1-P7 | AC1 | A date alone offers a venue with no block or booking | Partition | One venue | `?date=2026-10-01` | — | The venue is shown | — | API |
| AC1-P8 | AC1, AC2 | An untouched form does not search | Partition | Search form | Build the query with nothing filled in | — | No query | No request sent | UI unit |
| AC1-B1 | AC1 | With only a date, a venue needs some free time that day | Boundary | Venue booked for most of a day | Search the date only | — | Offered while any free time remains; hidden when none | — | API |
| AC1-N1 | AC1 | Invalid times, or times without a date, are refused | Negative | — | Search with an off-step time, a time outside 07:00–24:00, an end not after the start, a start with no end, and times with no date | 610; 405; 720–720; 600 only; no date | 422 with the reason code for each | Nothing returned | API |
| AC1-N2 | AC1 | A non-positive or non-integer capacity is reported, not sent | Negative | Search form | Enter 0, abc, 2.5, -1 | those values | Error shown; no query | No request sent | UI unit |
| AC1-N3 | AC1 | Values outside the allowed lists are dropped, not sent | Negative | Search form | Enter an unknown layout and slot | "spaceship" | Dropped from the query | No 422 from the service | UI unit |
| AC1-N4 | AC1 | An invalid time range, or times without a date, are reported before sending | Negative | Search form | Enter reversed or off-step times, or times with no date | see test | Error shown | No request sent | UI unit |
| AC1-N5 | AC1 | An impossible date is dropped | Negative | Search form | Enter 30 February | 2026-02-30 | Dropped from the query | No 422 from the service | UI unit |
| AC2-H1 | AC2 | Only the venue that matches every filter is shown | Happy | One match and venues failing one filter each (capacity, layout) | Search with location, capacity, facility, layout, date and times | see test | Only the match | — | API |
| AC2-N1 | AC2 | A venue failing a single filter is excluded | Negative | Same data as AC2-H1 | Same search | — | "WrongCapacity" and "WrongLayout" absent | — | API |
| AC2-P1 | AC2 | With no filter every available venue is shown | Partition | Two venues | `GET /venues/search` | — | Both | — | API |
| AC2-X1 | AC2, AC4, AC5 | A coordinator's results match every filter in the browser | Cross-cutting | Coordinator session; mock venue service | Filter by capacity and facilities | see spec | Matching venues only; none below the capacity; blocked venue absent | — | E2E |
| AC3-H1 | AC3 | A result carries the six shortlist attributes | Happy | One venue with every attribute | `GET /venues/search` | Orchard Hall, 180, theatre and boardroom, projector and stage, ramp | The result has all six, unchanged | — | API (new) |
| AC3-H2 | AC3 | The page shows those attributes for each result | Happy | Results | Render the results | — | Name, location, capacity, layouts, facilities, accessibility visible | — | UI unit |
| AC3-N1 | AC3 | No match is stated plainly | Negative | No results | Render | — | A clear "no venue matches" message | — | UI unit |
| AC4-H1 | AC4 | The capacity filter hides a smaller venue | Happy | 50 and 300 | `?required_capacity=100` | 100 | Only the 300 venue | — | API |
| AC4-B1 | AC4 | One below the maximum capacity is shown | Boundary | Venue of 100 | `?required_capacity=99` | 99 | Shown | — | API (new) |
| AC4-B2 | AC4 | Exactly the maximum capacity is shown | Boundary | Venue of 100 | `?required_capacity=100` | 100 | Shown | — | API (new) |
| AC4-B3 | AC4 | One above the maximum capacity is hidden | Boundary | Venue of 100 | `?required_capacity=101` | 101 | Hidden | — | API (new) |
| AC4-P1 | AC4 | A chosen layout's own capacity decides | Partition | Max 300; classroom 80 | `?required_capacity=100&layout=classroom` | 100, classroom | Hidden | — | API (new) |
| AC4-P2 | AC4 | A layout with no recorded capacity uses the maximum | Partition | Same venue | `?required_capacity=100&layout=theatre` | 100, theatre | Shown | — | API (new) |
| AC4-P3 | AC4 | With no layout chosen the maximum applies | Partition | Same venue | `?required_capacity=250` | 250 | Shown | — | API (new) |
| AC4-N1 | AC4 | A small venue is hidden even when everything else matches | Negative | 40-seat venue matching location, facility and layout | Search for 41 with those filters | 41 | No result | — | API (new) |
| AC5-H1 | AC5 | A venue out of service is not offered | Happy | One open, one blocked | `GET /venues/search` | status blocked | Only the open venue | — | API |
| AC5-H2 | AC5 | A block overlapping the range hides the venue, on both boundary dates | Happy | Venue with a date-range block | Search each boundary date and the days around | — | Hidden on the block's dates; offered on others | — | API |
| AC5-H3 | AC5 | An approved booking overlapping the range hides the venue | Happy | Approved booking | Search its date and time | — | Hidden | — | API |
| AC5-P1 | AC5 | Pending and rejected requests do not hide a venue | Partition | Pending, rejected request | Search that time | — | Offered | — | API |
| AC5-P2 | AC5 | A lifted block does not hide a venue | Partition | Lifted block | Search its dates | — | Offered | — | API |
| AC5-B1 | AC5 | Booking dates are inclusive at both ends | Boundary | Booking 20–21 October | Search 19, 21 and 22 October | — | Offered on the 19th, hidden on the 21st (its last day), offered on the 22nd | — | API |
| AC5-B2 | AC5 | Setup and turnaround time around a booking are respected | Boundary | Booking with setup 30, turnaround 45 | Search just inside and just outside the padded range | — | Hidden inside, offered at the exact gap | — | API |
| AC6-H1 | AC6 | An Event Coordinator can search | Happy | Role `event_coordinator` | `GET /venues/search` | — | 200 and the venues | — | API (new) |
| AC6-H2 | AC6 | A Venue Staff member can search | Happy | Role `venue_staff` | Same | — | 200 | — | API (new) |
| AC6-H3 | AC6 | A Safety Officer can search | Happy | Role `safety_officer` | Same | — | 200 | — | API (new) |
| AC6-P1 | AC6 | Several roles: one permitted role is enough | Partition | Roles `attendee` and `event_coordinator` | Same | — | 200 | — | API (new) |
| AC6-N1 | AC6 | Event Organiser refused | Negative | Role `event_organiser` | Same | — | 403; no venue in the body | — | API (new) |
| AC6-N2 | AC6 | Attendee refused | Negative | Role `attendee` | Same | — | 403 | — | API (new) |
| AC6-N3 | AC6 | Technical Support refused | Negative | Role `technical_support` | Same | — | 403 | — | API (new) |
| AC6-N4 | AC6 | Event Coordinator Lead refused | Negative | Role `event_operations_manager` | Same | — | 403 | — | API (new) |
| AC6-N5 | AC6 | Admin refused | Negative | Role `admin` | Same | — | 403 | — | API (new) |
| AC6-N6 | AC6 | No session is 401 | Negative | No override | Same | — | 401 | — | API (new) |
| AC6-X1 | AC6 | An Event Organiser cannot open the search page | Cross-cutting | Organiser session | Open `/venues/search` | — | Redirected to the unauthorised page | — | E2E |
| AC6-X2 | AC6 | An expired session goes to sign-in | Cross-cutting | Expired session | Open `/venues/search` | — | Sign-in, not results | — | E2E |
| AC6-X3 | AC6 | A Safety Officer can open the search page | Cross-cutting | Safety Officer session | Open `/venues/search` | — | The page opens (as the story says) | — | E2E |

AC6-X3 is **not automated and does not hold today**: `frontend/app/venues/search/page.tsx` line 18 admits only `event_coordinator` and `venue_staff`, and the navigation offers a Safety Officer no search link. See *Open questions*.

## Latest execution record

Build: `b5b53b0` (`dev` after PR #123) plus this branch's working tree (`docs/testcases-scrum-9-27-30`), run on Kennedy's machine on 1 November 2026 with Claude Code, pending human review. Backend tests ran against the in-memory venue store; the browser tests ran against the Node mock services. "Red first" was not observed for any case: the tests were written after the code, or (marked new) found nothing to fix.

| ID | Automation status | Actual result | Execution status | Build or commit | Executed by and date | Remarks and evidence |
| --- | --- | --- | --- | --- | --- | --- |
| AC1-H1, AC1-P8, AC1-N2, AC1-N3, AC1-N4, AC1-N5 | Green | Query built from every filter; empty form builds none; bad capacity, unknown values, impossible dates and bad times are reported or dropped | Pass | b5b53b0 + working tree, local | Claude Code, 1 Nov 2026 | `frontend/__tests__/venue-search.test.tsx` (16 passed). AC1-N4 is the test labelled SCRUM-65 AC4-N3 |
| AC1-P1, AC1-P2, AC1-P3, AC1-P4, AC1-P5, AC1-P6, AC1-P7, AC2-H1, AC2-N1, AC2-P1, AC4-H1, AC5-H1 | Green | Each filter, the combination and the no-filter case behave as specified | Pass | same | same | `backend/venueService/tests/test_venues_search.py` (10 passed); labels added on 1 Nov 2026 |
| AC1-H2, AC1-B1, AC1-N1, AC5-H2, AC5-H3, AC5-P1, AC5-P2, AC5-B1, AC5-B2 | Green | Time-range search, date-only rule, invalid-time 422s, blocks, bookings, padding | Pass | same | same | `test_block_search_times.py` (SCRUM-65 AC3-H2, AC4-H1, AC4-B1, AC4-N1), `test_block_availability.py` (SCRUM-23 AC2-*), `test_booked_availability.py` (SCRUM-23 AC3-*), `test_padded_availability.py` (SCRUM-66 AC1-*): 86 passed with `test_venue_layout_capacity.py` |
| AC3-H1, AC4-B1, AC4-B2, AC4-B3, AC4-P1, AC4-P2, AC4-P3, AC4-N1, AC6-H1, AC6-H2, AC6-H3, AC6-P1, AC6-N1, AC6-N2, AC6-N3, AC6-N4, AC6-N5, AC6-N6 | Green | Six attributes returned; capacity boundaries 99, 100, 101; layout capacity; permitted roles 200; every other role 403 with no venue returned; no session 401 | Pass | same | same | New: `backend/venueService/tests/test_venues_search_contract.py` (18 passed). Together with `test_venues_search.py`: 28 passed. These passed first time: no defect found |
| AC3-H2, AC3-N1 | Green | Results show the attributes; no match is stated | Pass | same | same | `frontend/__tests__/venue-search.test.tsx` |
| AC2-X1, AC6-X1, AC6-X2 | Green | Coordinator's results match every filter and exclude a blocked venue; organiser refused; expired session to sign-in | Pass | same | same | `frontend/e2e/venue-search.spec.ts` against the Node mock services (4 tests in the file; 14 passed across the five specs cited in this and the other two documents) |
| AC6-X3 | Not automated | The page admits only Event Coordinator and Venue Staff, found by reading `app/venues/search/page.tsx:18` | **Fail (not run)** | same | Claude Code, 1 Nov 2026 | Needs a decision: see *Open questions*. No test is written, because it would fail |

### Local validation evidence

| Check | Command and environment | Result | Remarks |
| --- | --- | --- | --- |
| Story tests, backend | `pytest tests/test_venues_search.py tests/test_venues_search_contract.py`, venueService, local Python 3.13 | 28 passed | Mock-free in-memory store; no network |
| Backend regression | `pytest` (whole venueService suite); `ruff check .` | 790 passed, 10 skipped; clean | 747 before the new files |
| Frontend unit | `npx vitest run` (whole frontend suite) | 80 files, 762 passed | jsdom |
| Frontend static checks | `npm run typecheck`; `npm run lint` | Clean | — |
| End-to-end | `playwright test venue-search venue-catalogue assign-coordinator auth.spec equipment-catalogue` with the cached Chromium 1148 headless shell | 14 passed | The pinned browser build is not installed and was not downloaded |

Not run: the shared development database, the venue search on the real database (hotfix 12's real-stack run checked the layout capacity path only), pull-request CI, reviewer approval.

## Open questions

1. **Safety Officer on the web page (AC6).** The service lets a Safety Officer search; the page does not. Either the page should admit `safety_officer` (and offer a link), or AC6 should say the Safety Officer reads venues through the safety check only. Needs the Product Owner's decision; the code was not changed.
2. **Required capacity of zero or less.** The code returns 422; the story is silent. Confirm or drop.
3. **Multi-day searches.** A search takes one date. If a coordinator needs a venue for a range of days, that is a new requirement.
