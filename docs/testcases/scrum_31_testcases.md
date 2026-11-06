# SCRUM-31 Test Cases: View Venue Availability

Last reviewed: 20 October 2026

Status: **approved by the story owner (Kennedy) on 19 October 2026**, including assumptions A1 to A6 as proposed (A1, tentative holds not applicable, and A2, the roles, still to be confirmed with the Product Owner). Q1 and Q2 are left open: Technical Support stays excluded, and the page is reached from venue search only. Nothing has been built yet; results are recorded below as work proceeds.

## Story

| Field | Value |
| --- | --- |
| Jira key | SCRUM-31 |
| Title | View Venue Availability |
| Sprint | Sprint 3 (ends 22 October 2026) |
| Points | 1 (estimate from Sprint 1; the real size is larger, see Included and excluded behaviour) |
| User story | As an Event Coordinator, I want to view a venue's availability across dates and times, so that I can identify when it can be requested for an event. |
| Scope decision | Delivered on the current AM / PM / Night slot model, agreed by the Product Owner on 19 October 2026. The move to 15-minute times (Discussion #131) is handled by SCRUM-65, which will convert this view. |

## Story contract

The four Jira criteria (restored to their original wording on 19 October 2026) were reviewed with the vocabulary in `docs/standards/testing.md` §1.

| ID | Criterion | Review outcome | Reason |
| --- | --- | --- | --- |
| AC1 | An authorised internal user can view a venue's availability by date and time slot (AM / PM / Night). | **Keep, Clarify** | "Authorised internal user" is taken as the roles that can already view the venue catalogue: Event Coordinator, Venue Staff and Safety Officer (A2). A month at a time, one row per date, one column per slot. |
| AC2 | The calendar reflects confirmed bookings, tentative holds, and blocked/unavailable periods. | **Split** | Confirmed bookings (approved booking requests) and blocks exist and are covered. **Tentative holds do not exist** (SCRUM-18 is not built or scheduled), so that part is not applicable until SCRUM-18 is delivered (A1). |
| AC3 | Given a slot with a confirmed booking or a block, when the calendar is viewed, then that slot is shown as unavailable. | **Keep** | "Unavailable" means not open: a slot that is booked or blocked is shown as such, in words. |
| AC4 | Availability shown is consistent with the venue's operating information. | **Keep, Clarify** | Operating information is the venue's operating slots and its catalogue status. Consistency is also checked against venue search, which already uses the same rule. |

### Included and excluded behaviour

| | Behaviour | Jira |
| --- | --- | --- |
| Included | `GET /venues/{venue_id}/calendar?month=YYYY-MM`: one month of slot states for one venue, with no private details | SCRUM-31 |
| Included | A read-only availability page for coordinators, venue staff and safety officers, reached from the venue search results | SCRUM-31 |
| Excluded | The Venue Staff calendar with block reasons and event names (`/venue-blocks`, koei's page): unchanged | SCRUM-23 |
| Excluded | Tentative holds on the calendar | SCRUM-18 |
| Excluded | Conversion to 15-minute times | SCRUM-65 |
| Excluded | Setup and turnaround time on the calendar | SCRUM-59, SCRUM-20 |
| Excluded | Booking from the calendar, or any write | Not in this story |

### Actors and relationship permissions

- Event Coordinator, Venue Staff and Safety Officer may read any venue's calendar (A2). It is catalogue-level information, not an event's data.
- Every other role, and anyone without a token, is refused.
- Nobody can change anything through this read.

### State and persistence

Read-only: no table is written and no migration is needed. A slot's state is derived, in this order: an active block shows as `blocked`, otherwise an approved booking shows as `booked`, otherwise a slot the venue does not operate shows as `not_offered`, otherwise a venue blocked in the catalogue shows as `unavailable`, otherwise `open`. This is the order the Venue Staff calendar already uses, so the two screens agree.

### Assumptions and open questions

| ID | Assumption or question | Used by |
| --- | --- | --- |
| A1 | Tentative holds are not applicable until SCRUM-18 exists. The Product Owner is to confirm this reading of AC2. | AC2 |
| A2 | "Authorised internal user" means Event Coordinator, Venue Staff and Safety Officer, the roles that can already view the venue catalogue. Technical Support, organisers and attendees are refused. | AC1-N8 to AC1-N10 |
| A3 | The calendar shows each slot's state only. It never shows block reasons, event names, booking ids or user ids; those stay on the Venue Staff page. | AC1-X2 |
| A4 | Pending, rejected and cancelled booking requests never show as booked; only approved ones do. Pending requests reserve nothing (SCRUM-32). | AC2-P2 to AC2-P4 |
| A5 | A month at a time, with no limit on how far back or forward. Dates are plain calendar dates with no time zone. | AC1 |
| A6 | An active block shows even on a slot the venue does not operate, as on the Venue Staff calendar. | AC4-P3 |
| Q1 | Should Technical Support see availability? Today they can see only a venue's name and building. | none |
| Q2 | Should the page have its own entry in the main menu, which is a shared file? The plan is a link from each venue search result only. | AC1-U6 |

## Test-case matrix

### Specification

| ID | AC | Test scenario | Technique | Pre-conditions | Test steps | Test data | Expected result | Forbidden side effects | Layer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AC1-H1 | AC1 | A coordinator reads a month for an open venue | Happy | Venue operating all slots, no blocks or bookings | `GET /venues/{id}/calendar?month=2026-10` as `event_coordinator` | October 2026 | 200; 31 dates in order; each with AM, PM and NIGHT; every state `open` | none | API |
| AC1-P1, AC1-P2 | AC1 | Venue Staff and a Safety Officer may also read it | Partition | As AC1-H1 | Same call as `venue_staff`; as `safety_officer` | none | 200 with the same shape | none | API |
| AC1-B1 | AC1 | A leap-year February has 29 dates | Boundary | As AC1-H1 | Read February 2028 | `2028-02` | 29 dates, last `2028-02-29` | none | API |
| AC1-B2 | AC1 | A common-year February has 28 dates | Boundary | As AC1-H1 | Read February 2027 | `2027-02` | 28 dates, last `2027-02-28` | none | API |
| AC1-B3 | AC1 | December has 31 dates and stops at the year end | Boundary | As AC1-H1 | Read December 2026 | `2026-12` | 31 dates, last `2026-12-31` | none | API |
| AC1-N1 to AC1-N6 | AC1 | A month that is not `YYYY-MM` is refused | Negative | As AC1-H1 | Read with each value, and with none | `2026-13`, `2026-00`, `2026-1`, `26-10`, `abc`, omitted | 422 | none | API |
| AC1-N7 | AC1 | An unknown venue returns 404 | Negative | No venue with that id | Read | random id | 404 "Venue not found" | none | API |
| AC1-N8 to AC1-N10 | AC1 | Other roles are refused (A2) | Negative | As AC1-H1 | Read as `event_organiser`; as `attendee`; as `technical_support` | October 2026 | 403 "Insufficient permissions" for each | No calendar returned | API |
| AC1-X1 | AC1 | A request without a token is refused | Cross-cutting | As AC1-H1 | Read with no `Authorization` | none | 401 "Authentication required" | none | API |
| AC1-X2 | AC1, AC2 | The response carries no private details (A3) | Cross-cutting | One block with a reason and detail, one approved booking with an event name and requester | Read as each allowed role | the month containing both | The body has only dates, slots and states; none of the reason, detail, event name, booking id, block id or user ids appears | none | API |
| AC2-H1 | AC2 | An approved booking shows as booked on its dates and slots only | Happy | Approved booking, 12 to 14 Oct, slots AM and PM | Read October 2026 | none | `booked` for AM and PM on 12, 13 and 14 Oct; NIGHT and every other date `open` | none | API |
| AC2-B1, AC2-B2 | AC2 | The first and last date of a booking are included, the days around it are not | Boundary | As AC2-H1 | Read | 11 and 15 Oct, and 12 and 14 Oct | 11 and 15 `open`; 12 and 14 `booked` | none | API |
| AC2-H2 | AC2 | An active block shows as blocked on its dates and slots | Happy | Active block, 20 to 21 Oct, slot NIGHT | Read October 2026 | none | `blocked` for NIGHT on 20 and 21 Oct only | none | API |
| AC2-P1 | AC2 | A lifted block does not show | Partition | A block with status `lifted` | Read | none | Its slots are `open` | none | API |
| AC2-P2 to AC2-P4 | AC2 | Pending, rejected and cancelled bookings do not show as booked (A4) | Partition | One booking of each status over the same dates | Read | none | All `open` | none | API |
| AC2-P5 | AC2 | A multi-day, multi-slot booking covers every slot of every day | Partition | Approved booking, 3 days, AM and PM | Read | none | Six `booked` cells and the rest `open` | none | API |
| AC2-X1 | AC2 | A booking that spans two months shows in both; one outside the month does not | Cross-cutting | Approved booking 30 Oct to 2 Nov; another in December | Read October, then November | none | `booked` on 30 and 31 Oct; on 1 and 2 Nov; the December one in neither | none | API |
| AC2-X2 | AC2 | Reading changes nothing | Cross-cutting | A venue with blocks and bookings | Read twice; compare stored blocks, bookings and the venue | none | Identical before and after | No create, update or delete | API |
| AC2-X3 | AC2 | The stores return only the approved bookings of that venue that touch the month | Cross-cutting | Memory store; mocked PostgREST for Supabase | `list_approved_for_venue(venue, start, end)` | bookings of two venues and mixed statuses | Only approved, that venue, overlapping the window; the Supabase query filters `venue_id`, `status=eq.approved` and the date overlap | none | Unit |
| AC3-H1 | AC3 | A slot that is both booked and blocked shows as blocked | Happy | Booking and block on the same date and slot | Read | none | `blocked` | none | API |
| AC3-H2 | AC3 | Cancelling an approved booking makes its slots open again | Happy | Approved booking, then cancelled (SCRUM-61) | Read before and after | none | `booked`, then `open` | none | API |
| AC3-X1 | AC3, AC4 | The calendar and venue search agree | Cross-cutting | Venues with blocks, approved bookings, non-operating slots and a catalogue-blocked venue | For each date and slot, read the calendar and run venue search for that date and slot | a month of dates, all three slots | The calendar says `open` exactly when the venue appears in the search | none | API |
| AC4-P1 | AC4 | A slot the venue does not operate shows as not offered | Partition | Venue operating AM and PM only | Read | none | NIGHT `not_offered` on every date | none | API |
| AC4-P2 | AC4 | A venue blocked in the catalogue shows its operating slots as unavailable | Partition | Venue status `blocked`, operating AM and PM | Read | none | AM and PM `unavailable`; NIGHT `not_offered` | none | API |
| AC4-P3 | AC4 | An active block on a slot the venue does not operate still shows (A6) | Partition | Venue operating AM; block on NIGHT | Read | none | NIGHT `blocked` | none | API |
| AC1-U1 | AC1, AC3 | The table lists each date with its three slots, each state in words | Happy | A calendar with open, booked, blocked, unavailable and not offered cells | Render | none | One row per date; the state is written out, not colour only; the table has a caption naming the venue and month | none | Component |
| AC1-U2 | AC1 | Month links go to the previous and next month, across year ends and at the calendar's ends | Boundary | December 2026 and January 2027; `0001-01`; `9999-12` | Render | none | December's next link is `2027-01`; January's previous is `2026-12`; there is no Previous link at `0001-01` and no Next link at `9999-12` | none | Component |
| AC1-U3 | AC1 | An unknown venue says so | Negative | The API answers 404 | Render the page | unknown id | "Venue not found"; no calendar | none | Component |
| AC1-U4 | AC1 | A failed load shows an error, never an all-open calendar | Negative | The API fails | Render the page | none | An alert; no cells | none | Component |
| AC1-U5 | AC1 | Only coordinators, venue staff and safety officers can open the page | Cross-cutting | Each role | Open the page | each role | Allowed roles see it; others go to `/unauthorised` | Calendar not fetched for others | Component |
| AC1-U6 | AC1 | Each venue search result links to its availability | Happy | Search results shown | Render a result card | none | A "View availability" link to the page for that venue | none | Component |
| AC1-N11 | AC1 | Year 0000 is refused with 422, as a month that is not a calendar month (review comment on PR #68) | Negative | As AC1-H1 | Read with `0000-01` | `0000-01` | 422 | none | API |
| AC1-B4, AC1-B5 | AC1 | The first and last month the calendar can show both work (review comment on PR #68) | Boundary | As AC1-H1 | Read `0001-01` and `9999-12` | `0001-01`, `9999-12` | 200 with 31 dates each | none | API |
| AC1-U7 | AC1 | A month the API would refuse (year 0000) falls back to the current month and never reports "Venue not found" (review comment) | Negative | A venue exists | Open the page with `month=0000-01` | `0000-01` | The current month's calendar is requested and shown | No "Venue not found" | Component |
| AC1-U8 | AC1 | The search-result link carries the month of the date that was searched (review comment) | Happy | Search results shown for a date | Render a result card | searched date 2026-11-14; no date; an invalid date | link has `month=2026-11`; no `month` without a date; none for an invalid date | none | Component |
| AC1-E1 | AC1, AC2 | In a browser a coordinator finds a venue, opens its availability, sees a booked and a blocked slot, and moves to the next month | Happy | Venue with one approved booking and one block; coordinator signed in | Search, click View availability, read the cells, click Next month | none | Booked and Blocked cells visible; the next month loads | none | E2E |

### Latest execution record

Results from 19 October 2026 on Kennedy's machine against branch `feat/scrum-31-venue-availability-view` (docs commit `8cd4a32` plus the uncommitted backend work), by Claude Code. Environment: Python 3.13, in-memory stores, authService overridden, no network. Real services were **not** involved.

| ID | Automation status | Actual result | Execution status | Remarks and evidence |
| --- | --- | --- | --- | --- |
| AC1-H1, AC1-P1, AC1-P2, AC1-B1 to AC1-B3, AC1-N1 to AC1-N10, AC1-X1, AC1-X2 | Red then Green | Red: 404 on the missing route (and one body-shape assertion). Green: as expected | Pass (local) | `tests/test_venue_calendar.py` |
| AC2-H1, AC2-B1, AC2-B2, AC2-H2, AC2-P1 to AC2-P5, AC2-X1, AC2-X2 | Red then Green | As expected. AC2-X2 passed vacuously before the route existed, so it was changed to assert a 200 first | Pass (local) | `tests/test_venue_calendar.py`. SCRUM-69's conversion (27 Oct) moved the calendar to times and relabelled every test there with SCRUM-69's case IDs, so no SCRUM-31 label was added (one label per test). This row's scenarios are now proven by the tests labelled AC2-H1 `test_approved_booking_shows_as_booked`, AC2-H2 `test_active_block_shows_as_blocked`, AC2-P1 `test_lifted_block_does_not_show`, AC2-P5 `test_multi_day_booking_applies_its_times_to_every_date` and AC2-X1 `test_booking_spanning_two_months_shows_in_both` (SCRUM-69's IDs, same sources and precedence) |
| AC3-H1, AC3-H2, AC3-X1 | Red then Green | As expected | Pass (local) | `test_blocked_wins_over_booked`, `test_cancelled_booking_frees_its_slots`, `test_calendar_agrees_with_venue_search` (4 venues, 10 dates, 3 slots each). SCRUM-69's conversion renamed and relabelled these (SCRUM-69's IDs; no SCRUM-31 label added, one label per test): AC3-H1 → `test_blocked_wins_over_booked_and_splits_the_booking` (labelled AC2-H3), AC3-H2 → `test_cancelled_booking_frees_its_time` (labelled AC2-H5), AC3-X1 → `test_calendar_agrees_with_venue_search_at_every_step` (labelled AC6-X1, now at every 15-minute step) |
| AC4-P1 to AC4-P3 | Red then Green | As expected | Pass (local) | `tests/test_venue_calendar.py`. SCRUM-69's conversion (27 Oct) changed this row group: AC4-P2's catalogue part is proven by `test_catalogue_status_sets_the_unavailable_flag` (labelled AC3-P1/AC3-P2, SCRUM-69's IDs); AC4-P3's nearest current proof is `test_block_on_an_unavailable_venue_still_shows` (labelled AC3-P3: a block on a catalogue-blocked venue still shows — the slot-model case, a block on a slot the venue does not operate, cannot exist now that every venue runs 07:00–24:00). AC4-P1's `not_offered` state was dropped by SCRUM-69 (its AC5: PO decision, 20 Oct — every venue operates 07:00 to 24:00), and `test_response_has_no_slot_vocabulary` (labelled AC5-X1) asserts the word never appears, so the slot-model row has no current equivalent |
| AC2-X3 | Red then Green | Red: the store method did not exist. Green: as expected. A window-edge case was added after reviewing the plan | Pass (local, mocked Data API for Supabase) | `tests/test_booking_store_calendar.py`, `tests/test_supabase_booking_repository.py` |
| AC1-H1, AC1-P1, AC1-B1, AC1-B2, AC1-N1, AC1-N6 to AC1-N10, AC1-X1, AC1-X2, AC2-H1, AC2-H2, AC2-P2, AC3-H2, AC3-X1, AC4 | Written after the code | 34 of 34 checks passed, 1 skipped (script output reported by Kennedy, not captured here) | Pass (real stack, 19 October 2026); AC1-P2 **Not executed** live | `scrum31_live_check.py` against the real authService, eventRequestService and venueService with the shared development database. See "Real-stack check" below |
| AC1-N11, AC1-B4, AC1-B5 (review fixes) | Guards written before a refactor (passed before and after) | As expected | Pass (local) | `tests/test_venue_calendar.py`. They pin the behaviour while the month pattern was simplified; removing the year-0000 check makes AC1-N11 fail |
| AC1-U2 (ends), AC1-U7, AC1-U8 (review fixes) | Red then Green | Red: the page requested year 0000, the links at the calendar's ends were wrong, the search link ignored the date. Green: as expected | Pass (local) | `frontend/__tests__/venue-availability.test.tsx` (now 20 test cases) |
| AC1-U1 to AC1-U6 | Red then Green | Red: the new modules did not exist (import error). Green: as expected | Pass (local) | `frontend/__tests__/venue-availability.test.tsx` (10 test cases): the table, month links across year ends, the venue picker, unknown venue, failed loads, the role gate and its refusal, and the search-result link |
| AC1-E1, AC1-U5 (browser) | Written after the code (not Red first) | As expected, after fixing two faults in my own test (a "4 Mar" locator that also matched 14 and 24 Mar, then a word boundary that failed on the row's joined text) | Pass (local, Chrome, mock venue API) | `frontend/e2e/venue-availability.spec.ts`: from a search result a coordinator opens the calendar, sees Booked and Blocked in words, no block reason, and moves to the next month; an organiser is sent to `/unauthorised` |

## Latest verification

| Check | Command (run from `backend/venueService`) | Result |
| --- | --- | --- |
| Lint | `ruff check .` | All checks passed |
| New backend tests | `pytest tests/test_venue_calendar.py tests/test_booking_store_calendar.py -q` | 41 passed (plus 2 new Supabase-store tests in `tests/test_supabase_booking_repository.py`) |
| Whole venueService suite | `pytest -q` (the CI command; also `python -m pytest`) | 496 passed, 10 skipped (the untracked live-database file) |

**Frontend (19 October 2026, `frontend/`, Kennedy's machine).**

| Check | Command | Result |
| --- | --- | --- |
| Lint | `npm run lint` | Clean |
| Type check | `npm run typecheck` | Clean |
| Unit and component tests | `npm test` | 378 passed (35 files); 10 are new |
| Browser tests, full suite | `npx playwright test` through a temporary config selecting the installed Google Chrome (`channel: "chrome"`), as for SCRUM-12 and SCRUM-61 | 43 passed, including the 2 new |

Fault checks on the frontend: mislabelling blocked cells as Booked, a mock that ignores blocks, and letting organisers into the page each made a browser test fail.

The browser tests run against the **mock** venue API in `e2e/support/venue-api.mjs`, extended with a copy of the calendar rules. They prove the screen and its wiring, not the real service. The real-stack check below covers the API and, for the Blocked case, the screen.

**Real-stack check, 19 October 2026.** Run by Kennedy on their machine against branch `feat/scrum-31-venue-availability-view` (commit `3b32d23`) through Docker Compose: the real authService (Supabase Auth), eventRequestService and venueService (Supabase store), and the shared development database. The script signs in as the two coordinator test accounts, venue staff, an organiser, an attendee and technical support, and uses the one venue on shared development. It prints status codes only. Kennedy reported **34 passed, 0 failed, 1 skipped**. Per-line output was pasted; it is summarised here.

| Checks (case IDs) | What was done | Expected | Actual |
| --- | --- | --- | --- |
| AC1-H1, AC1-P1 | The coordinator and venue staff read October 2026 | 200; 31 dates; slots in AM, PM, NIGHT order | as expected |
| AC1-P2 | The safety officer reads the calendar | 200 | **Skipped**: there is no `safety_officer@example.com` account on shared development. Covered only by the local tests |
| AC1-N8 to AC1-N10, AC1-X1 | Organiser, attendee, technical support; no token | 403, 403, 403; 401 | as expected |
| AC1-B1, AC1-B2 | February 2028 and February 2027 | 29 and 28 dates | as expected |
| AC1-N1, AC1-N6, AC1-N7 | Month 13; month missing; unknown venue | 422; 422; 404 | as expected |
| AC1-X2 | The response keys; the 3 real blocks' ids and detail text | only `venue_id`, `month`, `days`; no block id or detail text in September or October | as expected |
| AC2-H2, AC4 | September and October 2026, which contain the venue's real blocks | The calendar matches an independent calculation, blocks included | as expected |
| AC2-P2 | A pending request for 10 Mar 2031, PM | The slot stays open | as expected |
| AC2-H1 | Venue staff approved a request for 4 and 5 Mar 2031, AM | Both AM cells booked; the days around and the other slots open; the whole month matches an independent calculation | as expected |
| AC3-X1 | Venue search for the booked and the open day | The booked slot omits the venue; the open day offers it | as expected |
| AC3-H2 | The coordinator cancelled the approved booking | The slots are open again | as expected |

**Database confirmation after the run (read-only, service role).** The two requests created were both `cancelled` (the approved one keeps its venue staff decider; the pending one has none) and `cancelled_by` is the assigned coordinator. No `pending` or `approved` rows existed anywhere, and the venue still had exactly its 3 existing blocks, so none were created. The 2 cancelled rows remain on shared development (no DELETE grant); they hold no slot.

**The screen against the real stack, 19 October 2026.** Kennedy signed in as `event_coordinator1@example.com` on the same real stack, opened the availability page for the shared development venue and shared a screenshot of October 2026. It shows 4 and 5 October as Blocked for AM and PM, Night available on those days, every other date Available, Previous and Next month links, and no block reason anywhere. That matches the venue's existing block in the database (AC1-U1, AC1-U6 area and AC1-X2 against real data). The screenshot is not stored in the repository.

Not covered live: the safety officer role, clicking through from a venue search result against the real service, the Not offered, Booked and Unavailable cells on screen, and the failure paths (venue service down). Those are covered only by the local tests.

**After the PR #68 review comments (20 October 2026).** `dev` was merged into the branch (`f02a956`, clean, 27 commits from other people) and everything re-run on the merged tree.

| Check | Command | Result |
| --- | --- | --- |
| Backend lint and tests | `ruff check .` and `pytest -q` from `backend/venueService` | clean; 499 passed, 10 skipped |
| Frontend | `npm run lint`, `npm run typecheck`, `npm test` | clean, clean, 408 passed (39 files) |
| Browser tests, full suite | `npx playwright test` through a temporary config selecting the installed Google Chrome | 45 passed, including the 2 for this story; the journey now goes from a search with a date straight to that month |

Six more faults were injected for the review fixes and each made a test fail: no refusal of year 0000 on the API, the frontend accepting year 0000, Previous at year 1 going to year 0, Next at 9999-12 going to year 10000, the searched date not validated, and the search link ignoring the month.

**Mutation check (manual, 19 October 2026).** Eleven one-line faults were injected one at a time and each made at least one test fail: booked winning over blocked, pending bookings counted as booked, the month's last date dropped, non-operating slots shown as open, a catalogue-blocked venue shown as open, lifted blocks counted, any signed-in user allowed, the window's start and end edges made exclusive, slots in the wrong order, and the Supabase query ignoring the status. Two attempts at the "any signed-in user" fault first broke an import and were discarded; the third, using the real dependency, was killed by the three role-refusal tests.

### Changes after review

PR #68 received review comments on 20 October 2026. Accepted and built, tests first: the month check on the page and the month links at the calendar's ends (AC1-U2, AC1-U7, AC1-N11, AC1-B4, AC1-B5), the search-result link keeping the searched month (AC1-U8), a simpler month pattern on the API (the year-0000 refusal is now an explicit check, AC1-N11), and removal of an unused sort in the approved-bookings read. Not changed: fetching every block of a venue and filtering in memory, because blocks per venue are few, `build_calendar` already ignores lifted and non-overlapping ones, and a windowed block query would add a Supabase method for no practical gain; recorded as a possible follow-up. The comment on tentative holds is a request to confirm assumption A1 with the Product Owner, which is still open.

## Disclosures

- This document, its assumptions and the cases were drafted by Claude Code on 19 October 2026 and **approved by the story owner the same day**, before any code was written.
- The Product Owner agreed on 19 October 2026 to restore SCRUM-31's original wording and deliver it on the slot model. Assumption A1 (tentative holds not applicable) and A2 (the roles) are mine and still need confirming.
- The points estimate (1) predates this design. The work is a new endpoint, a store method, a page and tests.

## Hotfix 2 H12: the calendar follows each venue's operating hours, 3 November 2026

H12 in `release_1_hotfixes_testcases.md` gave each venue its own daily operating hours (migration 0092, PR #130). This story's AC4 is Jira's rewritten AC4 of 1 November. The IDs carry the `H12` prefix, as in the tracking sheet, because this document already uses AC4-P1 to AC4-P3. The catalogue, search and suitability cases of H12 are in `scrum_30_testcases.md`.

Layer: **API** = `backend/venueService/tests/test_venue_operating_hours.py` (FastAPI routes, in-memory stores, Coordinator session).

| ID | AC | Test scenario | Technique | Pre-conditions | Test steps | Test data | Expected result | Forbidden side effects | Layer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| H12 AC4-H2 | AC4 | The calendar shows free time only inside the venue's hours | Happy | Venue open 09:00 to 18:00, nothing booked | Read the month as a Coordinator | the test day | Free time is 09:00 to 18:00 only | Nothing outside the hours is free | API |
| H12 AC4-P3 | AC4 | Bookings and blocks are still listed, and free time is what is left of the hours | Partition | Venue open 09:00 to 18:00; approved booking 10:00 to 12:00; block 07:00 to 08:00 | Read the month | the test day | Free 09:00 to 10:00 and 12:00 to 18:00; the block is still listed | — | API |
| H12 AC4-X1 | AC4 | For a venue with short hours, the calendar and search agree at every 15-minute step | Cross-cutting | Venue with short hours | At each 15-minute step, search and read the calendar | every step of the day | Search offers the venue exactly where the calendar shows it free | — | API |
| H12 AC4-X2 | AC4 | On a day with short hours, the calendar's ranges are ordered, do not overlap and stay inside the hours | Cross-cutting | Venue open 10:00 to 17:00 | Read the month | the test day | Every range lies within 10:00 to 17:00; no overlaps | — | API |

| ID | Automation status | Actual result | Execution status | Remarks and evidence |
| --- | --- | --- | --- | --- |
| H12 AC4-H2, AC4-P3, AC4-X1, AC4-X2 | Automated, written test first | As expected | Pass | Hotfix 2 execution record, 3 Nov 2026 (Kennedy, Claude): venueService 854 passed, 10 skipped. Re-run on 5 Nov 2026 by Claude for Yang Xue at `fdc989f`: `test_venue_operating_hours.py` 38 passed, venueService 858 passed |

