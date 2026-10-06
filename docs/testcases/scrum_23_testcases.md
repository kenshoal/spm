# SCRUM-23 — Block a Venue

**Jira:** [SCRUM-23](https://is212g9t4.atlassian.net/browse/SCRUM-23)

**User story:** As a Venue Staff member, I want to block a venue for maintenance, renovation, safety, or internal use, so that it is not offered or booked while it is unavailable.

## Story contract review

The original acceptance criteria were reviewed against the customer briefing (*Venue Unavailability Management*, *Venue Availability Calendar*) and the repository. The story owner approved this increment's scope on 4 October 2026: Venue Staff only, delivered in new frontend files before any shared navigation or teammate-owned page is changed.

| Original criterion | Outcome | Reason |
| --- | --- | --- |
| Venue Staff can mark a venue unavailable for a date-range/slot with a recorded reason. | Clarify | Inputs, inclusivity and refusals were not stated. |
| Given a blocked venue/slot, when a search or booking is attempted for that period, then the venue is not offered or booked. | Split | Search (AC2) is testable now; booking (AC2b) needs venue booking requests from SCRUM-15. |
| Given a block that affects an already-confirmed upcoming event, when applied, then the affected event's Coordinator is notified. | Keep, dependent | Needs confirmed venue bookings (SCRUM-15) and notification delivery (SCRUM-37). |
| Blocked periods appear as "blocked" on the availability calendar. | Clarify | Viewer, covered periods and non-operating slots were not stated. |

## Increment scope

- **Included:** Venue Staff create a dated block through the frontend (AC1); dated search excludes blocked venues (AC2, already implemented and tested in venueService); Venue Staff view blocked periods on a monthly calendar (AC4).
- **Shared-file change:** one "Venue blocks" workspace link for Venue Staff in `frontend/app/components/app-shell.tsx`, with its expectations in `frontend/__tests__/workspace-links.test.ts`. The venue catalogue page (SCRUM-30) is unchanged; the block page has its own venue picker.
- **Excluded:** AC2b booking refusal and AC3 Coordinator notification (wait on SCRUM-15 bookings and SCRUM-37); Event Coordinator calendar access; lifting a block (no endpoint); post-login landing change (shared file, next increment); booking requests inbox (SCRUM-15).
- **Actors and access:** Only Venue Staff can open `/venue-blocks` or create a block. venueService enforces the `venue_staff` role on `POST /venues/{id}/blocks`.
- **State:** A new block is `active`. `lifted` blocks are kept as history and never shown as blocked.
- **Persistence:** One `POST /venues/{venue_id}/blocks` call writes the block; the server sets its ID, creator, status and timestamp.
- **Assumptions:** A venue whose catalogue status is `blocked` (set on the venue edit page, SCRUM-30) is unavailable on every date, so the calendar shows it as unavailable rather than available. Dates are inclusive; the chosen slots apply on every date in the range; NIGHT belongs to its starting date; a block on a slot the venue does not operate is still shown as blocked; past dates are not refused because no AC requires it.

## Acceptance criteria

- **AC1:** Given Venue Staff and an existing venue, when they submit a start and end date (inclusive), at least one slot (AM/PM/NIGHT) and a reason (maintenance, renovation, safety or internal use, with optional detail up to 1,000 characters), then an active block is saved and shown. An end date before the start date, no slots, no reason or no venue is refused and nothing is saved; a non-Venue-Staff user cannot open the page and the API refuses them with 403.
- **AC2:** Given an active block on a venue for a date and slot, when someone searches for that date and slot, then the venue is not offered; it is still offered for unblocked dates and slots, and lifted blocks do not hide it.
- **AC2b (dependent on SCRUM-15):** Given an active block, when a booking for an overlapping date and slot is approved, then the approval is refused.
- **AC3 (dependent on SCRUM-15 and SCRUM-37):** Given a block that affects an already-confirmed upcoming event, when it is applied, then the event's Coordinator is notified.
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
| AC2-H1 | AC2 | Search excludes a venue on its blocked date/slot, including both boundary dates | Happy | Venue with a 20–21 Sep AM block | Search each date | 2026-09-20/21/22, AM | Excluded on 20 and 21, included on 22 | — | API (backend, existing) |
| AC2-P1 | AC2 | Lifted blocks and non-overlapping slots do not hide a venue | Partition | Lifted block; PM search on AM block | Search | — | Venue included | — | API (backend, existing) |
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

Planned for the next increment (needs shared files): an end-to-end journey in `frontend/e2e/` (block → calendar → search), which requires block endpoints in the shared mock `e2e/support/venue-api.mjs`.

## Latest execution record

Build: uncommitted working tree on `feat/venue-blocking` at `c9ebb5d` (dev merged at `48b55ae`). Executed with Claude Code on 4 October 2026, pending human review.

| ID | Automation status | Actual result | Execution status | Build or commit | Executed by and date | Remarks and evidence |
| --- | --- | --- | --- | --- | --- | --- |
| AC1-H1 | Green | Payload posted once; `/venue-blocks` revalidated; redirect to the venue's month; venue id URL-encoded | Pass | c9ebb5d + working tree, local | Claude Code, 4 Oct 2026 | `frontend/__tests__/venue-block-actions.test.ts`, `venue-block-form.test.ts`, `venue-blocks.test.tsx` |
| AC1-H2 | Green | "Block saved." status and block listed | Pass | same | same | `frontend/__tests__/venue-blocks.test.tsx` |
| AC1-P1–P5 | Green | All four reasons accepted; slots canonicalised, unknown dropped | Pass | same | same | `frontend/__tests__/venue-block-form.test.ts` |
| AC1-B1–B3 | Green | One-day block accepted; end-before-start refused without an API call; 1,000/1,001 detail boundary held; blank detail omitted | Pass | same | same | `venue-block-form.test.ts`, `venue-block-actions.test.ts` |
| AC1-N1–N4 | Green | Each refusal gives its field error | Pass | same | same | `frontend/__tests__/venue-block-form.test.ts` |
| AC1-N5–N9 | Green | 403/404/422/502/network messages with input kept; 401 redirects to `/auth`; no revalidation on failure | Pass | same | same | `frontend/__tests__/venue-block-actions.test.ts` |
| AC1-X1 | Green | Role checked before any data or API call (page and action); live: coordinator redirected to `/unauthorised` | Pass | same | same | `venue-blocks.test.tsx`, `venue-block-actions.test.ts`; live check below |
| AC1-X3 | Green | Venue Staff menu shows Venues, Venue blocks, Venue search; coordinator menu unchanged (live) | Pass | same | same | Red observed first, then Green: `frontend/__tests__/workspace-links.test.ts` (2 SCRUM-27 expectations updated to include the new link, 1 test added) |
| AC1-X2 | Green | Coordinator principal gets 403; nothing stored | Pass | same | same | `backend/venueService/tests/test_venue_blocks.py::test_non_venue_staff_cannot_create_block` |
| AC2-H1, AC2-P1 | Green (existing) | Boundary dates excluded, neighbouring date and lifted block included | Pass | same | same | `backend/venueService/tests/test_block_availability.py` |
| AC4-H1, B1–B3, P1–P4 | Green | Calendar model and rendering as specified | Pass | same | same | `frontend/__tests__/block-calendar.test.ts`, `venue-blocks.test.tsx` |
| AC4-P6 | Green | Banner shown; operating cells Unavailable; dated block reasons kept; no Available cell | Pass | same | same | Red observed first (cell was `open`), then Green: `block-calendar.test.ts`, `venue-blocks.test.tsx` |
| AC4-N1–N3, P5 | Green | Outage, not-found, failed block lookup (no open calendar) and empty catalogue each reported | Pass | same | same | `frontend/__tests__/venue-blocks.test.tsx` |
| AC2b, AC3 | — | — | Blocked | — | — | Wait on SCRUM-15 venue bookings and SCRUM-37 delivery. |
| E2E journey | Planned | — | Not executed | — | — | Needs block endpoints in the shared `e2e/support/venue-api.mjs`. |

**Red phase:** the new tests were written first and failed because the modules did not exist. Under `testing.md` §5 that is not a valid behavioural Red, so no Red evidence is claimed.

### Local validation evidence

| Boundary | Command or environment | Result | Limitation |
| --- | --- | --- | --- |
| Frontend unit/component | `npx vitest run` (from `frontend/`) | 22 files, 199 passed (46 SCRUM-23 tests new or updated) | API calls mocked. |
| Frontend lint and types | `npm run lint`; `npm run typecheck` | Passed | Local only. |
| Production build | `npm run build` | Passed; `/venue-blocks` listed as a dynamic route | Local only. |
| Backend | `ruff check .`; `pytest` in `python:3.12-slim` (the Docker image's Python) | Lint clean; 188 passed | In-memory repositories. |
| Live stack, read-only | Docker Compose services + `npm run dev`; Venue Staff (`venue_staff@example.com`) and Event Coordinator (`event_coordinator1@example.com`) test accounts | Staff page renders form, calendar and list; existing Supabase block (20–21 Sep, AM/PM) shown Blocked with its reason, 19 and 22 Sep and NIGHT Available; coordinator redirected to `/unauthorised` | No block was created in the shared database. |

Pull-request CI and reviewer approval: not yet run.
