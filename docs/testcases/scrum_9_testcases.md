# SCRUM-9 — Search and Filter Venues

Source: issue tracker SCRUM-9 (Event Coordinator shortlists venues). The four ACs below were pulled from the issue tracker on 1 November 2026 and are recorded as approved; this document and its labels were drafted by the test-case gap sweep on the same day.

Status: **AI-drafted test design, not yet reviewed by a teammate (`testing.md` §10). The issue tracker remains the source of truth.** The automated tests predate this document: this pass added label comments to them and designed the matrix, and ran no suite — every row below is **Not executed** and no pass/fail is claimed (`testing.md` §8).

> **Update from PR #125 (1 Nov 2026).** (1) issue tracker changed after this document was drafted: the Product Owner rewrote the ACs into AC1 to AC6 at 11:54 and added out-of-scope, dependencies and a change log at 16:23 and 16:28 ("the meaning did not change", approved by Heng Rui). This matrix still follows the earlier four bullets. They map as: new AC1 = AC1, new AC2 and AC3 = AC2, new AC4 = AC3, new AC5 = AC4, new AC6 (roles) = the AC2-X rows. Re-base the IDs onto the new ACs when the story owner reviews. (2) The gap this document called out (AC3-B1 to AC3-B3) is now automated, and the role cases are added as AC2-X2 to AC2-X11, in `backend/venueService/tests/test_venues_search_contract.py`. (3) One case does not hold: AC2-X12.

## Story contract

**User story:** As an Event Coordinator, I want to search and filter venues by my event's requirements, so that I can shortlist the venues that can host it.

### Acceptance criteria (approved, issue tracker 1 Nov 2026)

| ID | Criterion |
| --- | --- |
| AC1 | The Coordinator can filter venues by date/slot, required capacity, location, accessibility, supported layout, and required facilities. |
| AC2 | Results list only venues matching all applied filters, each showing key attributes. |
| AC3 | Given a capacity filter of N attendees, when results are shown, then no venue with maximum capacity below N appears. (Boundary: N−1, N, N+1.) |
| AC4 | Venues blocked/unavailable for the requested date-slot are excluded from results. |

### Included and excluded behaviour

| | Behaviour | Story / file |
| --- | --- | --- |
| Included | `GET /venues/search`: every filter, AND semantics, the capacity rule, and the exclusion of unavailable venues | SCRUM-9 |
| Included | The search form (query building and client-side validation) and the result cards (key attributes, no-match message) | SCRUM-9 frontend |
| Included | Role refusals on search and catalogue reads (401 / 403) | SCRUM-9 |
| Excluded | The suitability check on a search result | SCRUM-12 |
| Excluded | The `tentatively_held` flag on results | SCRUM-18 |
| Excluded | Creating the blocks and bookings that make a venue unavailable | SCRUM-23, SCRUM-31, SCRUM-32 |
| Excluded | The organiser route guard on `/venues/search` | SCRUM-27 |
| Excluded | The `/venues/locations` contract | SCRUM-13 |
| Excluded | Per-venue operating hours / slots | Retired by SCRUM-65 (assumption A1) |

### Actors and permissions

- **Event Coordinator** — the story actor; searches and shortlists (e2e session `coordinator-session`).
- **Venue Staff** and **Safety Officer** may also read search and the catalogue (`require_venue_viewer` in `backend/venueService/app/dependencies.py`).
- Every other role gets 403 (proven for attendee and Technical Support) and a missing session gets 401.

### Assumptions and open questions

| ID | Assumption or question | Used by |
| --- | --- | --- |
| A1 | AC1's "date/slot" has been implemented, since SCRUM-65 (discussion #131), as a **date plus an optional 07:00–24:00 time range in 15-minute steps**; per-venue operating slots no longer filter search (`test_slot_filter_matches_operating_slots` now asserts both venues come back, under SCRUM-65's AC4-P2 label). The issue tracker wording predates SCRUM-65 — the card owner should confirm the wording or close the point as superseded. | AC1-P6, AC1-N3, AC4-P1 |
| A2 | "Key attributes" (AC2) = name, location, maximum capacity, supported layouts, facilities and accessibility features, plus setup/turnaround times (SCRUM-59). | AC2-H2 |
| A3 | The capacity filter must be a positive whole number: the form reports `0`, `abc`, `2.5`, `-1` instead of sending them, and the API rejects `required_capacity <= 0` with 422 (`Query(gt=0)`). | AC1-N1 |
| A4 | "Unavailable" (AC4) means the venue's status is `blocked`, or, on a dated search, a venue block or an **approved** booking overlaps the requested time; a date-only search requires some free time within 07:00–24:00 that day; a pending booking reserves nothing. | AC4-H1, AC4-P1, AC4-P2, AC4-B1 |
| A5 | The AC3 boundary triple (N−1, N, N+1) is specified by the AC but **no automated test asserts it**: today's test uses capacities 50 and 300 against N = 100 (AC3-P1). AC3-B1 to AC3-B3 are this story's known coverage gap. | AC3-B1 to AC3-B3 |
| Q1 | The e2e test `organisers cannot open venue search` proves SCRUM-27's route guard; it is left unlabelled so this story does not claim another story's behaviour. | AC2-X1 |

## Test data used below

Invented examples to seed local runs (each automated test seeds its own equivalents, named in the remarks column):

| Venue | Location | Capacity | Facilities | Accessibility | Layouts | Status |
| --- | --- | --- | --- | --- | --- | --- |
| Marina Bay Suite | Marina Bay | 300 | Projector, Stage | Ramp access | theatre, banquet | available |
| Tampines Room | Tampines | 20 | Projector | — | boardroom | available |
| Bukit Timah Hall | Bukit Timah | 400 | Projector, Stage | — | theatre | blocked (`PATCH {"status": "blocked"}`) |

Dated searches use D = 2030-03-04 with the afternoon range 13:00–15:00 (`start_minute` 780, `end_minute` 900). The operating window is 07:00 (minute 420) to 24:00 (minute 1440). For AC3, N = 100 with boundary venues of 99, 100 and 101.

## Test case specification

Layer codes: **API** = `backend/venueService/tests/test_venues_search.py` (FastAPI route tests, in-memory store) unless another path is named; **UI** = `frontend/__tests__/venue-search.test.tsx` (Vitest); **E2E** = `frontend/e2e/venue-search.spec.ts` (Playwright). Cross-referenced rows run in SCRUM-65's `backend/venueService/tests/test_block_search_times.py`.

| ID | AC | Test scenario | Technique | Pre-conditions | Test steps | Test data | Expected result | Forbidden side effects | Layer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AC1-H1 | AC1 | Every filter is sent to the API from the form, lists as repeated parameters | Happy | Search form open | Fill every filter and submit; inspect the built query | capacity 80, location " East ", D 2026-11-14, 12:00–18:00, theatre, "Projector, WiFi", "Ramp access" | Query carries `required_capacity=80`, trimmed `location=East`, `date`, `start_minute=720`, `end_minute=1080`, `layout`, `accessibility`, and `facility` twice | No request with untrimmed or unparsed values | UI |
| AC1-P1 | AC1 | An untouched form sends no query | Partition | Search form open | Submit with nothing filled | none | `query` is null, no errors | No request sent | UI |
| AC1-P2 | AC1 | The location filter matches case-insensitively as a substring | Partition | Marina Bay Suite, Tampines Room (examples) | Search `location=marina` | "marina" | Only Marina Bay Suite returned | Tampines Room absent | API |
| AC1-P3 | AC1 | The layout filter keeps only venues supporting the layout | Partition | One theatre venue, one boardroom-only venue | Search `layout=theatre` | theatre | Only the theatre venue returned | Boardroom-only venue absent | API |
| AC1-P4 | AC1 | Every requested facility must be present (subset match) | Partition | Venues with 3 facilities and with 1 of them | Search with two `facility` parameters | projector, microphone | Only the venue holding both | The partial venue absent | API |
| AC1-P5 | AC1 | Every requested accessibility feature must be present | Partition | Venues with 2 features and with 1 of them | Search with two `accessibility` parameters | ramp, hearing_loop | Only the venue holding both | The partial venue absent | API |
| AC1-P6 | AC1, AC4 | A date-only search keeps a venue with no blocks or bookings that day | Partition | One venue, nothing recorded on the date | Search with `date` only | D = 2026-10-01 in the test | 200, the venue returned | — | API |
| AC1-P7 | AC1 | A layout value outside the enum is dropped instead of causing a 422 | Partition | Search form open | Enter layout "ballroom" and a location, submit | ballroom, East | Query is `location=East` only; no layout sent | No 422 from the venue service | UI |
| AC1-N1 | AC1 | A non-positive or non-integer capacity is reported, not sent | Negative | Search form open | Enter each invalid capacity and submit | "0", "abc", "2.5", "-1" | Error "Enter a whole number greater than zero."; no query built | No request reaches the venue service | UI |
| AC1-N2 | AC1 | A date that is not a real calendar day is dropped, not sent | Negative | Search form open | Enter 2026-02-30 with a location and submit | 2026-02-30 | Query is `location=East` only | No 422 from the venue service | UI |
| AC1-N3 | AC1, AC4 | Invalid search times, or times without a date, are refused with the reason | Negative | Any venue exists | Search with each bad time combination | off-step 610–720; outside 07:00–24:00 405–480; end = start; start without end; times without a date | 422 with `off_step`, `outside_operating_window`, `end_not_after_start`, `times_incomplete`, `date_required` respectively | No results returned | API |
| AC2-H1 | AC2, AC1 | Only venues matching every applied filter are returned | Happy | Three venues that each fail exactly one of the combined filters | Search with location, capacity, facility, layout and date-time together | capacity 200/250 vs required 200; theatre vs boardroom; one shared location; free 12:00–18:00 on D | Only the venue passing every filter returned | Failing venues absent; no venue below capacity | API |
| AC2-P1 | AC2 | With no filters every available venue is returned | Partition | Two available venues | Search with no parameters | none | 200, both venues | — | API |
| AC2-H2 | AC2 | Each result shows the attributes a coordinator shortlists by | Happy | One result from a search | Render the results list | Riverside Hall: East Wing, 120, Theatre, Projector, Ramp access | Card shows every key attribute and "1 venue matches every filter." | Attributes not shown as plain page text outside the card | UI |
| AC2-N1 | AC2 | An empty result for a valid query is stated plainly | Negative | Search returns nothing | Render an empty results list | none | "No venue matches every filter. Try removing one." | No error banner; no crash | UI |
| AC2-H3 | AC2, AC3, AC4 | In a browser the coordinator filters by capacity and facilities and only the matching venue shows | Happy | Three seeded venues (300 projector+stage theatre; 20 projector boardroom; 400 blocked) as coordinator | Submit 0 attendees, then 100 with location and facilities | Attendees 0 then 100; "Search Wing"; "projector, stage" | 0 → inline capacity error; 100 → only the big hall, "1 venue matches every filter."; small and blocked venues never listed | Blocked venue never rendered | E2E |
| AC2-X1 | AC2 | Only catalogue readers may search; other roles and anonymous callers are refused | Cross-cutting | Venue exists | Search as attendee; (Technical Support covered by SCRUM-13's AC1-X4; organisers redirected by SCRUM-27) | attendee principal | 403 for the attendee on `GET /venues/search` | No venue data leaked; catalogue unchanged | API |
| AC3-P1 | AC3, AC1 | Venues below the required capacity are excluded; venues above are kept | Partition | Small (50) and Big (300) venues | Search `required_capacity=100` | N = 100 | Only Big returned | Small never appears | API |
| AC3-B1 | AC3 | A venue at N−1 is excluded | Boundary | Venue with capacity 99 | Search `required_capacity=100` | N = 100, venue 99 | Venue absent from results | — | API |
| AC3-B2 | AC3 | A venue at exactly N is included | Boundary | Venue with capacity 100 | Search `required_capacity=100` | N = 100, venue 100 | Venue present in results | — | API |
| AC3-B3 | AC3 | A venue at N+1 is included | Boundary | Venue with capacity 101 | Search `required_capacity=100` | N = 100, venue 101 | Venue present in results | — | API |
| AC4-H1 | AC4 | A venue blocked by an update is excluded from results | Happy | Two available venues | `PATCH` one venue's status to blocked, then search | `{"status": "blocked"}` | Only the still-available venue returned | Blocked venue absent; the other venue unchanged | API |
| AC4-P1 | AC4 | A venue blocked at an overlapping time is hidden for that time and searchable outside it | Partition | Venue with a block 12:30–14:00 on D | Search D 13:00–15:00, then D 14:00–16:00 | block 750–840; searches 780–900 and 840–960 | Absent for the overlapping range, returned for the adjacent one | — | API |
| AC4-P2 | AC4 | A venue with an approved overlapping booking is hidden; a pending booking reserves nothing | Partition | Venue with an approved 10:00–12:00 booking and a pending 15:00–17:00 booking | Search 11:00–13:00, 12:00–14:00 and 15:00–16:00 on D | approved 600–720; pending 900–1020 | Absent only for the overlap with the approved booking | Pending booking does not exclude the venue | API |
| AC4-B1 | AC4 | A date-only search excludes a venue with no free minute and keeps one with 15 free | Boundary | One venue covered 07:00–24:00 by block+booking; one blocked 07:00–23:45 | Search with `date` only | blocks 420–780 / 420–1425; booking 780–1440 | Fully covered venue absent; 15-minute venue present | — | API |

| AC2-H4 | AC2 | The API result carries the six shortlist attributes | Happy | One venue with every attribute | `GET /venues/search` | Orchard Hall, Orchard Road, 180, projector and stage, ramp, theatre and boardroom | name, location, `max_capacity`, `supported_layouts`, `facilities`, `accessibility_features` equal what was stored | — | API (`test_venues_search_contract.py`) |
| AC3-P2 | AC3 | A chosen layout's own capacity decides, not the maximum (Q&A #112) | Partition | Max 300, classroom 80 | `required_capacity=100&layout=classroom` | 100, classroom | Venue absent | — | API (same file) |
| AC3-P3 | AC3 | A layout with no recorded capacity uses the maximum | Partition | Same venue | `required_capacity=100&layout=theatre` | 100, theatre | Venue present | — | API (same file) |
| AC3-P4 | AC3 | With no layout chosen the maximum applies | Partition | Same venue | `required_capacity=250` | 250 | Venue present | — | API (same file) |
| AC3-N1 | AC3 | A small venue is hidden even when everything else matches | Negative | 40-seat venue matching location, facility and layout | Search for 41 with those filters | 41 | No result | — | API (same file) |
| AC2-X2, AC2-X3, AC2-X4 | AC2 | Event Coordinator, Venue Staff and Safety Officer can search | Cross-cutting | One venue; each role in turn | `GET /venues/search` | roles | 200 and the venue | — | API (same file) |
| AC2-X5, AC2-X6, AC2-X7, AC2-X8, AC2-X9 | AC2 | Event Organiser, Attendee, Technical Support, Event Coordinator Lead and Admin are refused | Cross-cutting | One venue; each role in turn | `GET /venues/search` | roles | 403; no venue data in the body | Nothing returned | API (same file) |
| AC2-X10 | AC2 | One permitted role among several is enough | Cross-cutting | Roles `attendee` and `event_coordinator` | `GET /venues/search` | — | 200 | — | API (same file) |
| AC2-X11 | AC2 | A search with no session is refused | Cross-cutting | No session | `GET /venues/search` | — | 401 | — | API (same file) |
| AC2-X12 | AC2 | A Safety Officer can open the venue search page (the issue tracker AC lets them search) | Cross-cutting | Safety Officer session | Open `/venues/search` | — | The page opens | — | E2E (not automated) |

AC2-X12 **does not hold today** and has no test, because it would fail: `frontend/app/venues/search/page.tsx` line 18 admits only `event_coordinator` and `venue_staff`, and the navigation offers a Safety Officer no search link (the service does accept them). Decision for the Product Owner: admit the Safety Officer on the page, or reword the AC.

## Latest execution record

This pass (test-case gap sweep, 1 Nov 2026, branch `docs/testcase-gap-sweep`, uncommitted working tree) added the `SCRUM-9 …` label comments and designed this matrix; **no suite was run**, so no row carries pass/fail evidence. Label-only edits were lint-checked (`ruff`, eslint) but that is not test evidence. Existing rows for the same behaviour in `docs/testcases/scrum_65_testcases.md` keep their own execution records there.

| ID | Automation status | Actual result | Execution status | Build or commit | Executed by and date | Remarks and evidence |
| --- | --- | --- | --- | --- | --- | --- |
| AC1-H1, AC1-P1, AC1-P7, AC1-N1, AC1-N2, AC2-H2, AC2-N1 | Automated (label added in this pass) | — | Not executed | Working tree of `docs/testcase-gap-sweep` | Test-case gap sweep (Claude), 1 Nov 2026 | `frontend/__tests__/venue-search.test.tsx` (`builds a query from every filter`, `returns no query when nothing is filled in`, `drops unknown slot and layout values`, `rejects capacity %j`, `drops a date that is not a real calendar date`, `shows key attributes for each result`, `explains when no venue matches`) |
| AC1-P2, AC1-P3, AC1-P4, AC1-P5, AC1-P6, AC2-H1, AC2-P1, AC3-P1, AC4-H1 | Automated (label added in this pass) | — | Not executed | Working tree of `docs/testcase-gap-sweep` | Test-case gap sweep (Claude), 1 Nov 2026 | `backend/venueService/tests/test_venues_search.py` (one test per row; names match the scenarios) |
| AC1-N3, AC4-P1, AC4-P2, AC4-B1 | Automated (SCRUM-65 label; cross-referenced, not relabelled) | — | Not executed | Working tree of `docs/testcase-gap-sweep` | Test-case gap sweep (Claude), 1 Nov 2026 | `backend/venueService/tests/test_block_search_times.py`: SCRUM-65's AC4-N1 (`test_invalid_search_times_are_refused`), AC3-H2 (`test_blocked_time_is_not_offered_in_search`), AC4-H1 (`test_search_respects_booked_times`), AC4-B1 (`test_search_by_date_needs_free_time`) prove these rows; their IDs stay with SCRUM-65's matrix |
| AC2-X1 | Automated (shares the test labelled SCRUM-30 AC2-N3; not relabelled) | — | Not executed | Working tree of `docs/testcase-gap-sweep` | Test-case gap sweep (Claude), 1 Nov 2026 | `backend/venueService/tests/test_venues_catalogue.py::test_venue_reads_forbidden_for_attendees` includes `GET /venues/search` → 403 for an attendee; Technical Support's 403 on search sits in `test_venue_locations.py` (SCRUM-13's AC1-X4) |
| AC2-H3 | Automated (label added in this pass) | — | Not executed | Working tree of `docs/testcase-gap-sweep` | Test-case gap sweep (Claude), 1 Nov 2026 | `frontend/e2e/venue-search.spec.ts` (`coordinator filters venues by capacity and facilities`) |
| AC3-B1, AC3-B2, AC3-B3 | Automated (new, PR #125) | — | See the execution evidence below | — | — | `backend/venueService/tests/test_venues_search_contract.py::test_capacity_boundary_is_the_maximum_capacity` (venue of 99, 100 and 101 against a required 100) |
| AC2-H4, AC3-P2, AC3-P3, AC3-P4, AC3-N1, AC2-X2 to AC2-X11 | Automated (new, PR #125) | — | See the execution evidence below | — | — | `backend/venueService/tests/test_venues_search_contract.py` |
| AC2-X12 | Not automated | The page admits only Event Coordinator and Venue Staff | **Fail (found by reading `app/venues/search/page.tsx:18`; not run)** | — | Claude Code, 1 Nov 2026 | Needs a decision; see above |

## Execution evidence, 1 November 2026 (PR #125)

The suites below were run after the new tests were added and after `dev` (`439fec0`) was merged into the PR #125 branch. They are the first run of this story's tests in this document. Every automated row above passed because the test it names is in a suite that passed; no row was run on its own. Environment: Kennedy's machine, Claude Code, pending human review; backend tests use in-memory stores and fakes; the browser tests use the Node mock services and the cached Chromium 1148 headless shell (the pinned build is not installed).

| Check | Command and environment | Result |
| --- | --- | --- |
| venueService | `pytest`; `ruff check .` | 790 passed, 10 skipped; clean |
| authService | `pytest`; `ruff check .` | 60 passed; clean |
| eventRequestService | `pytest`; `ruff check .` | 1194 passed, 1 skipped; clean |
| equipmentService | `pytest`; `ruff check .` | 354 passed; clean |
| Frontend | `npx vitest run`; `npm run typecheck`; `npm run lint` | 80 files, 762 passed; clean; clean |
| End-to-end | `playwright test` (whole suite) | 59 passed |

Not run: the shared development database, pull-request CI at the time of writing, and reviewer sign-off. The new tests passed first time, so they found no defect; they close gaps in the record.
