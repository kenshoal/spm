# SCRUM-30 — Maintain the Venue Catalogue

Source: [Jira SCRUM-30](https://is212g9t4.atlassian.net/browse/SCRUM-30) (Venue Staff maintains the catalogue). The three ACs below were pulled from Jira on 1 November 2026 and are recorded as approved; this document and its labels were drafted by the test-case gap sweep on the same day.

Status: **AI-drafted test design, not yet reviewed by a teammate (`testing.md` §10). Jira remains the source of truth.** The automated tests predate this document: this pass added label comments to them and designed the matrix, and ran no suite — every row below is **Not executed** and no pass/fail is claimed (`testing.md` §8).

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

## Latest execution record

This pass (test-case gap sweep, 1 Nov 2026, branch `docs/testcase-gap-sweep`, uncommitted working tree) added the `SCRUM-30 …` label comments and designed this matrix; **no suite was run**, so no row carries pass/fail evidence. Label-only edits were lint-checked (`ruff`, eslint) but that is not test evidence. SCRUM-59's existing labels on the setup/turnaround tests in the same files were left untouched.

| ID | Automation status | Actual result | Execution status | Build or commit | Executed by and date | Remarks and evidence |
| --- | --- | --- | --- | --- | --- | --- |
| AC1-H1, AC1-H2, AC1-P1, AC1-N1, AC1-N2, AC1-N3, AC2-H1, AC2-P1, AC2-N1, AC2-N2, AC2-N3 | Automated (label added in this pass) | — | Not executed | Working tree of `docs/testcase-gap-sweep` | Test-case gap sweep (Claude), 1 Nov 2026 | `backend/venueService/tests/test_venues_catalogue.py` (one test per row; names match the scenarios) |
| AC1-H3, AC2-H2, AC1-N6 | Automated (label added in this pass) | — | Not executed | Working tree of `docs/testcase-gap-sweep` | Test-case gap sweep (Claude), 1 Nov 2026 | `frontend/__tests__/venues.test.tsx` |
| AC1-H4, AC1-P2, AC1-P3, AC1-P4, AC1-P5, AC1-N4, AC1-N5, AC1-N7 | Automated (label added in this pass) | — | Not executed | Working tree of `docs/testcase-gap-sweep` | Test-case gap sweep (Claude), 1 Nov 2026 | `frontend/__tests__/venue-form.test.ts` |
| AC1-H5 | Automated (label added in this pass) | — | Not executed | Working tree of `docs/testcase-gap-sweep` | Test-case gap sweep (Claude), 1 Nov 2026 | `frontend/e2e/venue-catalogue.spec.ts` (`venue staff add and update a venue`) |
| AC1-H1, AC1-N1, AC1-N3, AC1-N5 (action layer) | Automated (label added in this pass) | — | Not executed | Working tree of `docs/testcase-gap-sweep` | Test-case gap sweep (Claude), 1 Nov 2026 | `frontend/__tests__/venue-actions.test.ts`: the same four rows proved through the `createVenue` / `updateVenue` server actions (`creates a venue and redirects…`, `a 403 explains…`, `a 404 on update explains…`, `an invalid form never calls fetch…`). Three further tests in that file — the backend-422 wording, the expired-session redirect to `/auth`, and the unreachable-service retry message — match no matrix row and were left unlabelled rather than given new IDs |
| AC3-X1 | Planned | — | Not executed | — | — | gap: no automated test yet — story owner to write; nearest existing evidence is the status-only update→search case labelled SCRUM-9 AC4-H1 (`test_venues_search.py::test_blocked_venue_is_excluded`), and SCRUM-12's AC5-X1 proves a check never writes — neither edits attributes and re-runs both checks |
