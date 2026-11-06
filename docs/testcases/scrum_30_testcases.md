# SCRUM-30 — Maintain the Venue Catalogue

Source: [Jira SCRUM-30](https://is212g9t4.atlassian.net/browse/SCRUM-30) (Venue Staff maintains the catalogue). The three ACs below were pulled from Jira on 1 November 2026 and are recorded as approved; this document and its labels were drafted by the test-case gap sweep on the same day.

Status: **AI-drafted test design, not yet reviewed by a teammate (`testing.md` §10). Jira remains the source of truth.** The automated tests predate this document: this pass added label comments to them and designed the matrix, and ran no suite — every row below is **Not executed** and no pass/fail is claimed (`testing.md` §8).

> **Update from PR #125 (1 Nov 2026).** (1) **Jira's ACs changed after this document was drafted, and the new AC1 does not match the system.** At 16:07 the SCRUM-30 ACs were rewritten as AC1 to AC7 (Jira shows the time; the editor was not checked). AC1 now says a venue has "one daily operating start and end … on 15-minute steps within 07:00 to 24:00", and AC4 and AC5 say search and suitability use the venue's operating hours. The system does not do this: the form has no such field, and the stored `operating_slots` (AM, PM, NIGHT) are read by nothing since SCRUM-65 (assumption A1). This is a requirement-to-code mismatch, not a test gap: either per-venue operating times are built, or the AC is amended. It needs the Product Owner's decision. (2) The other new ACs map to this matrix as: AC2 = AC1 (update), AC3 = AC2, AC4 and AC5 = AC3, AC6 = AC1-N rows, AC7 = AC1-N1 and the new AC1-X rows. Re-base the IDs when the story owner reviews. (3) Cases added by PR #125 are in `backend/venueService/tests/test_venues_catalogue_contract.py`; the planned AC3-X1 case is now covered by AC3-X2 to AC3-X5.

## Story contract

**User story:** As Venue Staff, I want to create and update venue records in the catalogue, so that Coordinators search and check suitability against accurate venue information.

### Acceptance criteria (approved, Jira 1 Nov 2026)

| ID | Criterion |
| --- | --- |
| AC1 | Venue Staff can create and update a venue record with location, maximum capacity, facilities, accessibility, supported room layouts, and operating hours. |
| AC2 | Given a venue record, when viewed by an authorised user, then its current attributes are shown. |
| AC3 | Updates to a venue's attributes are reflected in venue search and suitability checks. |

### Included and excluded behaviour

| | Behaviour | Story / file |
| --- | --- | --- |
| Included | `POST /venues`, `PATCH /venues/{id}`, `GET /venues/{id}`, `GET /venues` and their role rules | SCRUM-30 |
| Included | The venue form: attribute capture, prefill on edit, invalid-value echo, status handling | SCRUM-30 frontend |
| Included | AC3's propagation of an attribute update into venue search and suitability (one cross-cutting case) | SCRUM-30 |
| Excluded | Setup/turnaround minutes and the booking-impact notices a timing change sends | SCRUM-20, SCRUM-59 (their labels already sit on those tests) |
| Excluded | How search and suitability use the attributes (the checking side) beyond AC3's one case | SCRUM-9, SCRUM-12 |
| Excluded | The `/venues/locations` contract | SCRUM-13 (its labels already sit on `test_venue_locations.py`) |
| Excluded | Per-venue operating hours as an editable attribute | Retired by SCRUM-65 (assumption A1) |

### Actors and permissions

- **Venue Staff** (`venue_staff`) — creates and updates venue records (`require_venue_staff`); any other role is refused 403 (proven for `event_operations_manager`).
- **Authorised readers** (AC2) — `event_coordinator`, `venue_staff`, `safety_officer` (`require_venue_viewer`); an attendee is refused 403, Technical Support is refused 403 on the catalogue (SCRUM-13's AC1-X4 proves it).
- No session — 401 on every venue route.

### Assumptions and open questions

| ID | Assumption or question | Used by |
| --- | --- | --- |
| A1 | AC1's "operating hours": since SCRUM-65 every venue runs 07:00–24:00 in 15-minute steps and the forms neither ask for nor send operating slots (`venue-form.test.ts` asserts `operating_slots` is absent from the payload). The API model still stores a legacy `operating_slots` default (AM/PM/NIGHT) that nothing reads. Requirement-vs-code point for the card owner: confirm the AC is read as "the fixed 07:00–24:00 window", not per-venue hours. | AC1-H3, AC1-H4, AC1-P3 |
| A2 | Status (`available` / `blocked`) is part of the **update** payload only; the create form offers no status field and new venues start `available`. | AC1-P1, AC1-P4, AC1-P5 |
| A3 | `max_capacity` must be a whole number above zero (API 422 via `Field(gt=0)`; form message "Enter a whole number greater than zero."). | AC1-N2, AC1-N4 |
| A4 | Updates are partial: unset fields stay unchanged and `updated_at` moves forward; the response is the full stored record. | AC1-H2, AC2-H1 |
| A5 | AC3 has **no automated test** that edits an attribute and re-runs search and suitability. The only update→search coverage today is the status flip in SCRUM-9's AC4-H1 (`test_blocked_venue_is_excluded`). AC3-X1 is this story's known coverage gap. | AC3-X1 |

## Test data used below

Invented examples to seed local runs (each automated test seeds its own equivalents, named in the remarks column):

| Venue | Location | Capacity | Facilities | Accessibility | Layouts | Status |
| --- | --- | --- | --- | --- | --- | --- |
| Orchard Hall | Orchard Road | 200 | projector, microphone | wheelchair_ramp | theatre, classroom | available |
| Riverside Hall (frontend example) | Level 2, East Wing | 120 | Projector, WiFi | Ramp access | theatre | available |

Update example for AC3-X1: `PATCH {"max_capacity": 350, "facilities": ["projector", "stage"]}` on Orchard Hall.

## Test case specification

Layer codes: **API** = `backend/venueService/tests/test_venues_catalogue.py` (FastAPI route tests, in-memory store); **UI** = `frontend/__tests__/venues.test.tsx` and `frontend/__tests__/venue-form.test.ts` (Vitest); **E2E** = `frontend/e2e/venue-catalogue.spec.ts` (Playwright).

| ID | AC | Test scenario | Technique | Pre-conditions | Test steps | Test data | Expected result | Forbidden side effects | Layer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AC1-H1 | AC1 | Creating a venue stores it and returns the record | Happy | Authenticated Venue Staff | `POST /venues` with every attribute | Orchard Hall payload | 201; body carries an `id`, the attributes, `status` "available", `created_at`, `updated_at` | No duplicate record; status is never set by creation | API |
| AC1-H2 | AC1 | A partial update changes only the sent fields | Happy | Orchard Hall exists | `PATCH` capacity and facilities only | `{"max_capacity": 350, "facilities": ["projector", "stage"]}` | 200; new values stored; name untouched; `updated_at` >= before | Other attributes unchanged | API |
| AC1-H3 | AC1 | The create form offers every catalogue attribute and no status field | Happy | Venue Staff on the create form | Render `VenueForm` with no venue | none | Name, Location, Maximum capacity, Facilities, Accessibility fields, layout checkboxes; the fixed-window note; no Availability control; "Add venue" button | No status input on create | UI |
| AC1-H4 | AC1 | Every catalogue attribute is captured from the form into the payload | Happy | Valid form data | Submit the form data through `parseVenueForm` | Riverside Hall fields | Payload carries name, location, `max_capacity` 120 (number), facility and accessibility lists, both layouts, times 0; no errors | Operating slots never sent | UI |
| AC1-H5 | AC1, AC2 | In a browser Venue Staff add a venue, see its attributes, then update it | Happy | Signed in as Venue Staff | Add with capacity 0, correct it, save, edit capacity and status | Orchard Studio; 0 → 45 → 60; blocked | Capacity-0 error shown; card shows "up to 45 people" and Boardroom; after the edit "up to 60 people" and "Blocked" | No venue created by the refused submission | E2E |
| AC1-P1 | AC1 | The status can be updated to blocked | Partition | Available venue | `PATCH {"status": "blocked"}` | blocked | 200; stored status is `blocked` | Other attributes unchanged | API |
| AC1-P2 | AC1 | Comma lists are trimmed, blank-free and de-duplicated | Partition | Form parsing | `splitList` on messy input | "Projector, , projector ,WiFi"; "   " | `["Projector", "WiFi"]`; empty string → `[]` | No blank or duplicate entries stored | UI |
| AC1-P3 | AC1 | Values outside the backend enums are dropped, not sent | Partition | Form data with unknown values | Parse with `includeStatus: true` | layout "ballroom", slots AM/MIDNIGHT, status "gone" | Only `["theatre"]` kept; `operating_slots` absent; status falls back to "available" | No 422 from the venue service | UI |
| AC1-P4 | AC1 | The status field is sent only when editing | Partition | Same form data, both modes | Parse with `includeStatus` true and false | status "blocked" | With editing: "blocked"; creating: no `status` key | Creation never sets a status | UI |
| AC1-P5 | AC1 | No status is echoed when the create form omits the field | Partition | Form data without status | `readVenueFormValues` | valid fields, no status | No `status` key; with a status present it is echoed | Create flow never invents a status | UI |
| AC1-N1 | AC1 | A non-Venue-Staff role is refused venue creation | Negative | Principal with `event_operations_manager` only | `POST /venues` | Orchard Hall payload | 403 | No venue created | API |
| AC1-N2 | AC1 | A non-positive capacity is refused at creation | Negative | Venue Staff session | `POST /venues` with capacity 0 | `max_capacity: 0` | 422 | No venue created | API |
| AC1-N3 | AC1 | Updating an unknown venue returns 404 | Negative | No venue with that id | `PATCH /venues/does-not-exist` | `{"max_capacity": 10}` | 404 | No record created | API |
| AC1-N4 | AC1 | A non-positive or non-integer capacity is reported, not sent | Negative | Valid form data otherwise | Parse with each bad capacity | "abc", "0", "-3", "12.5", "" | Error "Enter a whole number greater than zero." on `max_capacity` | No submit payload with a bad capacity | UI |
| AC1-N5 | AC1 | Missing name and location are reported instead of sent | Negative | Form with only capacity | Parse the incomplete form | `max_capacity: 10` only | Errors "Enter the venue name." and "Enter the venue location." | No payload submitted | UI |
| AC1-N6 | AC1 | An invalid capacity echoed after a failed edit overrides the stored value | Negative | Edit form for an existing venue; `updateVenue` resolves with a capacity error | Click "Save changes"; observe the re-render | echoed `max_capacity` "-3" against stored 120 | Field shows "-3", not the stored 120, with the error message | Stored value never silently replaces the typed text | UI |
| AC1-N7 | AC1 | An invalid capacity is echoed verbatim so a correction never loses it | Negative | Form data with an invalid capacity | `readVenueFormValues` | `max_capacity: "abc"` | Echoed as "abc"; lists echoed raw | No null or fallback value echoed | UI |
| AC2-H1 | AC2 | Viewing a venue shows its stored attributes | Happy | Orchard Hall created | `GET /venues/{id}` | created id | 200; body equals the created record attribute for attribute | Record unchanged by the read | API |
| AC2-H2 | AC2 | The edit form starts from the venue's current attributes | Happy | Riverside Hall exists | Render `VenueForm` with the venue | stored attributes | Fields prefilled (name, comma-joined facilities, checked Theatre, unchecked Classroom, status available); "Save changes" button | No attribute invented or defaulted visibly | UI |
| AC2-P1 | AC2 | The catalogue lists every venue | Partition | Two venues created | `GET /venues` | venues A and B | 200; both names present | — | API |
| AC2-N1 | AC2 | An unknown venue id returns 404 | Negative | No venue with that id | `GET /venues/does-not-exist` | — | 404 | — | API |
| AC2-N2 | AC2 | Reading the catalogue without a session is refused | Negative | No auth override | `GET /venues` with no bearer token | — | 401 | No venue data returned | API |
| AC2-N3 | AC2 | An attendee is refused catalogue reads | Negative | Attendee principal | `GET /venues`, `GET /venues/search`, `GET /venues/{id}`, `POST …/suitability` | attendee principal | 403 on all four | No venue data returned | API |
| AC3-X1 | AC3 | An attribute update is reflected in venue search and suitability | Cross-cutting | Orchard Hall: capacity 200, facilities projector only | `PATCH` capacity 350 and facilities + stage; re-run search at required capacity 300; re-run suitability at attendance 300 requiring stage | update `{"max_capacity": 350, "facilities": ["projector", "stage"]}`; search `required_capacity=300`; suitability attendance 300 + stage | Search now returns Orchard Hall (it could not before the edit); suitability now reports `suitable: true` with no mismatches (it reported a capacity mismatch before) | No duplicate record; the edit does not create or cancel bookings; unrelated venues unchanged | API |

| AC1-H6 | AC1 | Every catalogue attribute is stored on create and read back | Happy | Venue Staff session | `POST /venues`; `GET /venues/{id}` | Orchard Hall, Orchard Road, 200, projector and microphone, wheelchair_ramp and hearing_loop, theatre and classroom, AM and PM | 201; every field equals what was sent, on create and on re-read | — | API (`test_venues_catalogue_contract.py`) |
| AC1-H7 | AC1 | Every attribute can be updated at once | Happy | Venue as above | `PATCH` all seven fields | Orchard Grand Hall, Marina Bay, 450, stage, lift, banquet, NIGHT | 200; every field changed | — | API (same file) |
| AC1-P6 | AC1 | Facilities, accessibility and layouts may be empty | Partition | Venue Staff session | `POST` with only name, location, capacity | Bare, Anywhere, 10 | 201; the three lists are empty | — | API (same file) |
| AC1-B1, AC1-B2 | AC1 | A maximum capacity of 1 is accepted and 0 is refused | Boundary | Venue Staff session | `POST` capacity 1, then 0 | 1; 0 | 201; 422 with no venue stored | — | API (same file) |
| AC1-N8, AC1-N9, AC1-N10, AC1-N11 | AC1 | A negative capacity, a non-numeric capacity, a blank location and an unknown layout are each refused | Negative | Venue Staff session | `POST` each | -5; "many"; ""; "spaceship" | 422; no venue stored | Nothing stored | API (same file) |
| AC1-N12 | AC1 | A refused update leaves the venue as it was | Negative | Venue exists | `PATCH` capacity 0 | 0 | 422; the venue read back is identical | Nothing changed | API (same file) |
| AC1-X1, AC1-X2, AC1-X3, AC1-X4, AC1-X5 | AC1 | Event Coordinator, Safety Officer, Event Organiser, Technical Support and Attendee cannot create or update | Cross-cutting | Venue exists; each role in turn | `POST /venues` and `PATCH /venues/{id}` | roles | 403 and 403 | Venue unchanged | API (same file) |
| AC2-H3, AC2-H4, AC2-H5 | AC2 | Event Coordinator, Venue Staff and Safety Officer read the current attributes | Happy | Venue updated to 260 seats; each role in turn | `GET /venues/{id}` | roles | 200; 260 and the facilities | — | API (same file) |
| AC2-N4, AC2-N5, AC2-N6 | AC2 | Event Organiser, Technical Support and Event Coordinator Lead cannot read a venue | Negative | Venue exists; each role in turn | `GET /venues/{id}` and `GET /venues` | roles | 403 and 403 | — | API (same file) |
| AC3-X5 | AC3 | An updated capacity changes who search finds | Cross-cutting | Venue of 50 | Search for 120 → none; `PATCH` to 150; search again | 120 | Not found, then found | — | API (same file) |
| AC3-X2 | AC3 | Updated facilities, accessibility and layouts change what search finds | Cross-cutting | Venue with none | Search for stage, lift, banquet → none; `PATCH`; search again | stage, lift, banquet | Not found, then found | — | API (same file) |
| AC3-X3 | AC3 | Taking a venue out of service removes it from search | Cross-cutting | Available venue | Search; `PATCH` blocked; search | — | Found, then not | — | API (same file) |
| AC3-X4 | AC3 | An updated capacity and facilities change a suitability verdict | Cross-cutting | Venue of 40 seats, no facilities | Check 80 people and a stage → unsuitable with two mismatches; `PATCH` to 90 and a stage; check again | 80, stage | Unsuitable (capacity, facilities), then suitable with none | — | API (same file) |

## Latest execution record

This pass (test-case gap sweep, 1 Nov 2026, branch `docs/testcase-gap-sweep`, uncommitted working tree) added the `SCRUM-30 …` label comments and designed this matrix; **no suite was run**, so no row carries pass/fail evidence. Label-only edits were lint-checked (`ruff`, eslint) but that is not test evidence. SCRUM-59's existing labels on the setup/turnaround tests in the same files were left untouched.

| ID | Automation status | Actual result | Execution status | Build or commit | Executed by and date | Remarks and evidence |
| --- | --- | --- | --- | --- | --- | --- |
| AC1-H1, AC1-H2, AC1-P1, AC1-N1, AC1-N2, AC1-N3, AC2-H1, AC2-P1, AC2-N1, AC2-N2, AC2-N3 | Automated (label added in this pass) | — | Not executed | Working tree of `docs/testcase-gap-sweep` | Test-case gap sweep (Claude), 1 Nov 2026 | `backend/venueService/tests/test_venues_catalogue.py` (one test per row; names match the scenarios) |
| AC1-H3, AC2-H2, AC1-N6 | Automated (label added in this pass) | — | Not executed | Working tree of `docs/testcase-gap-sweep` | Test-case gap sweep (Claude), 1 Nov 2026 | `frontend/__tests__/venues.test.tsx` |
| AC1-H4, AC1-P2, AC1-P3, AC1-P4, AC1-P5, AC1-N4, AC1-N5, AC1-N7 | Automated (label added in this pass) | — | Not executed | Working tree of `docs/testcase-gap-sweep` | Test-case gap sweep (Claude), 1 Nov 2026 | `frontend/__tests__/venue-form.test.ts` |
| AC1-H5 | Automated (label added in this pass) | — | Not executed | Working tree of `docs/testcase-gap-sweep` | Test-case gap sweep (Claude), 1 Nov 2026 | `frontend/e2e/venue-catalogue.spec.ts` (`venue staff add and update a venue`) |
| AC1-H1, AC1-N1, AC1-N3, AC1-N5 (action layer) | Automated (label added in this pass) | — | Not executed | Working tree of `docs/testcase-gap-sweep` | Test-case gap sweep (Claude), 1 Nov 2026 | `frontend/__tests__/venue-actions.test.ts`: the same four rows proved through the `createVenue` / `updateVenue` server actions (`creates a venue and redirects…`, `a 403 explains…`, `a 404 on update explains…`, `an invalid form never calls fetch…`). Three further tests in that file — the backend-422 wording, the expired-session redirect to `/auth`, and the unreachable-service retry message — match no matrix row and were left unlabelled rather than given new IDs |
| AC3-X1 (umbrella), AC1-H6, AC1-H7, AC1-P6, AC1-B1, AC1-B2, AC1-N8 to AC1-N12, AC1-X1 to AC1-X5, AC2-H3 to AC2-H5, AC2-N4 to AC2-N6, AC3-X2 to AC3-X5 | Automated (new, PR #125) | — | See the execution evidence below | — | — | `backend/venueService/tests/test_venues_catalogue_contract.py` (25 tests) |

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

## Hotfix 2 H12 (operating hours) and review item E1, 3 November 2026

These cases come from `release_1_hotfixes_testcases.md`: H12 gave each venue its own daily operating hours (migration 0092, PR #130), and E1 made holds and approvals outside those hours refuse instead of raising (PR #132). Their AC numbers are Jira's rewritten AC1 to AC7 of 1 November, not the three ACs in the contract above. The hotfix numbering reuses IDs this document already holds, so each ID carries its item as a prefix (`H12`, `E1`), as in the tracking sheet; the frontend labels read `SCRUM-30 H12 AC…`.

Layer codes: **API** = `backend/venueService/tests/test_venue_operating_hours.py` (FastAPI routes, in-memory stores); **R** = the Supabase store test in the same file (`httpx.MockTransport`); **DB** = the 0092 block of `database/verify_release_1_hotfixes_2.sql`; **UI** = `frontend/__tests__/venue-form.test.ts`, `venues.test.tsx`, `venue-search.test.tsx` and `venue-suitability.test.tsx`; **E2E** = `frontend/e2e/venue-catalogue.spec.ts` (`venue staff set a venue's operating hours`). The calendar cases of H12 are in `scrum_31_testcases.md`.

| ID | AC | Test scenario | Technique | Pre-conditions | Test steps | Test data | Expected result | Forbidden side effects | Layer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| H12 AC1-H1 | AC1 | A venue is created with its daily operating start and end, and the database accepts a valid range | Happy | Venue Staff session | `POST /venues` with hours; `GET` it back. DB: update the hours of a verification venue | 540 to 1080 | 201; the hours are stored and read back. DB: the range is accepted | — | API, DB |
| H12 AC1-P1 | AC1 | A venue created without hours operates 07:00 to 24:00 | Partition | Venue Staff session | `POST /venues` without hours. DB: insert without the columns | no hours | Hours are 420 and 1440 | — | API, DB |
| H12 AC1-B1 | AC1 | The first quarter hour of the day is a valid range on its own | Boundary | Venue Staff session | `POST /venues`. DB: update | 420 to 435 | 201. DB: accepted | — | API, DB |
| H12 AC1-B2 | AC1 | The last quarter hour of the day is a valid range on its own | Boundary | Venue Staff session | `POST /venues`. DB: update | 1425 to 1440 | 201. DB: accepted | — | API, DB |
| H12 AC1-B3 | AC1 | The whole day is a valid range | Boundary | Venue Staff session | `POST /venues` | 420 to 1440 | 201 | — | API |
| H12 AC1-B4 | AC1 | The venue form accepts the first quarter hour of the day on its own | Boundary | Valid venue form | `parseVenueForm` | 420 to 435 | No error | — | UI |
| H12 AC1-B5 | AC1 | The venue form accepts the last quarter hour of the day on its own | Boundary | Valid venue form | `parseVenueForm` | 1425 to 1440 | No error | — | UI |
| H12 AC1-H6 | AC1 | The venue form sends the opening and closing times as minutes after midnight | Happy | Valid venue form with hours | `parseVenueForm` | opening and closing times | Payload carries `operating_start_minute` and `operating_end_minute` as numbers | — | UI |
| H12 AC1-P6 | AC1 | Blank hours on the venue form mean the whole day | Partition | Valid venue form, hours blank | `parseVenueForm` | blank | Payload carries 420 and 1440 | — | UI |
| H12 AC1-H7 | AC1 | The new venue form offers an opening and a closing time on 15-minute steps, starting at the whole day | Happy | None | Render the new venue form | — | Both selects list 07:00 to 24:00 in 15-minute steps and start at 07:00 and 24:00 | — | UI |
| H12 AC1-H8 | AC1 | Venue Staff set a venue's operating hours in the browser | Happy | Venue Staff signed in; mock venue API | Open a venue, set the hours, save | opening and closing times | The saved hours show on the catalogue | — | E2E |
| H12 AC1-X1 | AC1 | The Supabase store sends the hours on create, and only the changed end on update | Cross-cutting | Supabase store over `httpx.MockTransport` | Create, then update the end only | 540 to 1080; end 1200 | Create body has both; update body has the end and no start | No other column written | R |
| H12 AC2-H1 | AC2 | An update can change either end, and an omitted end keeps its value | Happy | Venue open 09:00 to 18:00 (540 to 1080) | `PATCH` the start; then both | 600; 480 and 1200 | (600, 1080), then (480, 1200) | — | API |
| H12 AC2-P1 | AC2 | An update of other attributes leaves the hours alone | Partition | Venue open 09:00 to 18:00 (540 to 1080) | `PATCH` another attribute | capacity 120 | Hours stay 540 to 1080 | — | API |
| H12 AC2-H2 | AC2 | The edit venue form shows the venue's stored hours | Happy | Venue with its own hours | Render the edit form | stored hours | The selects start at the stored hours | — | UI |
| H12 AC6-N1 | AC6 | A range with an opening time before 07:00 is refused | Negative | Venue Staff session | `POST /venues`; DB: update; form: `parseVenueForm` | 405 to 1080 | API 422; DB check violation; form error | Nothing stored; stored hours unchanged; nothing sent | API, DB, UI |
| H12 AC6-N2 | AC6 | A range with a closing time after 24:00 is refused | Negative | Venue Staff session | `POST /venues`; DB: update; form: `parseVenueForm` | 540 to 1455 | API 422; DB check violation; form error | Nothing stored; stored hours unchanged; nothing sent | API, DB, UI |
| H12 AC6-N3 | AC6 | A range with an opening time off the 15-minute step is refused | Negative | Venue Staff session | `POST /venues`; DB: update; form: `parseVenueForm` | 545 to 1080 | API 422; DB check violation; form error | Nothing stored; stored hours unchanged; nothing sent | API, DB, UI |
| H12 AC6-N4 | AC6 | A range with a closing time off the 15-minute step is refused | Negative | Venue Staff session | `POST /venues`; DB: update; form: `parseVenueForm` | 540 to 1085 | API 422; DB check violation; form error | Nothing stored; stored hours unchanged; nothing sent | API, DB, UI |
| H12 AC6-N5 | AC6 | A range with an opening time equal to the closing time is refused | Negative | Venue Staff session | `POST /venues`; DB: update; form: `parseVenueForm` | 600 to 600 | API 422; DB check violation; form error | Nothing stored; stored hours unchanged; nothing sent | API, DB, UI |
| H12 AC6-N6 | AC6 | A range with an opening time after the closing time is refused | Negative | Venue Staff session | `POST /venues`; DB: update; form: `parseVenueForm` | 900 to 600 | API 422; DB check violation; form error | Nothing stored; stored hours unchanged; nothing sent | API, DB, UI |
| H12 AC6-N7 | AC6 | An update that moves the opening time past the closing time is refused / An inverted range is refused on insert / The form reports a non-numeric opening time | Negative | Venue open 09:00 to 18:00 (540 to 1080) | `PATCH`; DB: insert; form: `parseVenueForm` | start 1100; 1000 to 900; "abc" | API 422; DB check violation; form error | Stored hours unchanged; nothing sent | API, DB, UI |
| H12 AC6-N8 | AC6 | An update that moves the closing time before the opening time is refused / The form shows a refusal of the hours and keeps the chosen times | Negative | Venue open 09:00 to 18:00 (540 to 1080) | `PATCH`; render the form with a refusal | end 500 | API 422; the form shows the error and keeps the chosen times | Stored hours unchanged | API, UI |
| H12 AC6-N9 | AC6 | An update that makes the opening time equal the closing time is refused | Negative | Venue open 09:00 to 18:00 (540 to 1080) | `PATCH` | start 1080 | 422 | Stored hours unchanged | API |
| H12 AC6-N10 | AC6 | An update cannot clear an end with null | Negative | Venue open 09:00 to 18:00 (540 to 1080) | `PATCH` | end null | 422 | Stored hours unchanged | API |
| H12 AC6-X1 | AC6 | After a refusal the form echoes the hours exactly as typed | Cross-cutting | Form refused | `readVenueFormValues` | raw hours | Echoed values equal the input | — | UI |
| H12 AC6-E1 | AC6 | In the browser, an opening time after the closing time is refused with the chosen times kept, and the corrected hours save | Negative | Venue Staff signed in; mock venue API | Set an inverted range, save; correct it, save | opening after closing | Refusal shown; times kept; corrected hours on the catalogue | Inverted range never saved | E2E |
| H12 AC7-N1 | AC7 | Only Venue Staff change the hours | Negative | Venue open 09:00 to 18:00 (540 to 1080); Coordinator session | `PATCH` the hours | start 600 | 403 | Stored hours unchanged | API |
| H12 AC4-H1 | AC4 | Search offers a venue only for a time wholly inside its hours | Happy | Venue open 09:00 to 18:00 (540 to 1080) | Search the day and time | 09:00 to 10:00 | Offered | — | API |
| H12 AC4-B1 | AC4 | Search offers a venue only for a time wholly inside its hours | Boundary | Venue open 09:00 to 18:00 (540 to 1080) | Search the day and time | 17:00 to 18:00 | Offered | — | API |
| H12 AC4-B2 | AC4 | Search offers a venue only for a time wholly inside its hours | Boundary | Venue open 09:00 to 18:00 (540 to 1080) | Search the day and time | 08:45 to 09:45 | Not offered | — | API |
| H12 AC4-B3 | AC4 | Search offers a venue only for a time wholly inside its hours | Boundary | Venue open 09:00 to 18:00 (540 to 1080) | Search the day and time | 17:30 to 18:15 | Not offered | — | API |
| H12 AC4-B4 | AC4 | Search offers a venue only for a time wholly inside its hours | Boundary | Venue open 09:00 to 18:00 (540 to 1080) | Search the day and time | 08:00 to 09:00 | Not offered | — | API |
| H12 AC4-B5 | AC4 | Search offers a venue only for a time wholly inside its hours | Boundary | Venue open 09:00 to 18:00 (540 to 1080) | Search the day and time | 18:00 to 19:00 | Not offered | — | API |
| H12 AC4-P1 | AC4 | A search by date alone needs free time inside the venue's hours | Partition | Venue open 09:00 to 10:00 only, with that hour booked on one day | Search by date only | that day; a free day | Not offered, then offered | — | API |
| H12 AC4-P2 | AC4 | For a venue open at the searched time, the other filters still apply | Partition | Venue open 09:00 to 18:00 (540 to 1080) | Search 10:00 to 11:00 with a capacity | 10; 1000 | Offered, then not | — | API |
| H12 AC4-N1 | AC4; SCRUM-66 AC1 | The availability check reports a time outside the hours, and a time inside is available | Negative | Venue open 09:00 to 18:00 (540 to 1080) | `POST /venues/{id}/availability` | outside; inside | `outside_operating_hours`; available with no reasons | — | API |
| H12 AC4-H3 | AC4 | Each search result shows the hours the venue is open | Happy | Search results shown | Render a result | venue hours | The card lists the opening and closing times | — | UI |
| H12 AC5-H1 | AC5; SCRUM-12 AC3 | A requested time inside the venue's hours is suitable | Happy | Venue open 09:00 to 18:00 (540 to 1080) | `POST /venues/{id}/suitability` with a time | inside | `suitable: true` | — | API |
| H12 AC5-N1 | AC5; SCRUM-12 AC3 | A requested time outside the venue's hours is unsuitable and says why | Negative | Venue open 09:00 to 18:00 (540 to 1080) | As above | outside | `suitable: false`; mismatch `operating_hours` naming 09:00 and 18:00 | — | API |
| H12 AC5-P1 | AC5; SCRUM-12 AC3 | With no time asked for, suitability does not judge the hours | Partition | Venue open 09:00 to 18:00 (540 to 1080) | As above without a time | — | `suitable: true` | — | API |
| H12 AC5-N2 | AC5; SCRUM-12 AC3 | The suitability panel names and explains an operating-hours mismatch | Negative | Suitability result with an `operating_hours` mismatch | Render the panel | mismatch | Shown as operating hours with the venue's times, not a bare code | — | UI |
| E1 AC4-N2 | AC4 | A hold outside the venue's hours is refused with its code instead of raising (in-memory store) | Negative | Venue open 09:00 to 18:00 (540 to 1080); Coordinator with an event | `POST /venues/{id}/holds` | outside the hours | 409, `refusal_codes: ["outside_operating_hours"]` | No hold stored | API |
| E1 AC4-B5 | AC4 | A hold from exactly opening to closing is placed | Boundary | Venue open 09:00 to 18:00 (540 to 1080); Coordinator with an event | `POST /venues/{id}/holds` | 540 to 1080 | 201 | — | API |
| E1 AC4-N3 | AC4 | Approving a request outside the venue's hours is refused with the code (in-memory store) | Negative | Venue open 09:00 to 18:00 (540 to 1080); pending request outside the hours | Venue Staff approve it | — | 409 with `outside_operating_hours`; one refusal recorded | Request stays Pending | API |
| E1 AC4-H3 | AC4 | Approving a request inside the venue's hours still works | Happy | Venue open 09:00 to 18:00 (540 to 1080); pending request inside the hours | Venue Staff approve it | — | 200; Approved | — | API |

### Execution record

| ID | Automation status | Actual result | Execution status | Build or commit | Executed by and date | Remarks and evidence |
| --- | --- | --- | --- | --- | --- | --- |
| Every H12 row | Automated, written test first | As expected | Pass | `2ebf67a` and PR #130, local | Kennedy (Claude), 3 Nov 2026 | Recorded in the hotfix 2 execution record: venueService 854 passed, 10 skipped; frontend 802 passed; Playwright 60 passed; `verify_release_1_hotfixes_2.sql` PASSED on PostgreSQL 16 through 0092 |
| E1 AC4-N2, E1 AC4-N3, E1 AC4-B5, E1 AC4-H3 | Automated; AC4-N2 and AC4-N3 Red then Green | Red: both failed on the pydantic validation error. Green: as expected | Pass | PR #132, local | Kennedy (Claude), 3 Nov 2026 | venueService 858 passed, 10 skipped. The Supabase store still holds and approves outside hours (see "What E1 leaves open" in the hotfix document) |
| API and R rows (re-run after relabelling) | Automated | As expected | Pass | `fdc989f` plus the label edits, working tree | Claude for Yang Xue, 5 Nov 2026 | `pytest tests/test_venue_operating_hours.py`: 38 passed; whole venueService suite 858 passed; `ruff check` clean. Python 3.13 on Linux. The frontend and SQL rows were not re-run: only their label comments changed |
