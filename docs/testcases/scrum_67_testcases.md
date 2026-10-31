# SCRUM-67 Test Cases: Warn the Coordinator About a Likely Venue Conflict on Submit

Last reviewed: 30 October 2026

Status: **scope approved by the story owner (Kennedy) on 30 October 2026 (option A below).** Built on the replacement request of SCRUM-63 (PR #115).

## Story

| Field | Value |
| --- | --- |
| Jira key | SCRUM-67 |
| Title | Warn the coordinator about a likely venue conflict on submit |
| Sprint | Sprint 4 (22 October to 5 November 2026) |
| Points | 2 |
| User story | As an Event Coordinator, I want to be warned when a venue booking request I'm submitting clashes with an existing approved booking, so that I can pick another time before Venue Staff refuse it. |
| Source | Raised by the Product Owner as an optional follow-up to SCRUM-20 (conflicts are refused when Venue Staff approve). |

## Story contract

| ID | Jira criterion | Review outcome | Reason |
| --- | --- | --- | --- |
| AC1 | When a coordinator submits a request that clashes with an approved booking (including setup/turnaround), they see a warning naming the clash. | **Clarify** | A clash is the rule SCRUM-20 uses at approval (`find_conflicts`: a shared date and overlapping times, each padded by the venue's setup and turnaround; only approved bookings). "Naming the clash" is read as the clashing booking's dates and times; never the other event's name, ids or users. "Submits" is read as the two calls that store a request: `POST /booking-requests` and the SCRUM-63 replacement. |
| AC2 | The request can still be submitted; approval remains the hard check. | **Keep** | The warning is advice. The request is stored as pending whatever the answer, and a failed lookup never fails it. |

### Included and excluded behaviour

| | Behaviour | Jira |
| --- | --- | --- |
| Included | A `conflicts` list (dates and times) in the response of `POST /booking-requests` and `POST /booking-requests/{id}/replacement` | SCRUM-67 |
| Included | The warning, in words, on the coordinator's event page after a replacement is requested | SCRUM-67 |
| Excluded | A general "Request a venue" form. The frontend has none today (SCRUM-32 is API-only), so the warning has one screen to appear on: the replacement form. A full form is its own story, for the Product Owner | not planned |
| Excluded | Warning before submitting, or on a later page load. The list is returned once, in the response | not planned |
| Excluded | The conflict check at approval (SCRUM-20): unchanged | SCRUM-20 |
| Excluded | Venue blocks as a warning. They already refuse at approval (`active_block`) and show on the availability calendar | SCRUM-23, SCRUM-69 |

### Actors and permissions

Unchanged: the event's current Event Coordinator (checked on every call). The warning reveals only that an approved booking holds the time, which the availability calendar already shows to coordinators.

### State and persistence

Read-only on top of an existing write. Nothing new is stored. The list is computed after the request is stored, so a lookup failure returns an empty list.

### Assumptions

| ID | Assumption | Used by |
| --- | --- | --- |
| A1 | **Option A (30 October):** API-level warning on both calls; the only screen that submits is the replacement form, so that is where it shows. | AC1 |
| A2 | The warning is advisory and can be stale (another booking may be approved a moment later). Approval is the authority. | AC2 |
| A3 | The warning stays on screen after the page refreshes because the form component stays mounted and shows the status line in its place. It is not stored; a reload clears it. | AC1 |

## Test cases (specification)

Fixed data: venue V (setup 30, turnaround 45 where stated), an approved booking 09:00 to 12:00 on 2030-01-10 for another event.

| ID | AC | Test scenario | Technique | Pre-conditions | Test steps | Test data | Expected result | Forbidden side effects | Layer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AC1-H1 | AC1 | A request that overlaps an approved booking is stored and lists the clash | Happy | As above | `POST /booking-requests` 10:00 to 11:00 | 600 to 660 | 201, `status` pending, `conflicts` = the booking's dates and times (540 to 720) | none | API |
| AC1-H2 | AC1 | A replacement that overlaps an approved booking at the new venue lists the clash | Happy | A flagged booking; an approved booking at the new venue 10:00 to 11:00 | `POST /booking-requests/{id}/replacement` | new venue | 201, pending, `conflicts` = 600 to 660 | none | API |
| AC1-P1 | AC1 | A free time lists no clash | Partition | As above | Request 15:00 to 16:00 | 900 to 960 | 201, `conflicts` empty | none | API |
| AC1-P2 | AC1 | Pending, rejected and cancelled bookings do not count | Partition | One of each overlapping | Request 10:00 to 11:00 | 600 to 660 | `conflicts` empty | none | API |
| AC1-P3 | AC1 | Another venue's booking and another date do not count | Partition | Approved booking at another venue; approved booking on 12 Jan at this venue | Request 10:00 to 11:00 | 600 to 660 | `conflicts` empty | none | API |
| AC1-P4 | AC1 | A multi-day approved booking clashes on any shared date | Partition | Approved 9 to 11 Jan, 09:00 to 12:00 | Request 10 Jan 10:00 to 11:00 | 600 to 660 | `conflicts` = 9 to 11 Jan, 540 to 720 | none | API |
| AC1-P5 | AC1 | A replacement with no overlap lists none | Partition | A flagged booking; nothing at the new venue | Request a replacement | new venue | 201, `conflicts` empty | none | API |
| AC1-B1 to AC1-B3 | AC1 | Setup and turnaround count: with setup 30 and turnaround 45, an approved 09:00 to 12:00 booking holds the venue until 12:45 and the next start needs 30 minutes of setup | Boundary | V with setup 30, turnaround 45 | Request 60 minutes starting 13:00, 13:15, 13:30 | 780, 795, 810 | 13:00 clashes; 13:15 and 13:30 do not | none | API |
| AC1-X1 | AC1 | The warning carries dates and times only | Cross-cutting | The approved booking has an event name, requester and event id | Read the response | secrets | None of them appear; the clash has exactly four keys | Any extra field | API |
| AC1-N1 | AC1 | A failed lookup does not fail the request | Negative | `list_approved_for_venue` raises a store error | Submit | none | 201, stored, `conflicts` empty | A 500 | API |
| AC2-H1 | AC2 | A clash never blocks the request and changes nothing else | Happy | As AC1-H1 | Submit | 600 to 660 | 201; the clashing booking is unchanged | Any change to it | API |
| AC2-X1 | AC2 | Approval stays the hard check | Cross-cutting | The stored clashing request | Venue Staff approve it | none | 409 `booking_conflict`; the request stays pending | An approval | API |
| AC1-U1 | AC1 | The warning names each clash in words | Happy | Two clashes | Render the warning | two clashes | "Second Hall already has an approved booking that overlaps this request"; "10 Mar 2030, 09:00–12:00"; "11 Mar 2030 – 12 Mar 2030, 14:00–15:00"; mentions setup and turnaround and that the request has still been submitted | Colour-only state | UI |
| AC1-U2 | AC1 | The action hands the clashes to the form | Happy | A 201 with `conflicts` | Call the action | one clash | Returns `{ conflicts }` and refreshes the page | none | UI |
| AC1-U3 | AC1 | No clash shows no warning | Partition | None | Render | `[]` | Nothing rendered | An empty box | UI |
| AC1-U4 | AC1 | A missing, empty or malformed list gives no warning | Partition | A 201 with each | Call the action | absent, empty, malformed | Returns `{}` | A crash | UI |
| AC1-E1 | AC1, AC2 | The journey: request a replacement that clashes | Happy | Mock APIs; a flagged booking; an approved booking at the new venue 10:00 to 11:00 for another event | Choose the venue, request | fixture | "Replacement requested at ... (Pending)" and the warning with "10 Mar 2030, 10:00–11:00"; the other event's name never appears | The other event's name | E2E (mocked APIs) |

## Latest execution record

| ID | Automation status | Actual result | Execution status | Build or commit | Executed by and date | Remarks and evidence |
| --- | --- | --- | --- | --- | --- | --- |
| AC1-H1, H2, P1 to P5, B1 to B3, X1, N1; AC2-H1, X1 (API) | Green | `backend/venueService`: `pytest -q` 705 passed, 10 skipped; `ruff check .` clean (13 new in `test_booking_clash_warning.py`, 2 added to `test_booking_replacement.py`). Red before: 11 of 13 failed on the missing `conflicts` field (the other 2 describe behaviour that already held) | Pass | branch `feat/scrum-67-clash-warning` on `feat/scrum-63-replacement-request` (`adfafe5`), local venv | Claude for Kennedy, 30 Oct 2026 | Seven one-line faults in the response builder: five caught. One (status forced to approved) is equivalent, because the store already returns only approved bookings and `find_conflicts` filters again; one was a no-op mutant I wrote wrongly. A fault in each of the two routes' responses is caught. One test stub store needed `list_approved_for_venue`, which the real interface already has |
| AC1-U1 to U4 (UI and action) | Green | `frontend`: `npx vitest run` 69 files, 585 tests passed (35 in `venue-replacement.test.tsx`); lint and typecheck clean. Red before: the file failed on the missing component | Pass | as above, local | Claude for Kennedy, 30 Oct 2026 | Six faults in the component, action and form: five caught by vitest; the sixth (dropping the warning from the status view) is caught by the browser test. Whole suite: 54 Playwright tests pass; `eventRequestService` and `venueService` ruff clean with ruff 0.17.3 |
| AC1-E1 (E2E, mocked APIs) | Green | Playwright, Chrome channel: `e2e/venue-replacement.spec.ts` 3 passed | Pass | as above | Claude for Kennedy, 30 Oct 2026 | The browser build found a real fault the unit tests could not: the warning, used in a client component, imported a helper from a module that reaches server-only code. The date helpers moved to `lib/booking-dates.ts`. The mock mirrors the rules; the real service is covered by the API tests |
| Real stack, shared development, PR CI | Planned | Not run | Not executed | none | none | Nothing to apply to the database. Part of the replacement flow, so it follows PR #115 |
