# SCRUM-23 — Block a Venue

**Jira:** [SCRUM-23](https://is212g9t4.atlassian.net/browse/SCRUM-23)

**User story:** As a Venue Staff member, I want to block a venue for maintenance, renovation, safety, or internal use, so that it is not offered or booked while it is unavailable.

## Story contract review

The original acceptance criteria were reviewed against the customer briefing (*Venue Unavailability Management*, *Venue Availability Calendar*) and the repository. The story owner approved this increment's scope on 4 October 2026: Venue Staff only, delivered in new frontend files before any shared navigation or teammate-owned page is changed.

| Original criterion | Outcome | Reason |
| --- | --- | --- |
| Venue Staff can mark a venue unavailable for a date-range/slot with a recorded reason. | Clarify | Inputs, inclusivity and refusals were not stated. |
| Given a blocked venue/slot, when a search or booking is attempted for that period, then the venue is not offered or booked. | Split | Search (AC2) is testable now; booking (AC2b) needs venue booking requests from SCRUM-15. |
| Given a block that affects an already-confirmed upcoming event, when applied, then the affected event's Coordinator is notified. | Clarify | Approved 8 October 2026: an approved booking request is the confirmed booking (0018), "upcoming" means it has not ended (Singapore date), and the recipient is the booking's requesting Coordinator, as in SCRUM-15. The block is still saved. |
| Blocked periods appear as "blocked" on the availability calendar. | Clarify | Viewer, covered periods and non-operating slots were not stated. |

## Increment scope

- **Included:** Venue Staff create a dated block through the frontend (AC1); dated search excludes blocked venues (AC2, already implemented and tested in venueService); Venue Staff view blocked periods on a monthly calendar (AC4).
- **Shared-file change:** one "Venue blocks" workspace link for Venue Staff in `frontend/app/components/app-shell.tsx`, with its expectations in `frontend/__tests__/workspace-links.test.ts`. The venue catalogue page (SCRUM-30) is unchanged; the block page has its own venue picker.
- **Review follow-ups (PR #45):** the AC3 placeholder that read allocations from an external `EVENT_ALLOCATIONS_URL` service was removed, because the agreed design (0018) makes an approved `venue_booking_requests` row the booking; AC3 will be rebuilt on that table after SCRUM-15. `GET /venues/{id}/blocks` is now Venue Staff only and `POST /venues/{id}/availability` is Venue Staff and Event Coordinators only. `database/migrations/0023_venue_blocks.sql` records the hand-created table and revokes browser-role access; it was applied to shared development on 6 October 2026.
- **Delivered later:** AC2b booking refusal arrived with SCRUM-15 (PR #48); AC3 Coordinator alerts on `feat/scrum-23-block-notifications`. **Excluded:** Event Coordinator calendar access; lifting a block (no endpoint); post-login landing change; notifying a reassigned Coordinator or the Organiser (C-9a; eventRequestService refuses the Coordinator lookup for Venue Staff).
- **Actors and access:** Only Venue Staff can open `/venue-blocks`, create a block or list block reasons; Venue Staff and Event Coordinators can run the availability check, which returns no free-text reasons; external roles get 403. venueService enforces the `venue_staff` role on `POST /venues/{id}/blocks`.
- **State:** A new block is `active`. `lifted` blocks are kept as history and never shown as blocked.
- **Persistence:** One `POST /venues/{venue_id}/blocks` call writes the block; the server sets its ID, creator, status and timestamp.
- **Assumptions:** A venue whose catalogue status is `blocked` (set on the venue edit page, SCRUM-30) is unavailable on every date, so the calendar shows it as unavailable rather than available. Dates are inclusive; the chosen slots apply on every date in the range; NIGHT belongs to its starting date; a block on a slot the venue does not operate is still shown as blocked; past dates are not refused because no AC requires it.

## Acceptance criteria

- **AC1:** Given Venue Staff and an existing venue, when they submit a start and end date (inclusive), at least one slot (AM/PM/NIGHT) and a reason (maintenance, renovation, safety or internal use, with optional detail up to 1,000 characters), then an active block is saved and shown. An end date before the start date, no slots, no reason or no venue is refused and nothing is saved; a non-Venue-Staff user cannot open the page and the API refuses them with 403.
- **AC2:** Given an active block on a venue for a date and slot, when someone searches for that date and slot, then the venue is not offered; it is still offered for unblocked dates and slots, and lifted blocks do not hide it.
- **AC2b:** Given an active block, when a booking for an overlapping date and slot is approved, then the approval is refused and recorded (delivered by SCRUM-15).
- **AC3:** Given Venue Staff create a block, when it shares a date and slot with an approved booking that has not ended, then the block is saved, the booking's requesting Coordinator receives a notification with the block's dates, slots and reason, and Venue Staff are told which bookings are affected. Pending or rejected requests, other venues, non-overlapping and ended bookings are not notified; a notification failure never fails the block.
- **AC4:** Given a venue with blocks, when Venue Staff view its availability calendar for a month, then every date and slot covered by an active block shows "Blocked" with its reason; lifted blocks and uncovered cells do not; slots the venue does not operate show "Not offered".

## Test-case specification

| ID | AC | Test scenario | Technique | Pre-conditions | Test steps | Test data | Expected result | Forbidden side effects | Layer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AC1-H1 | AC1 | A valid block reaches the API and the staffer lands on that venue's month | Happy | Venue Staff session | Submit the block form | Venue `v1`, 2026-10-20 to 2026-10-21, AM+PM, maintenance, "Air-con repairs" | `POST /venues/v1/blocks` with the normalised payload; `/venue-blocks` revalidated; redirect to `?venue=v1&month=2026-10&created=1` | No other endpoint is called | Unit (action) |
| AC1-H2 | AC1 | A saved block is confirmed and listed after the redirect | Happy | Venue `v1` has one active block | Open `/venue-blocks?venue=v1&month=2026-10&created=1` | Block from AC1-H1 | "Block saved" status and the block in "Recorded blocks" | — | Component |
| AC1-P1–P4 | AC1 | Every reason category is accepted and sent unchanged | Partition | Venue Staff | Submit with each reason | `maintenance`, `renovation`, `safety`, `internal_use` | Each is sent as `reason_category` | — | Unit (validation) |
| AC1-P5 | AC1 | One slot and all three slots are both accepted, in canonical order | Partition | Venue Staff | Submit with `PM` only, then `NIGHT, AM, PM` | — | `["PM"]` and `["AM","PM","NIGHT"]` | Unknown slot values are dropped, not sent | Unit (validation) |
| AC1-B1 | AC1 | A one-day block (end = start) is accepted | Boundary | Venue Staff | Submit | 2026-10-20 to 2026-10-20 | No errors | — | Unit (validation) |
| AC1-B2 | AC1 | An end date one day before the start is refused | Boundary | Venue Staff | Submit | 2026-10-20 to 2026-10-19 | `end_date` error | API is not called | Unit (validation + action) |
| AC1-B3 | AC1 | Detail at the 1,000-character limit is accepted; 1,001 is refused | Boundary | Venue Staff | Submit | 1,000 and 1,001 characters | First valid; second gets a `reason_detail` error | API is not called for 1,001 | Unit (validation) |
| AC1-N1 | AC1 | No slot chosen is refused | Negative | Venue Staff | Submit | No slots | `slots` error | API is not called | Unit (validation) |
| AC1-N2 | AC1 | Missing or unknown reason is refused | Negative | Venue Staff | Submit | `""`, `"holiday"` | `reason_category` error | API is not called | Unit (validation) |
| AC1-N3 | AC1 | Missing or impossible dates are refused | Negative | Venue Staff | Submit | `""`, `2026-02-30` | `start_date` / `end_date` errors | API is not called | Unit (validation) |
| AC1-N4 | AC1 | No venue chosen is refused | Negative | Venue Staff | Submit | Empty `venue_id` | `venue_id` error | API is not called | Unit (validation) |
| AC1-N5 | AC1 | API 403 is explained | Negative | Session lost Venue Staff role | Submit valid form | API returns 403 | "Only Venue Staff can block venues." and typed values kept | No redirect, no revalidation | Unit (action) |
| AC1-N6 | AC1 | API 404 (venue removed) is explained | Negative | Venue deleted after page load | Submit | API returns 404 | "This venue no longer exists." | No redirect | Unit (action) |
| AC1-N7 | AC1 | API 422 is explained without blaming highlighted fields | Negative | — | Submit | API returns 422 | "The venue service rejected these details…" | No redirect | Unit (action) |
| AC1-N8 | AC1 | Unreachable service or 5xx gives a retryable error | Negative | — | Submit | `fetch` rejects; API returns 502 | "The block could not be saved. Please try again." | No redirect | Unit (action) |
| AC1-N9 | AC1 | Expired session goes to sign-in | Negative | — | Submit | API returns 401 | Redirect to `/auth` | No revalidation | Unit (action) |
| AC1-X1 | AC1 | The page is Venue Staff only | Cross-cutting | Non-staff session | Open `/venue-blocks` | `requireRole` refuses | `requireRole("venue_staff")` is checked first | Venues and blocks are not fetched | Component |
| AC1-X2 | AC1 | The API refuses a non-staff caller | Cross-cutting | Event Coordinator principal | `POST /venues/{id}/blocks` | Valid body | 403 | No block is stored | API (backend) |
| AC1-X3 | AC1, AC4 | Only Venue Staff get a "Venue blocks" workspace link to the block page | Cross-cutting | Each role | Build the workspace links | Every role | Venue Staff: Venues, Venue blocks, Venue search; no other role gets `/venue-blocks` | No other role's links change | Unit + live check |
| AC1-X4 | AC1 | Block reasons are readable by Venue Staff only | Cross-cutting | One block with detail; caller is Event Coordinator, Event Organiser or Attendee | `GET /venues/{id}/blocks` | — | 403 | Reason text not returned; block unchanged | API (backend) |
| AC1-X6 | AC1 | The block table is reproducible and closed to browser roles | Cross-cutting | Fresh Postgres with 0016 applied | Apply `0023_venue_blocks.sql` twice | — | Table matches the shared schema; second run is a no-op; `anon`/`authenticated` have no privileges; RLS on | Shared database not touched | DB |
| AC2-X1 | AC2 | Only internal planners can run the availability check | Cross-cutting | Caller of each role | `POST /venues/{id}/availability` | Venue Staff, Event Coordinator, Event Organiser, Attendee | 200, 200, 403, 403 | No block free text in any response | API (backend) |
| AC2-H1 | AC2 | Search excludes a venue on its blocked date/slot, including both boundary dates | Happy | Venue with a 20–21 Sep AM block | Search each date | 2026-09-20/21/22, AM | Excluded on 20 and 21, included on 22 | — | API (backend, existing) |
| AC2-P1 | AC2 | Non-overlapping dates and slots still offer the venue | Partition | AM block on 20–21 Sep | Search other dates and slots | 2026-09-19/22 AM, 2026-09-20 PM | Venue included | — | API (backend) |
| AC4-H1 | AC4 | Covered cells show "Blocked" with the reason | Happy | Active block 20–21 Oct AM+PM, maintenance | Build and render October | — | 4 cells blocked with "Maintenance — Air-con repairs" | Other cells not blocked | Unit + component |
| AC4-B1 | AC4 | The first and last days are blocked; the days either side are not | Boundary | Same block | Build October | 19, 20, 21, 22 Oct | 20 and 21 blocked; 19 and 22 open | — | Unit |
| AC4-B2 | AC4 | A block spanning two months appears in both, only on its own days | Boundary | Block 30 Oct–2 Nov | Build October and November | — | 30–31 Oct and 1–2 Nov blocked | 29 Oct and 3 Nov open | Unit |
| AC4-B3 | AC4 | Month navigation and invalid months are handled | Boundary | — | Build December; parse `2026-13`, `abc` | — | Next of 2026-12 is 2027-01; invalid month falls back to the current month | — | Unit |
| AC4-P1 | AC4 | A lifted block is not shown as blocked | Partition | Lifted block | Build month | — | Cells open | — | Unit |
| AC4-P2 | AC4 | Non-operating slots show "Not offered" unless an active block covers them | Partition | Venue operates AM, PM | Build month with and without a NIGHT block | — | NIGHT is not offered; NIGHT under a block is blocked | — | Unit |
| AC4-P3 | AC4 | Overlapping blocks list every reason in the cell | Partition | Two active blocks on the same cell | Build month | — | Both reasons listed | — | Unit |
| AC4-P4 | AC4 | Another venue's block never marks this calendar | Partition | Block with a different `venue_id` | Build month | — | Cells open | — | Unit |
| AC4-P6 | AC4 | A venue blocked in the catalogue (whole-venue status) is unavailable on every date | Partition | Venue `status` is `blocked`; one dated block | Open the calendar | — | Banner "This venue is blocked in the catalogue…"; operating cells "Unavailable"; dated blocks keep their reasons; non-operating slots stay "Not offered" | No cell shows "Available"; the block form stays usable | Unit + component |
| AC4-N1 | AC4 | Venue service down shows an outage, not an empty catalogue | Negative | `listVenues` fails | Open page | — | Alert "The venue service is unavailable…" | No form or calendar | Component |
| AC4-N2 | AC4 | Unknown venue in the URL is reported | Negative | `?venue=` not in catalogue | Open page | `missing` | "Venue not found" | No form or calendar | Component |
| AC4-N3 | AC4 | Failed block lookup never shows an all-open calendar | Negative | `listVenueBlocks` fails | Open page | — | Alert that blocks could not be loaded | No calendar cells are shown as open | Component |
| AC4-P5 | AC4 | An empty catalogue is presented plainly | Partition | No venues | Open page | — | "No venues in the catalogue yet." | No form | Component |

### Backend test cases (venueService)

Each backend test carries its ID in a one-line label comment; parametrized cases have per-case IDs (for example `AC1-N10a`). Pre-conditions use the in-memory stores reset by `tests/conftest.py`, signed in as Venue Staff unless stated.

| ID | AC | Test scenario | Technique | Expected result | Layer | Test |
| --- | --- | --- | --- | --- | --- | --- |
| AC1-H3 | AC1 | A valid block request parses its dates and slots | Happy | Dates and slot enum parsed | Unit | `test_block_models.py` |
| AC1-H4 | AC1 | A stored block gets an id, a UTC timestamp and active status | Happy | Server defaults set | Unit | `test_block_models.py` |
| AC1-H5 | AC1 | The API stores a normalised block with server-set id, creator and status | Happy | 201; slots ordered, detail trimmed, creator from the token | API | `test_venue_blocks.py` |
| AC1-H6 | AC1 | Blocks persist in the database across requests and drive search | Happy | Stored rows returned and applied by later requests | API + mocked Data API | `test_database_storage.py` |
| AC1-P6 | AC1 | Each story reason category is accepted | Partition | All four accepted | Unit | `test_block_models.py` |
| AC1-P7 | AC1 | Detail is trimmed, blank becomes absent, 1,000 characters kept | Partition | Normalised values | Unit | `test_block_models.py` |
| AC1-P8 | AC1 | Repeated blocks get distinct ids; detail is optional | Partition | Two rows, distinct ids, null detail | API | `test_venue_blocks.py` |
| AC1-B4 | AC1 | A same-day full-day block keeps AM, PM, NIGHT order | Boundary | Canonical order | Unit | `test_block_models.py` |
| AC1-N10–N13 | AC1 | Invalid dates/slots/reasons, missing reason, client-set server fields, blank identity | Negative | Validation error | Unit | `test_block_models.py` |
| AC1-N14 | AC1 | Unknown venue | Negative | 404; nothing stored | API | `test_venue_blocks.py` |
| AC1-N15 | AC1 | Invalid or spoofed request body | Negative | 422; nothing stored | API | `test_venue_blocks.py` |
| AC1-N16 | AC1 | Unknown or malformed venue id in database mode | Negative | 404; nothing written | API + mocked Data API | `test_database_storage.py` |
| AC1-N17 | AC1 | Database constraint/permission errors | Negative | 409, 422, 502; no database detail leaked | API + mocked Data API | `test_database_storage.py` |
| AC1-N18 | AC1 | Non-UUID creator | Negative | Refused before any database call | Unit | `test_database_storage.py` |
| AC1-X5 | AC1 | Database mode needs a URL and a server-side secret key | Cross-cutting | Settings rejected | Unit | `test_database_storage.py` |
| AC2-H2 | AC2 | A block identifies exactly the dates and slots it shares with a booking | Happy | Shared cells only | Unit | `test_slots.py` |
| AC2-H3 | AC2 | The availability check reports block conflicts | Happy | `available: false`, conflict dates/slots; no writes | API | `test_block_checks.py` |
| AC2-P2 | AC2 | Overlap is symmetric | Partition | Same result either order | Unit | `test_slots.py` |
| AC2-P3 | AC2 | A lifted block does not hide the venue | Partition | Venue included | API | `test_block_availability.py` |
| AC2-P4 | AC2 | Search without a date makes no dated claim | Partition | Dated blocks ignored | API | `test_block_availability.py` |
| AC2-P5 | AC2 | Date-only search needs one operating slot free across all blocks | Partition | Excluded only when every slot is blocked | API | `test_block_availability.py` |
| AC2-P6 | AC2 | A block on a non-operating slot does not hide the venue | Partition | Venue included | API | `test_block_availability.py` |
| AC2-P7 | AC2 | A venue with no operating slots is not offered for a date | Partition | Venue excluded | API | `test_block_availability.py` |
| AC2-P8 | AC2 | Dated search keeps every catalogue filter | Partition | Filters still applied | API | `test_block_availability.py` |
| AC2-P9 | AC2 | Catalogue-blocked venue or non-operating slot is unavailable | Partition | Reason codes reported | API | `test_block_checks.py` |
| AC2-P10 | AC2 | A database block hides only its own venue | Partition | Other venue still offered | API + mocked Data API | `test_database_storage.py` |
| AC2-B1–B3 | AC2 | Leap day/month end, widest date range, last representable date | Boundary | Overlap computed correctly | Unit | `test_slots.py` |
| AC2-B4 | AC2 | Every slot blocked excludes a date-only search | Boundary | Venue excluded | API | `test_block_availability.py` |
| AC2-B5 | AC2 | NIGHT belongs to its starting date | Boundary | Only the starting date affected | API | `test_block_availability.py` |
| AC2-B6 | AC2 | Availability treats block dates as inclusive | Boundary | 30 Sep and 4 Oct free; 1 and 3 Oct blocked | API | `test_block_checks.py` |
| AC2-N1 | AC2 | Reversed period | Negative | ValueError in both checks | Unit | `test_slots.py` |
| AC2-N2 | AC2 | Invalid date or slot in search | Negative | 422 | API | `test_block_availability.py` |
| AC2-N3 | AC2 | Invalid availability body | Negative | 422 | API | `test_block_checks.py` |
| AC2-N4 | AC2 | Availability for an unknown venue | Negative | 404 | API | `test_block_checks.py` |
| AC4-H2 | AC4 | A venue's block list is scoped to it and keeps lifted blocks | Happy | Own blocks only, lifted included | API | `test_block_availability.py` |
| AC4-P7 | AC4 | A venue with no blocks | Partition | `[]` | API | `test_block_availability.py` |
| AC4-N4 | AC4 | Block list for an unknown venue | Negative | 404 | API | `test_block_availability.py` |
| AC4-N5 | AC4 | Database timeout | Negative | Error, never an empty list | Unit | `test_database_storage.py` |

### AC2b and AC3 test cases

| ID | AC | Test scenario | Technique | Expected result | Layer | Test |
| --- | --- | --- | --- | --- | --- | --- |
| AC2b | AC2b | Approval of a booking over an active block is refused and recorded | Happy | 409 `active_block`; refusal logged | API + DB | SCRUM-15: `tests/test_booking_decision_api.py` (AC5-H1), `database/verify_venue_booking_decisions.sql` |
| AC3-H1 | AC3 | A block over an approved, upcoming booking notifies its requesting Coordinator | Happy | One `venue_block_affects_booking` event with block and booking details; idempotency key ≤ 64 chars | API + E2E | `tests/test_block_impact_notifications.py`; `frontend/e2e/venue-blocking.spec.ts` |
| AC3-H2 | AC3 | Every affected booking is notified once | Happy | One event per affected booking | API | `tests/test_block_impact_notifications.py` |
| AC3-P1 | AC3 | Pending/rejected requests, other venues, other slots and later dates are not notified | Partition | No events | API | `tests/test_block_impact_notifications.py` |
| AC3-B1 | AC3 | A booking ending today is upcoming; one that ended yesterday is not | Boundary | Today notified; yesterday not | API | `tests/test_block_impact_notifications.py` |
| AC3-N1 | AC3 | A notification failure never fails or undoes the block | Negative | 201; block stored | API | `tests/test_block_impact_notifications.py` |
| AC3-N2 | AC3 | A refused block (422, 404) sends nothing | Negative | No events | API | `tests/test_block_impact_notifications.py` |
| AC3-H5, AC3-P6 | AC3 | The Coordinator's inbox explains the block | Happy / Partition | Venue, event, dates, slots, reason; sparse payloads still read well; link to the coordination page | Unit | `frontend/__tests__/booking-notifications.test.ts` |
| AC3-H6, AC3-P7 | AC3 | Venue Staff see which confirmed bookings a new block affects | Happy / Partition | Saved message lists affected bookings and says their Coordinators were notified; plain "Block saved." otherwise | Component | `frontend/__tests__/venue-blocks.test.tsx`, `venue-block-actions.test.ts` |

## Latest execution record

Build: `feat/venue-blocking` at `c352c51` plus the PR #45 review follow-ups (dev merged at `6673a21`). Executed with Claude Code on 6 October 2026, pending human review.

| ID | Automation status | Actual result | Execution status | Build or commit | Executed by and date | Remarks and evidence |
| --- | --- | --- | --- | --- | --- | --- |
| AC1-H1 | Green | Payload posted once; `/venue-blocks` revalidated; redirect to the venue's month; venue id URL-encoded | Pass | c352c51 + review follow-ups, local | Claude Code, 4 Oct 2026 | `frontend/__tests__/venue-block-actions.test.ts`, `venue-block-form.test.ts`, `venue-blocks.test.tsx` |
| AC1-H2 | Green | "Block saved." status and block listed | Pass | same | same | `frontend/__tests__/venue-blocks.test.tsx` |
| AC1-P1–P5 | Green | All four reasons accepted; slots canonicalised, unknown dropped | Pass | same | same | `frontend/__tests__/venue-block-form.test.ts` |
| AC1-B1–B3 | Green | One-day block accepted; end-before-start refused without an API call; 1,000/1,001 detail boundary held; blank detail omitted | Pass | same | same | `venue-block-form.test.ts`, `venue-block-actions.test.ts` |
| AC1-N1–N4 | Green | Each refusal gives its field error | Pass | same | same | `frontend/__tests__/venue-block-form.test.ts` |
| AC1-N5–N9 | Green | 403/404/422/502/network messages with input kept; 401 redirects to `/auth`; no revalidation on failure | Pass | same | same | `frontend/__tests__/venue-block-actions.test.ts` |
| AC1-X1 | Green | Role checked before any data or API call (page and action); live: coordinator redirected to `/unauthorised` | Pass | same | same | `venue-blocks.test.tsx`, `venue-block-actions.test.ts`; live check below |
| AC1-X3 | Green | Venue Staff menu shows Venues, Venue blocks, Venue search; coordinator menu unchanged (live) | Pass | same | same | Red observed first, then Green: `frontend/__tests__/workspace-links.test.ts` (2 SCRUM-27 expectations updated to include the new link, 1 test added) |
| AC1-X2 | Green | Coordinator principal gets 403; nothing stored | Pass | same | same | `backend/venueService/tests/test_venue_blocks.py::test_non_venue_staff_cannot_create_block` |
| AC1-X4, AC2-X1 | Green | Organiser/attendee/coordinator get 403 on the block list; organiser/attendee get 403 and staff/coordinator 200 on availability | Pass | c352c51 + review follow-ups, local | Claude Code, 6 Oct 2026 | Red observed first (5 refusal cases returned 200), then Green: `tests/test_venue_blocks.py` |
| AC1-X6 | Green | Applied twice on a throwaway `postgres:16-alpine`; columns match; second run skipped; `anon`/`authenticated` have no SELECT; RLS on | Pass | same | same | Applied to shared development on 6 October 2026 (SQL Editor): `has_table_privilege` false for `anon` and `authenticated`; publishable key `401` (`42501`); secret key still reads 2 blocks |
| Backend AC1/AC2/AC4 catalogue | Green | All 48 block tests labelled and passing | Pass | same | same | `backend/venueService/tests/` (see Backend test cases) |
| AC4-H1, B1–B3, P1–P4 | Green | Calendar model and rendering as specified | Pass | same | same | `frontend/__tests__/block-calendar.test.ts`, `venue-blocks.test.tsx` |
| AC4-P6 | Green | Banner shown; operating cells Unavailable; dated block reasons kept; no Available cell | Pass | same | same | Red observed first (cell was `open`), then Green: `block-calendar.test.ts`, `venue-blocks.test.tsx` |
| AC4-N1–N3, P5 | Green | Outage, not-found, failed block lookup (no open calendar) and empty catalogue each reported | Pass | same | same | `frontend/__tests__/venue-blocks.test.tsx` |
| AC2b | Green | Approval over an active block refused with `active_block` and recorded | Pass | dev at `2997af2` (PR #48) | Claude Code, 7–8 Oct 2026 | Evidence in `docs/testcases/scrum_15_testcases.md` (AC5-H1, DB-1) |
| AC3 (backend) | Green | Affected Coordinators notified once each; unaffected, ended and refused cases send nothing; failure keeps the block | Pass | `feat/scrum-23-block-notifications` working tree on dev `36432fe` | Claude Code, 8 Oct 2026 | Red first (the 3 notify cases sent nothing), then Green: `tests/test_block_impact_notifications.py` |
| AC3 (frontend) | Green | Inbox message; staff told which bookings are affected; block id passed back after saving | Pass | same | same | Red first (5 cases), then Green: `booking-notifications.test.ts`, `venue-blocks.test.tsx`, `venue-block-actions.test.ts` (2 redirect expectations updated) |
| AC3 (E2E) | Green | Staff block a booked slot, see the affected booking, Coordinator inbox shows the alert | Pass | same | same | `CI=1 npx playwright test`: 31 passed; dates use next year so the "not ended" rule stays true |
| E2E journey | Green | Venue Staff reach Venue blocks from the menu, see a slot error, block a venue, see it Blocked with its reason on the calendar; a Coordinator's dated search no longer offers that slot but still offers the other; Coordinators are redirected from `/venue-blocks` | Pass | `feat/venue-booking-decision` at 9a0859d + working tree, local | Claude Code, 8 Oct 2026 | `CI=1 npx playwright test`: 30 passed. `frontend/e2e/venue-blocking.spec.ts`; block endpoints added to the shared `e2e/support/venue-api.mjs`. Lands with the SCRUM-15 PR |

**Red phase:** the new tests were written first and failed because the modules did not exist. Under `testing.md` §5 that is not a valid behavioural Red, so no Red evidence is claimed.

### Local validation evidence

| Boundary | Command or environment | Result | Limitation |
| --- | --- | --- | --- |
| Frontend unit/component | `npx vitest run` (from `frontend/`) | 25 files, 236 passed (46 SCRUM-23 tests new or updated) | API calls mocked. |
| Frontend lint and types | `npm run lint`; `npm run typecheck` | Passed | Local only. |
| Production build | `npm run build` | Passed; `/venue-blocks` listed as a dynamic route | Local only. |
| Backend | `ruff check .`; `pytest` in `python:3.12-slim` (the Docker image's Python) | Lint clean; 259 passed (includes SCRUM-32 and suitability) | In-memory repositories. |
| Live stack, read-only | Docker Compose services + `npm run dev`; Venue Staff (`venue_staff@example.com`) and Event Coordinator (`event_coordinator1@example.com`) test accounts | Staff page renders form, calendar and list; existing Supabase block (20–21 Sep, AM/PM) shown Blocked with its reason, 19 and 22 Sep and NIGHT Available; coordinator redirected to `/unauthorised` | No block was created in the shared database. |

Pull-request CI and reviewer approval: not yet run.
