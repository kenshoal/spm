# SCRUM-12 Test Cases: Check Venue Suitability

Last reviewed: 5 October 2026

Status: **the AC review below was approved as proposed by the story owner (Kennedy) on 4 October 2026.** The test-design review is still pending. The implementation and tests were written before this document existed, so the sequence the standard asks for (approve the ACs, write the cases, watch them fail, implement) was not followed; see [Disclosures](#disclosures).

## Story

| Field | Value |
| --- | --- |
| issue tracker key | SCRUM-12 |
| Title | Check Venue Suitability |
| Sprint | Sprint 2 |
| User story | As an Event Coordinator, I want the system to indicate whether a venue appears suitable for an event, so that I avoid proposing venues that cannot meet the event's requirements. |

## Story contract

The ACs below are the five live issue tracker criteria (read on 3 October 2026), rewritten as Given / When / Then. Review outcomes use the vocabulary in `docs/standards/testing.md` §1. Approved as proposed by Kennedy on 4 October 2026; the assumptions A1 to A5 below were presented with it and are not separately confirmed.

| ID | Criterion | Review outcome | Reason |
| --- | --- | --- | --- |
| AC1 | Given an event with expected attendance A and a venue with maximum capacity C, when A exceeds C, then the venue is flagged **not suitable** and the reason names A and C. | **Keep** | Actor, condition and result are clear. "Exceeds" makes A equal to C suitable, which fixes the boundary. |
| AC2 | Given an event that requires a facility the venue does not provide, when suitability is checked, then the venue is flagged **not suitable** and the reason names the missing facility. | **Keep** | It overlaps AC3's "required facilities", but it states the facility rule as its own scenario. Merge into AC3 if the reviewer prefers. |
| AC3 | Given an event's requirements, when suitability is checked, then capacity, supported layout, accessibility, required facilities and operating slot are each compared with the venue's recorded attributes, and every attribute not met is listed. | **Clarify** | Two wording problems: (1) "operating hours" is modelled as the venue's operating **slots** (AM / PM / NIGHT), the only operating-time attribute venueService stores; (2) "the event's requirements" are supplied by the caller in the request body, because the event record only holds free text, so there is nothing structured to read. It also bundles five checks (a Split candidate); it is kept as one AC with one case per attribute. |
| AC4 | Given a check result, then it states **suitable** or **not suitable**, and each mismatch carries the attribute and a reason. | **Keep** | Observable from the response body. |
| AC5 | Given any suitability check, then the venue is not booked, held or modified. | **Keep** | Testable as "no write path exists and the venue record is unchanged afterwards". |

Expected change to scope: none. Expected change to testing effort: one case per enumerated layout and slot value, plus boundary and negative cases.

### Included and excluded behaviour

| | Behaviour | issue tracker |
| --- | --- | --- |
| Included | `POST /venues/{venue_id}/suitability`: an advisory comparison of caller-supplied requirements against one venue's recorded attributes | SCRUM-12 |
| Excluded | Whether the venue is free on a date (blocks, bookings) | SCRUM-31, SCRUM-23 |
| Excluded | Location. It is not in the ACs and an event has no structured location to compare; venue search already filters by location. Confirmed by Kennedy on 5 October 2026 | none |
| Excluded | Submitting, deciding or holding a booking | SCRUM-32, SCRUM-15, SCRUM-18 |
| Excluded | Reading the event's attendance or dates from eventRequestService | Not in the ACs (see Q1) |
| Included (added 5 October 2026) | A per-result "Check suitability" form on the existing venue search results page, showing the verdict and each mismatch (see Q3) | SCRUM-12 |

### Actors and relationship permissions

- Story actor: Event Coordinator.
- The endpoint accepts any authenticated user (assumption A3). No relationship to an event is checked, because the request body carries the requirements and no event is read.

### State transitions, persistence and atomicity

- **State transitions:** none. The check is read-only.
- **Persistence:** none. One venue is read through the venue store (in-memory or Supabase); nothing is written.
- **Atomicity:** not applicable.

### Assumptions and open questions

| ID | Assumption or question | Used by |
| --- | --- | --- |
| A1 | `expected_attendance` must be a positive integer. This is not stated in the ACs; it matches `eventRequestService`, which also requires attendance above zero. | AC1-N1, AC1-N2 |
| A2 | Facility and accessibility names compare case-insensitively, as venue search does. Surrounding whitespace is not trimmed. Not stated in the ACs. | AC2-P1, AC2-P2, AC3-P10, AC3-P11 |
| A3 | Any authenticated user may run the check, as with search and list. The ACs name no role restriction. | AC3-X2, AC3-X3 |
| A4 | One required slot per check. An event that needs several slots needs several checks. | AC3-P6 to AC3-P8 |
| A5 | A venue whose status is `blocked` is still compared on its attributes. Suitability is not availability. | none |
| Q1 | Should the check read attendance from the event itself (by `event_request_id`) instead of the request body? | none |
| Q2 | Should a blocked venue be reported as not suitable? | none |
| Q3 | The search results contain only venues that already meet every search filter, so a check pre-filled from those filters will say Suitable. The check is useful when the coordinator changes a requirement (for example a larger attendance) or enters requirements the search did not filter on. Is that the intended use? | AC4-H6 |

## Test-case matrix

A row with an ID range is one parametrized test whose cases carry those IDs.

### Specification

| ID | AC | Test scenario | Technique | Pre-conditions | Test steps | Test data | Expected result | Forbidden side effects | Layer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AC1-B1 | AC1 | Attendance just below capacity is not flagged | Boundary | Venue, capacity 100 | Check suitability | attendance 99 | `suitable` true, no mismatches | none | Unit |
| AC1-B2 | AC1 | Attendance exactly at capacity is not flagged ("exceeds" is strict) | Boundary | Venue, capacity 100 | Check suitability | attendance 100 | `suitable` true, no mismatches | none | Unit |
| AC1-B3 | AC1 | Attendance just above capacity is flagged | Boundary | Venue, capacity 100 | Check suitability | attendance 101 | `suitable` false, one `capacity` mismatch | none | Unit |
| AC1-N1 | AC1 | Attendance of zero is rejected (A1) | Negative | Venue exists | POST suitability | attendance 0 | 422, error type `greater_than` on `body.expected_attendance` | Venue record unchanged | API |
| AC1-N2 | AC1 | A negative attendance is rejected (A1) | Negative | Venue exists | POST suitability | attendance -1 | 422, error type `greater_than` | Venue record unchanged | API |
| AC2-N1 | AC2 | A missing facility is flagged and only that facility is named | Negative | Venue provides Projector only | Check suitability | requires Projector and Stage | `suitable` false, one `facilities` mismatch naming Stage and not Projector | none | Unit |
| AC2-P1 | AC2 | A provided facility matches when the event's spelling is lower case (A2) | Partition | Venue provides "Projector" | Check suitability | requires "projector" | `suitable` true | none | Unit |
| AC2-P2 | AC2 | A provided facility matches when the event's spelling is upper case (A2) | Partition | Venue provides "projector" | Check suitability | requires "PROJECTOR" | `suitable` true | none | Unit |
| AC3-H1 | AC3 | A venue meeting all five kinds of requirement is suitable | Happy | Venue meets every requirement | Check suitability | attendance 100, theatre, PM, Projector and Microphone, Wheelchair ramp | `suitable` true, no mismatches | none | Unit |
| AC3-P1 to AC3-P5 | AC3 | Each layout the venue lacks is flagged (classroom, theatre, boardroom, banquet, exhibition) | Partition | Venue supports no layouts | Check suitability | one required layout per case | `suitable` false, one `layout` mismatch | none | Unit |
| AC3-P6 to AC3-P8 | AC3 | Each slot the venue does not operate is flagged (AM, PM, NIGHT) | Partition | Venue operates no slots | Check suitability | one required slot per case | `suitable` false, one `operating_slot` mismatch | none | Unit |
| AC3-P9 | AC3 | A missing accessibility feature is flagged | Partition | Venue has no accessibility features | Check suitability | requires Wheelchair ramp | `suitable` false, one `accessibility` mismatch | none | Unit |
| AC3-P10, AC3-P11 | AC3 | A provided accessibility feature matches in either letter case (A2) | Partition | Venue has the feature | Check suitability | "wheelchair ramp" against "Wheelchair ramp", and "WHEELCHAIR RAMP" against "wheelchair ramp" | `suitable` true | none | Unit |
| AC3-B1 | AC3 | With no optional requirements only attendance is compared | Boundary | Venue lists no facilities, accessibility, layouts or slots | Check suitability | attendance 1 only | `suitable` true, no mismatches | none | Unit |
| AC3-X1 | AC3 | Every unmet attribute is reported together, each once | Cross-cutting | Venue meets nothing requested | Check suitability | attendance 50 against capacity 10, plus layout, slot, facility and accessibility | five mismatches, one per attribute, no duplicates | none | Unit |
| AC3-N1 | AC3 | An unknown venue returns 404 | Negative | No venue with that id | POST suitability | id `does-not-exist` | 404, detail "Venue not found" | none | API |
| AC3-N2 | AC3 | An unknown layout value is rejected | Negative | Venue exists | POST suitability | `required_layout` "ballroom" | 422, error type `enum` on `body.required_layout` | Venue record unchanged | API |
| AC3-N3 | AC3 | An unknown slot value is rejected | Negative | Venue exists | POST suitability | `required_slot` "MORNING" | 422, error type `enum` on `body.required_slot` | Venue record unchanged | API |
| AC3-X2 | AC3 | A request without a valid bearer token is refused | Cross-cutting | Venue exists | POST suitability with no token; live check also with an invalid token | no `Authorization` header | 401, detail "Authentication required" | no comparison runs | API |
| AC3-X3 | AC3 | An Event Coordinator, who is not venue staff, may run the check (A3) | Cross-cutting | Venue exists; caller holds only `event_coordinator` | POST suitability | attendance 10 | 200, `suitable` true | none | API |
| AC4-H1 | AC4 | A suitable result states suitable and lists no mismatches | Happy | Venue meets the requirements | POST suitability | attendance 100, Projector | 200, `venue_id`, `suitable` true, `mismatches` empty | none | API |
| AC4-H2 | AC4 | A not-suitable result lists one reasoned mismatch per failed attribute | Happy | Venue capacity 20, no Stage | POST suitability | attendance 50, requires Stage | 200, `suitable` false, mismatches for `capacity` and `facilities`, each with a non-empty reason | none | API |
| AC4-H3 | AC4 | Each reason names the values that failed | Happy | Venue meets nothing requested | Check suitability | capacity 10 vs 50, boardroom, NIGHT, Stage, Hearing loop | reasons contain 10 and 50, "boardroom", "NIGHT", "Stage", "Hearing loop" | none | Unit |
| AC5-X1 | AC5 | A check, suitable or not, leaves the venue and the catalogue unchanged | Cross-cutting | Venue capacity 20 | Run one suitable and one unsuitable check | attendance 20, then 500 | Venue record and venue list identical before and after | no create, update or hold | API |
| AC1-N3 to AC1-N6 | AC1 | A non-positive or non-whole attendance is reported on the form and no request is sent (A1) | Negative | Search results are shown | Submit the check form | attendance "0", "abc", "2.5", "-1" | Message "Enter a whole number greater than zero.", no verdict shown | No request reaches venueService | Unit |
| AC3-H2 | AC3 | Only the requirements the coordinator filled in are sent, with lists split on commas | Happy | Search results are shown | Submit the check form | attendance 100, theatre, PM, "Projector, Stage", "Ramp access" | One `POST /venues/{id}/suitability` with `expected_attendance` 100, `required_layout` theatre, `required_slot` PM, two facilities, one accessibility feature | none | Unit |
| AC3-P12 | AC3 | A layout or slot outside the enums is dropped instead of causing a 422 (same rule as venue search) | Partition | Search results are shown | Submit the check form | layout "ballroom", slot "MIDNIGHT" | Request has no `required_layout` or `required_slot` | none | Unit |
| AC3-H3 | AC3 | The form is pre-filled from the search filters, so the check starts from what was searched for | Happy | Search with attendees 80, layout theatre, slot PM, facility Projector | Open a result's check form | none | Fields show 80, Theatre, PM, Projector | none | Unit |
| AC3-N4 | AC3 | A venue deleted or unknown after the search is reported, with no verdict | Negative | Venue returns 404 | Submit the check form | valid attendance | Message "This venue no longer exists." | No verdict shown | Unit |
| AC3-N5 | AC3 | An expired session goes to sign-in | Negative | venueService returns 401 | Submit the check form | valid attendance | Redirect to `/auth` | No verdict shown | Unit |
| AC3-N6 | AC3 | A service failure or network error is reported as "could not be checked", never as a verdict | Negative | venueService returns 500, or fetch throws | Submit the check form | valid attendance | Message "The suitability check could not be completed. Please try again." | No suitable or not-suitable verdict shown | Unit |
| AC4-H4 | AC4 | A not-suitable result shows the verdict in words and one line per mismatch with its attribute and reason | Happy | Result has two mismatches | Render the result | `suitable` false, capacity and facilities mismatches | Text "Not suitable", a list item per mismatch naming the attribute and its reason | Verdict is not conveyed by colour alone | Unit |
| AC4-H5 | AC4 | A suitable result shows the verdict and no mismatch list | Happy | Result has no mismatches | Render the result | `suitable` true | Text "Suitable", no list | none | Unit |
| AC4-H6 | AC4 | In a browser, a coordinator searches, checks a result against a larger attendance and sees Not suitable with the capacity reason, then a smaller attendance and sees Suitable | Happy | Venue capacity 120 seeded; signed in as `event_coordinator` | Search, open the check form on the result, submit 500, then 50 | attendance 500, then 50 | "Not suitable" with a capacity reason naming 500 and 120, then "Suitable" | none | E2E |
| AC5-X2 | AC5 | Running the check from the UI sends exactly one request, a POST to the suitability path, and the venue stays in the search results | Cross-cutting | Search results are shown | Submit the check form; reload the search | valid attendance | One `POST /venues/{id}/suitability`, no other call; the venue is still listed | No create, update or delete call | Unit, E2E |

### Latest execution record

Results are from the run on 4 October 2026 by Claude Code on Kennedy's machine, against commit `d1159c1` (the tip of `feat/venue-suitability-check` after merging `dev`, clean tracked tree). The mutation and live checks were run on 3 October 2026 against the same `app/suitability.py`, which is unchanged since commit `dfc8b17`.

| ID | Automation status | Actual result | Execution status | Build or commit | Remarks and evidence |
| --- | --- | --- | --- | --- | --- |
| AC1-B1, AC1-B2, AC1-B3 | Green (written after the code) | As expected | Pass | `d1159c1` | `tests/test_suitability.py::test_capacity_is_exceeded_only_above_the_maximum` |
| AC1-N1, AC1-N2 | Green | As expected | Pass | `d1159c1` | `tests/test_venues_suitability.py::test_non_positive_attendance_is_rejected` |
| AC2-N1 | Green | As expected | Pass | `d1159c1` | `test_only_the_missing_facility_is_named` |
| AC2-P1, AC2-P2 | Green | As expected | Pass | `d1159c1` | `test_facility_match_ignores_letter_case`; added after the mutation check showed the first version missed M2 |
| AC3-H1 | Green | As expected | Pass | `d1159c1` | `test_venue_meeting_every_requirement_is_suitable` |
| AC3-P1 to AC3-P5 | Green | As expected | Pass | `d1159c1` | `test_unsupported_layout_is_flagged` |
| AC3-P6 to AC3-P8 | Green | As expected | Pass | `d1159c1` | `test_slot_outside_operating_slots_is_flagged` |
| AC3-P9 | Green | As expected | Pass | `d1159c1` | `test_missing_accessibility_feature_is_flagged` |
| AC3-P10, AC3-P11 | Green | As expected | Pass | `d1159c1` | `test_accessibility_match_ignores_letter_case` |
| AC3-B1 | Green | As expected | Pass | `d1159c1` | `test_no_optional_requirements_compares_attendance_only` |
| AC3-X1 | Green | As expected | Pass | `d1159c1` | `test_all_unmet_attributes_are_reported_once` (`backend/venueService/tests/test_suitability.py`); the test carries the in-file comment `# AC3-X1 (cross-cutting)…`, which predates the story-prefix convention and was left untouched (referenced, not relabelled) in the 1 Nov 2026 gap sweep |
| AC3-N1 | Green | As expected | Pass | `d1159c1` | `test_unknown_venue_returns_404`; also confirmed live |
| AC3-N2, AC3-N3 | Green | As expected | Pass | `d1159c1` | `test_unknown_layout_value_is_rejected`, `test_unknown_slot_value_is_rejected` |
| AC3-X2 | Green | As expected | Pass | `d1159c1` | `test_check_requires_authentication`; confirmed live with no token and an invalid token (both 401) |
| AC3-X3 | Green | As expected | Pass | `d1159c1` | `test_event_coordinator_can_run_the_check`; confirmed live with `event_coordinator1@example.com` |
| AC4-H1, AC4-H2 | Green | As expected | Pass | `d1159c1` | `test_suitable_venue_returns_no_mismatches`, `test_unsuitable_venue_returns_a_reason_per_mismatch`; confirmed live |
| AC4-H3 | Green | As expected | Pass | `d1159c1` | `test_reasons_name_the_failing_values` |
| AC5-X1 | Green | As expected | Pass | `d1159c1` | `test_check_never_changes_the_venue_or_the_catalogue`; confirmed live |
| AC1-N3 to AC1-N6 | Red then Green | Red: the test file failed to import the missing modules. Green: as expected | Pass (UI addition, uncommitted working tree on `213a543`) | `213a543` + working tree | `__tests__/venue-suitability.test.tsx`: `rejects attendance`, `an invalid attendance sends no request` |
| AC3-H2, AC3-P12 | Red then Green | As expected | Pass (UI addition) | `213a543` + working tree | `sends the filled-in requirements...`, `omits requirements that were left blank`, `drops a layout and a slot outside the enums` |
| AC3-H3 | Red then Green | As expected | Pass (UI addition) | `213a543` + working tree | `pre-fills each result's check form from the search filters` |
| AC3-N4, AC3-N5, AC3-N6 | Red then Green | As expected | Pass (UI addition) | `213a543` + working tree | `reports a venue that no longer exists`, `redirects to sign-in...`, `reports ... as could not be checked` |
| AC4-H4, AC4-H5 | Red then Green | As expected | Pass (UI addition) | `213a543` + working tree | `shows Not suitable with each mismatch...`, `shows Suitable with no mismatch list`, and `returns the result from the service`. Flipping the verdict wording made both verdict tests fail |
| AC4-H6, AC5-X2 | Written after the code (not Red-first) | As expected | Pass (UI addition, mock venue API) | `213a543` + working tree | `e2e/venue-search.spec.ts` (`frontend/e2e/`): `coordinator checks a venue's suitability from the search results`; the unit test `makes no call other than the suitability POST` covers AC5-X2. The same wording flip made the browser test fail. The test carries the in-file `Purpose: SCRUM-12 AC4-H6, AC5-X2` comment, left untouched (referenced, not relabelled) in the 1 Nov 2026 gap sweep |

## Latest verification

Run on 4 October 2026 against commit `d1159c1`. Environment for the automated runs: local machine, Python 3.13, in-memory venue store, the authentication dependency overridden (so authService is **mocked**), no network.

| Check | Command (run from `backend/venueService`) | Result |
| --- | --- | --- |
| Lint | `ruff check .` | All checks passed |
| Suitability tests only | `pytest tests/test_suitability.py tests/test_venues_suitability.py -q` | 31 passed |
| Whole venueService suite | `pytest -q` | 67 passed, 10 skipped |

The 10 skipped tests are `tests/test_supabase_schema.py`, a live-database file that is untracked on this machine and not in the repository, so a clean checkout has no skips.

**UI addition (5 October 2026, `213a543` plus uncommitted changes).** Run from `frontend/` on Kennedy's machine, Node tooling as in the repo.

| Check | Command | Result |
| --- | --- | --- |
| Lint | `npm run lint` | Clean |
| Type check | `npm run typecheck` | Clean |
| Unit and component tests | `npm test` | 160 passed (19 files); 17 are new in `venue-suitability.test.tsx` |
| Browser tests, full suite | `npx playwright test` through a temporary config that selects the installed Google Chrome (`channel: "chrome"`; the Playwright browser download was not installed) | 20 passed, including the new test |

The browser test runs against the **mock** venue API in `e2e/support/venue-api.mjs`, which this change extended with a copy of the suitability rules. It proves the screen and the form-to-action wiring, not the real venueService contract. The real venueService is covered by its own 31 tests, and a manual check of the screen against the real stack (Docker Compose backends, `npm run dev`, signed in as a shared test coordinator) was done by Kennedy on 5 October 2026, who reported it working. That is the story owner's observation: no commands, counts or screenshots were captured, so it is not recorded as a Pass.

**Live check (real authService, 3 October 2026).** The real authService (Supabase Auth, shared dev project) and venueService (in-memory store, port 8004) were started, with the shared dev test accounts from `database/seed_test_accounts.sql`. The venue was created as `venue_staff@example.com` and checked as `event_coordinator1@example.com`: no token gave 401, an invalid token gave 401, a suitable check gave 200 with `suitable` true, an unsuitable check gave 200 with `capacity` and `facilities` mismatches, an unknown venue gave 404, and the venue record was identical before and after. Both services were stopped afterwards.

**Mutation check (manual, 3 October 2026).** `mutmut` is not installed, so ten one-line faults were injected into `app/suitability.py` one at a time. Every mutant made at least one test fail, and for each the test written for that rule was among those that failed.

| Mutant | Dedicated test that failed |
| --- | --- |
| M1 capacity `>` becomes `>=` | AC1-B2 |
| M2 required-facility match loses lower-casing | AC2-P2 |
| M3 layout check inverted | AC3-P1 |
| M4 slot check inverted | AC3-P6 |
| M5 required-accessibility match loses lower-casing | AC3-P11 |
| M6 result always `suitable` | AC1-B3 |
| M7 reason names every required facility, not only the missing ones | `test_only_the_missing_facility_is_named` |
| M8 capacity check removed | AC1-B3 |
| M9 venue-side facility lower-casing removed | AC2-P1 |
| M10 venue-side accessibility lower-casing removed | AC3-P10 |

The first run of this check showed that the original AC2-P1 did not catch M2, so the case was strengthened and AC2-P2 and the accessibility cases were added. `app/suitability.py` was restored after each run and is identical to the committed version.

**Not yet evidenced.** Pull-request CI, a run in the integrated stack through `docker compose`, browser or accessibility checks (there is no screen for this story), and coverage figures (`pytest-cov` is not installed).

## Disclosures

- The implementation (commits `dfc8b17` and `6991101`) was written before this document and before the AC review. The tests were written after the code, not Red-first, and were strengthened afterwards by the mutation check above.
- The code and the tests were both drafted by Claude Code. The test design review by a team member is **pending (Kennedy)**.
- The AC review in [Story contract](#story-contract) was **approved as proposed by Kennedy on 4 October 2026**; the assumptions A1 to A5 were not separately confirmed.
- The UI addition (per-result check form) was requested by Kennedy on 5 October 2026. Its cases were written into this document before the tests, and the unit tests were Red first. The browser test was written after the code. The pre-existing test `shows key attributes for each result` was changed to read the attribute list only, because the new form also offers "Theatre" as an option and made the old query ambiguous.
- Q3 (search results are already filtered, so a pre-filled check says Suitable until a requirement is changed) is open. Date and location checks were considered and left out of SCRUM-12 by Kennedy on 5 October 2026.
