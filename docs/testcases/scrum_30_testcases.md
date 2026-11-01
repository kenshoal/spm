# SCRUM-30 — Maintain the Venue Catalogue

**Jira:** [SCRUM-30](https://is212g9t4.atlassian.net/browse/SCRUM-30)

**User story:** As a Venue Staff member, I want to maintain each venue's information in the catalogue, so that Event Coordinators can plan events against accurate venue details.

**How this document was made.** The story was built in Sprint 1 (done on 19 September 2026) and this record was written afterwards, on 1 November 2026. The acceptance criteria are the Jira text as it stands today (the story has no numbering; the three bullets are AC1 to AC3). The review below is a proposal that the story owner or Product Owner has not approved yet. Most of the automated tests existed before this document, so none of them was seen failing first (`testing.md` §5). The tests marked "new" were written for this document; they all passed on first run, so they found no defect and fill gaps in the record. One AC wording problem (operating hours) is recorded under *Open questions*. The Jira comment of 5 September 2026 (INVEST review) decided to keep create and update in one story, and this document follows it.

## Story contract review

The acceptance criteria were checked against Week 4 core feature 8 (*Venue Catalogue*), Week 7 Customer Changes #1 and #3, GitHub Discussions #112 (capacity varies by room layout), #131 (the 07:00–24:00 window and 15-minute bookings replace AM / PM / Night) and #134 (no fixed list of facilities or accessibility features), and against the venueService code and `0016_venues.sql`.

| Original criterion | Outcome | Reason |
| --- | --- | --- |
| AC1. Venue Staff can create and update a venue record with location, maximum capacity, facilities, accessibility, supported room layouts, and operating hours. | Clarify | Two points. (1) "Operating hours": after #131 every venue runs the same 07:00–24:00 window, so the form no longer asks for operating slots and nothing reads a venue's own. The AC should say so, or the Product Owner should say per-venue hours are wanted. (2) The record also has a name, a setup and a turnaround time (SCRUM-59), layout capacities (#112) and a status (available or blocked); the name, location and capacity are required. |
| AC2. Given a venue record, when viewed by an authorised user, then its current attributes are shown. | Clarify | "Authorised user" is Event Coordinator, Venue Staff or Safety Officer (the same three roles that search, SCRUM-9). Technical Support may read only a venue's id, name and building (SCRUM-13). |
| AC3. Updates to a venue's attributes are reflected in venue search and suitability checks. | Keep | Observable as written: change a field, repeat the search or check, see a different answer. The effect on bookings already made at the venue is a different story (hotfix 13, Q&A #120, #122). |

Approval of this review: **not recorded.** Replace this line with the approver and date once the story owner or Jaren (Product Owner) has approved it.

## Increment scope

- **Included:** `POST /venues`, `GET /venues`, `GET /venues/{id}`, `PATCH /venues/{id}` in venueService; the venue list, new-venue and edit-venue pages and their form parsing (`frontend/app/venues`, `frontend/lib/venue-form.ts`); `0016_venues.sql`.
- **Excluded:** search and suitability logic themselves (SCRUM-9 and SCRUM-12; they are cited only to prove AC3); blocks for maintenance (SCRUM-23); setup and turnaround time (SCRUM-59, owns its own tests); flagging bookings when a venue changes (hotfix 13); deleting or retiring a venue (not in the story).
- **Actors and access:** only Venue Staff can create or update (any other role 403). Event Coordinator, Venue Staff and Safety Officer can read. A request with no session is 401.
- **State and persistence:** a venue is `available` or `blocked`; Venue Staff can change it by update. An update is applied in one step; a refused request changes nothing. `updated_at` advances on each update.
- **Team proposals:** the name and location must not be blank; the room layouts are the five in the briefing (classroom, theatre, boardroom, banquet, exhibition); facilities and accessibility features are free text (#134 gives no fixed list).

## Acceptance criteria

- **AC1:** Given a Venue Staff member, when they create or update a venue with its name, location, maximum capacity (a whole number above zero), facilities, accessibility features and supported room layouts, then it is saved with those values; an invalid request is refused with 422 and changes nothing; any other role gets 403.
- **AC2:** Given a venue, when an Event Coordinator, Venue Staff member or Safety Officer views it, then its current attributes are shown; any other role gets 403; an unknown venue is 404; no session is 401.
- **AC3:** Given a venue whose attributes were updated, when a coordinator searches venues or runs a suitability check, then the answer reflects the update.

## Test-case specification

| ID | AC | Test scenario | Technique | Pre-conditions | Test steps | Test data | Expected result | Forbidden side effects | Layer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AC1-H1 | AC1 | Every catalogue attribute is stored on create | Happy | Signed in as Venue Staff | `POST /venues`; read it back | Orchard Hall, Orchard Road, 200, projector and microphone, wheelchair_ramp and hearing_loop, theatre and classroom, AM and PM | 201; every field in the response and on re-read equals what was sent | — | API (new) |
| AC1-H2 | AC1 | Every attribute can be updated at once | Happy | Venue as above | `PATCH` all seven fields | Orchard Grand Hall, Marina Bay, 450, stage, lift, banquet, NIGHT | 200; every field changed | — | API (new) |
| AC1-H3 | AC1 | A created venue is available, with an id and timestamps | Happy | Signed in as Venue Staff | `POST /venues` | sample venue | 201; status `available`, id, created and updated times | — | API |
| AC1-H4 | AC1 | A partial update changes only what was sent | Happy | Venue 200 seats | `PATCH` capacity and facilities | 350, projector and stage | Those two change; the name is untouched; `updated_at` does not go back | — | API |
| AC1-H5 | AC1 | Venue Staff can take a venue out of service | Happy | Available venue | `PATCH` status | blocked | 200; status `blocked` | — | API |
| AC1-H6 | AC1 | The new-venue form asks for every attribute and offers no status | Happy | Venue Staff session | Render the new-venue form | — | Name, location, capacity, facilities, accessibility, layouts, setup and turnaround fields; no status | — | UI unit |
| AC1-H7 | AC1 | Every attribute is read from the form | Happy | Form values | Parse a complete venue | all fields | Payload has every attribute | — | UI unit |
| AC1-H8 | AC1, AC2 | Venue Staff add a venue, see it and update it in the browser | Happy | Mock venue API; `venue@example.com` / `test-password-123` | Add a venue with capacity 0 → error; correct to 45, add facilities, accessibility, Boardroom; save; edit to 60 and blocked | Orchard Studio | Error "Enter a whole number greater than zero."; card shows "up to 45 people" and Boardroom; then "up to 60 people" and Blocked | — | E2E |
| AC1-P1 | AC1 | Facilities, accessibility and layouts may be empty | Partition | Signed in as Venue Staff | `POST` with only name, location, capacity | Bare, Anywhere, 10 | 201; the three lists are empty | — | API (new) |
| AC1-P2 | AC1 | Comma lists are trimmed, blank-free and de-duplicated | Partition | Form values | Split `"Projector, , projector ,WiFi"` and `"   "` | — | `["Projector", "WiFi"]` and `[]` | — | UI unit |
| AC1-P3 | AC1 | Unknown layouts are dropped, an unknown status falls back to available, and operating slots are not sent | Partition | Form values | Parse a form with unknown values and slots | layouts theatre and ballroom, slots AM and MIDNIGHT, status gone | Layouts `["theatre"]`; no `operating_slots`; status `available` | — | UI unit |
| AC1-P4 | AC1 | Status is sent only when editing | Partition | Form values | Parse as create, then as edit | status blocked | No status on create; `blocked` on edit | — | UI unit |
| AC1-B1 | AC1 | A maximum capacity of 1 is accepted | Boundary | Signed in as Venue Staff | `POST` capacity 1 | 1 | 201 | — | API (new) |
| AC1-B2 | AC1 | A maximum capacity of 0 is refused | Boundary | Signed in as Venue Staff | `POST` capacity 0 | 0 | 422 | No venue stored | API (new) |
| AC1-N1 | AC1 | A negative capacity is refused | Negative | Signed in as Venue Staff | `POST` | -5 | 422 | No venue stored | API (new) |
| AC1-N2 | AC1 | A non-numeric capacity is refused | Negative | Signed in as Venue Staff | `POST` | "many" | 422 | No venue stored | API (new) |
| AC1-N3 | AC1 | A blank location is refused | Negative | Signed in as Venue Staff | `POST` | "" | 422 | No venue stored | API (new) |
| AC1-N4 | AC1 | An unknown room layout is refused | Negative | Signed in as Venue Staff | `POST` | "spaceship" | 422 | No venue stored | API (new) |
| AC1-N5 | AC1 | A refused update leaves the venue as it was | Negative | Venue exists | `PATCH` capacity 0 | 0 | 422; the venue read back is identical | Nothing changed | API (new) |
| AC1-N6 | AC1 | A zero capacity is refused (same boundary as AC1-B2) | Negative | Signed in as Venue Staff | `POST` capacity 0 | 0 | 422 | — | API |
| AC1-N7 | AC1 | Updating an unknown venue is 404 | Negative | No such venue | `PATCH /venues/does-not-exist` | — | 404 | — | API |
| AC1-N8 | AC1 | The form reports a capacity that is not a whole number above zero | Negative | Form values | Parse each | abc, 0, -3, 12.5, "" | Error; nothing sent | Nothing sent to venueService | UI unit |
| AC1-N9 | AC1 | The form reports a missing name or location | Negative | Form values | Parse with blanks | — | Error on each | Nothing sent | UI unit |
| AC1-N10 | AC1 | An invalid capacity stays as typed after a refused edit | Negative | Edit form | Submit -3 | -3 | Field still shows -3, not the stored value | — | UI unit |
| AC1-N11 | AC1 | An invalid capacity and the typed lists are echoed back unchanged | Negative | Form values | Read the raw values | — | Same text | — | UI unit |
| AC1-X1 | AC1 | Event Coordinator cannot create or update | Cross-cutting | Role `event_coordinator` | `POST` and `PATCH` | — | 403 and 403 | Venue unchanged | API (new) |
| AC1-X2 | AC1 | Safety Officer cannot create or update | Cross-cutting | Role `safety_officer` | Same | — | 403 and 403 | Venue unchanged | API (new) |
| AC1-X3 | AC1 | Event Organiser cannot create or update | Cross-cutting | Role `event_organiser` | Same | — | 403 and 403 | Venue unchanged | API (new) |
| AC1-X4 | AC1 | Technical Support cannot create or update | Cross-cutting | Role `technical_support` | Same | — | 403 and 403 | Venue unchanged | API (new) |
| AC1-X5 | AC1 | Attendee cannot create or update | Cross-cutting | Role `attendee` | Same | — | 403 and 403 | Venue unchanged | API (new) |
| AC1-X6 | AC1 | Event Coordinator Lead cannot create a venue | Cross-cutting | Role `event_operations_manager` | `POST` | — | 403 | — | API |
| AC1-X7 | AC1 | A coordinator cannot open the catalogue page | Cross-cutting | Coordinator session | Open `/venues/new` | — | Redirected to the unauthorised page | — | E2E |
| AC2-H1 | AC2 | Event Coordinator reads the current attributes | Happy | Venue updated to 260 seats; role `event_coordinator` | `GET /venues/{id}` | 260 | 200; 260 and the facilities | — | API (new) |
| AC2-H2 | AC2 | Venue Staff read the current attributes | Happy | Same; role `venue_staff` | Same | — | 200 | — | API (new) |
| AC2-H3 | AC2 | Safety Officer reads the current attributes | Happy | Same; role `safety_officer` | Same | — | 200 | — | API (new) |
| AC2-H4 | AC2 | Reading a venue shows what was stored | Happy | One venue | `GET /venues/{id}` | — | The stored record | — | API |
| AC2-H5 | AC2 | The list shows every venue | Happy | Two venues | `GET /venues` | — | Both | — | API |
| AC2-H6 | AC2 | Editing starts from the current attributes | Happy | Venue with values | Open the edit form | — | Every field shows the stored value | — | UI unit |
| AC2-N1 | AC2 | Event Organiser cannot read a venue | Negative | Role `event_organiser` | `GET /venues/{id}` and `GET /venues` | — | 403 and 403 | — | API (new) |
| AC2-N2 | AC2 | Technical Support cannot read a venue | Negative | Role `technical_support` | Same | — | 403 and 403 | — | API (new) |
| AC2-N3 | AC2 | Event Coordinator Lead cannot read a venue | Negative | Role `event_operations_manager` | Same | — | 403 and 403 | — | API (new) |
| AC2-N4 | AC2 | An attendee cannot read, search or run a suitability check | Negative | Role `attendee` | The four routes | — | 403 on each | — | API |
| AC2-N5 | AC2 | An unknown venue is 404 | Negative | No such venue | `GET /venues/does-not-exist` | — | 404 | — | API |
| AC2-N6 | AC2 | A request with no session is 401 | Negative | No override | `GET /venues` | — | 401 | — | API |
| AC3-H1 | AC3 | An updated capacity changes who is found by search | Happy | Venue of 50 | Search for 120 → none; `PATCH` to 150; search again | 120 | Not found, then found | — | API (new) |
| AC3-H2 | AC3 | Updated facilities, accessibility and layouts change what search finds | Happy | Venue with none | Search for stage, lift, banquet → none; `PATCH`; search again | stage, lift, banquet | Not found, then found | — | API (new) |
| AC3-H3 | AC3 | Taking a venue out of service removes it from search | Happy | Available venue | Search; `PATCH` blocked; search | — | Found, then not | — | API (new) |
| AC3-H4 | AC3 | An update changes a suitability verdict | Happy | Venue of 40 seats, no facilities | Check for 80 people and a stage → unsuitable with two mismatches; `PATCH` to 90 seats and a stage; check again | 80, stage | Unsuitable (capacity, facilities), then suitable with none | — | API (new) |

## Latest execution record

Build: `b5b53b0` (`dev` after PR #123) plus this branch's working tree (`docs/testcases-scrum-9-27-30`), run on Kennedy's machine on 1 November 2026 with Claude Code, pending human review. Backend tests ran against the in-memory venue store; the browser tests ran against the Node mock services. "Red first" was not observed for any case.

| ID | Automation status | Actual result | Execution status | Build or commit | Executed by and date | Remarks and evidence |
| --- | --- | --- | --- | --- | --- | --- |
| AC1-H3, AC1-H4, AC1-H5, AC1-N6, AC1-N7, AC1-X6, AC2-H4, AC2-H5, AC2-N4, AC2-N5, AC2-N6 | Green | Create, read, update, block, list, unknown venue, no session, attendee and Lead refusals behave as specified | Pass | b5b53b0 + working tree, local | Claude Code, 1 Nov 2026 | `backend/venueService/tests/test_venues_catalogue.py` (11 passed); labels added on 1 Nov 2026 |
| AC1-H1, AC1-H2, AC1-P1, AC1-B1, AC1-B2, AC1-N1, AC1-N2, AC1-N3, AC1-N4, AC1-N5, AC1-X1, AC1-X2, AC1-X3, AC1-X4, AC1-X5, AC2-H1, AC2-H2, AC2-H3, AC2-N1, AC2-N2, AC2-N3, AC3-H1, AC3-H2, AC3-H3, AC3-H4 | Green | Every attribute stored and updated; invalid input 422 with nothing stored; the five other roles 403 on create and update; three roles read, three refused; updates visible to search and suitability | Pass | same | same | New: `backend/venueService/tests/test_venues_catalogue_contract.py` (25 passed). With the file above: 36 passed. Passed first time: no defect found |
| AC1-H6, AC1-H7, AC1-P2, AC1-P3, AC1-P4, AC1-N8, AC1-N9, AC1-N10, AC1-N11, AC2-H6 | Green | Form shows and parses every attribute; invalid input reported; typed text kept | Pass | same | same | `frontend/__tests__/venues.test.tsx` (5 passed) and `frontend/__tests__/venue-form.test.ts` (26 passed); labels added on 1 Nov 2026. Both files also hold SCRUM-59 cases |
| AC1-H8, AC1-X7 | Green | Add, correct, save, edit and block in the browser; coordinator redirected | Pass | same | same | `frontend/e2e/venue-catalogue.spec.ts` against the Node mock services (3 tests; 14 passed across the five specs run) |

### Local validation evidence

| Check | Command and environment | Result | Remarks |
| --- | --- | --- | --- |
| Story tests, backend | `pytest tests/test_venues_catalogue.py tests/test_venues_catalogue_contract.py`, venueService, local Python 3.13 | 36 passed | In-memory store; no network |
| Story tests, suitability | `pytest tests/test_venues_suitability.py tests/test_suitability.py` | 31 passed | Cited for AC3-H4's neighbours; SCRUM-12 owns them |
| Backend regression | `pytest` (whole venueService suite); `ruff check .` | 790 passed, 10 skipped; clean | 747 before the new files |
| Frontend unit | `npx vitest run` (whole frontend suite) | 80 files, 762 passed | jsdom |
| Frontend static checks | `npm run typecheck`; `npm run lint` | Clean | — |
| End-to-end | `playwright test venue-search venue-catalogue assign-coordinator auth.spec equipment-catalogue` with the cached Chromium 1148 headless shell | 14 passed | The pinned browser build is not installed and was not downloaded |

Not run: the shared development database and the real Supabase store (the repository tests use a fake Data API), pull-request CI, reviewer approval.

## Open questions

1. **Operating hours (AC1).** The Jira wording asks for operating hours. After #131 the window is a fixed 07:00–24:00 for every venue, the form has no such field, and nothing reads a venue's stored `operating_slots`. The API still accepts and returns `operating_slots` (default AM, PM, NIGHT) so older data keeps working. Confirm that a fixed window is what the customer wants, and reword the AC; if per-venue hours are wanted, that is a new story.
2. **Blank name or location.** Refused with 422 as a team rule (AC1-N3 tests the location); the story does not say it.
3. **Two Venue Staff editing the same venue.** The last update wins; the story does not ask for a stale-edit check, unlike the coordinator's event edit (hotfix 8).
4. **Retiring a venue.** Q&A #122 asks what happens to future bookings when a venue is retired; there is no retire action in this story, only `blocked`.
