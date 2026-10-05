# SCRUM-10 Test Cases: Check Equipment Availability

Last reviewed: 5 October 2026

Test catalogue for the equipment-availability story, designed **before implementation** (testing.md §2). Design decisions come from `SCRUM-10-summary.md` in the project folder. Companion catalogues: [scrum_16_testcases.md](scrum_16_testcases.md) (equipment status, whose `GET /status` endpoint this story changes) and [scrum_45_testcases.md](scrum_45_testcases.md).

> **Status: approved for implementation.** The scenario-form ACs and team design proposals 1–7 were approved by Yang (story owner) on 5 October 2026. The AI-drafted cases still need a team-member review (testing.md §10); record the reviewer under "Review" before the story is marked Done.

## Story contract

- **Jira key:** [SCRUM-10](https://is212g9t4.atlassian.net/browse/SCRUM-10), "Check Equipment Availability". Blocks SCRUM-13. Related: SCRUM-33, SCRUM-49, SCRUM-16.
- **User story:** As a Technical Support Staff member, I want to check whether sufficient suitable equipment is available for an event's date, so that I can decide whether the requested equipment can be provided.

### Acceptance criteria

Verbatim from Jira (checklist form):

1. The check returns, per requested equipment type, the quantity available for the event's required period.
2. Equipment marked damaged, under repair, or under maintenance is excluded from available quantity.
3. Equipment already committed to an overlapping event is excluded from available quantity.
4. Availability honours the rule that equipment is unavailable from collection the day before (D-1) until **Return Day + 1**.
5. Equipment at another venue is only counted available after allowing for transfer/preparation time.
6. Given requested quantity Q and available quantity A, when A < Q, then the check reports a shortfall.

Scenario form used by the matrix (**proposed wording, pending story-owner approval**):

| AC | Review outcome | Scenario wording |
| --- | --- | --- |
| AC1 | Clarify: "required period" is defined by AC4 and AC5 | Given a Technical Support Staff member, an event's start and end dates and its venue, when they check availability for a list of equipment types and quantities, then each requested type returns the requested quantity, the quantity available for the whole hold period, and the shortfall. |
| AC2 | Clarify: `RETIRED` is excluded too | Given catalogue rows whose status is `DAMAGED`, `UNDER_REPAIR`, `UNDER_MAINTENANCE` or `RETIRED`, when availability is checked, then none of their units is counted. |
| AC3 | Clarify: "committed" = units on the busiest overlapping day, per row | Given units of a catalogue row already reserved for another event whose hold overlaps the new event's hold, when availability is checked, then the units reserved on that row's busiest day in the hold are not counted; and `GET /equipment/{id}/status` reports `available_quantity` minus the units reserved today. |
| AC4 | Clarify: inclusive dates | Given an event from `start_date` to `end_date`, when availability is checked, then each unit is needed from `start_date − 1` to `end_date` inclusive, and is free again on `end_date + 1`. |
| AC5 | Clarify: "another venue" = another building; transfer time is a team proposal | Given a catalogue row based in a different building from the event's venue, when availability is checked, then its hold starts `TRANSFER_DAYS` (1) days earlier; store stock and rows in the event's building get no extra day. |
| AC6 | Keep | Given requested quantity Q and available quantity A for a type, when availability is checked, then the shortfall is `Q − A` when A < Q, and 0 otherwise. |

### Scope

- **Included:** the `equipment_reservations` table (migration `0020`; numbered after `0018_venue_booking_requests.sql`, which dev took for SCRUM-32), the pure Python availability module `app/availability.py` (`check_availability`, `hold_window`, `needs_transfer`, `committed_peak`), `POST /equipment/availability-check`, the reservation-aware `available_quantity` on `GET /equipment/{id}/status`, the `get_today()` Singapore-time dependency, and the venueService lookup.
- **Excluded (named, not claimed):** creating reservations and refusing a reservation on shortfall (SCRUM-13); linking reservations to recorded requirements (SCRUM-13, after SCRUM-33); flagging reservations when an event is rescheduled or equipment is marked damaged (SCRUM-49); preventing two staff from reserving the last units at once (SCRUM-13).
- **Actors:** Technical Support Staff run the check (`technical_support` role; an Operations Manager who also holds it is let through by `require_role`). Event coordinators without the role are refused. `GET /status` stays open to any authenticated user (unchanged from SCRUM-16).
- **State transitions:** none. The check and the status read are read-only.
- **Persistence:** reservations store `collection_date` (= the hold start, D-1 plus any transfer day) and `return_date` (= the event's end date). SCRUM-13 must save them this way; SCRUM-10 compares stored windows directly.

### Team design proposals (not customer rules)

Cases that depend on a proposal say so in the scenario, e.g. "(proposal 1)".

1. **Transfer time:** one fixed buffer, `TRANSFER_DAYS = 1` (Discussion #2).
2. **Partly damaged stock:** stock is split into separate catalogue rows by status (Discussions #13, #86).
3. **Reservation dates:** whole dates; `return_date` defaults to the event's end date (Discussions #5, #71).
4. **Which rows get a transfer day:** a row's building comes from matching `home_location` with `norm()` against venue names first, then venue locations. Rows matching no venue are store stock (D-1 only). A name shared by venues in two buildings gets the transfer day.
5. **Unknown types and past dates:** an unknown type returns `available: 0` with the full shortfall (Discussion #90); a past `start_date` is allowed (Discussion #25).
6. **Status meaning:** `available` on `GET /status` means "working", not "has free units".
7. **Type matching:** requested types are matched to the catalogue, and checked for duplicates, ignoring case and extra spaces.

## Shared test data

All dates are October 2026: **Fri 9, Sat 10, Sun 11, Mon 12, Tue 13, Wed 14, Thu 15, Fri 16**. `norm(s) = " ".join(s.split()).casefold()`.

**Venues (`VENUES`)**, returned by the mocked venueService `GET /venues`:

| id | name | location | status |
| --- | --- | --- | --- |
| `v-big` | Search Big Hall | Search Wing | available |
| `v-small` | Search Small Room | Search Wing | available |
| `v-closed` | Search Closed Hall | Search Wing | blocked |
| `v-harbour` | Harbour Room | Harbour Block | available |

The **event venue is `v-big`** (building "Search Wing") unless a case says otherwise.

**Catalogue rows.** Unless stated, a row is `AVAILABLE` with `home_location = "Store Room B"` (store stock). `P10` = one Projector row of 10 units. `S4` = one Speaker row of 4 units.

**Reservation shorthand.** `R(row, qty, collection → return)`, e.g. `R(P10, 10, Sun 11 → Mon 12)` is event A on Mon 12 holding all 10 projectors.

**API base request (`REQ`):** `POST /equipment/availability-check` with header `Authorization: Bearer staff-token` (stubbed authService returns roles `["technical_support"]`) and body `{"start_date": "2026-10-14", "end_date": "2026-10-14", "venue_id": "v-big", "items": [{"type": "Projector", "quantity": 5}]}`. API cases use `FakeSupabase` for the two read queries and a stub for the venueService call.

**Frozen clock.** `GET /status` cases override `get_today()` to return **Mon 12 Oct 2026**.

## How to run the suites

| Area | Command | Notes |
| --- | --- | --- |
| Backend, whole service | `pytest -q` from `backend/equipmentService/` | Includes the SCRUM-16 and SCRUM-45 regression suites |
| Availability unit tests | `pytest tests/test_availability.py -q` | Pure function, no mocks |
| Availability API tests | `pytest tests/test_availability_check.py tests/test_status.py -q` | `FakeSupabase` and stubbed authService and venueService |
| Database checks (manual) | Run `database/verify_equipment_reservations.sql` in the Supabase SQL editor after migration `0020` | One transaction, rolled back. Not run in CI |
| Lint | `ruff check .` from `backend/equipmentService/` | |

Every automated test carries a label comment with its ID, e.g. `# AC4-B1 (boundary): …`.

## Acceptance-criterion test matrix

Layers: **Unit** = `app/availability.py` called directly; **API** = FastAPI `TestClient` with mocked dependencies; **DB** = manual SQL verification script.

### AC1: available quantity per requested type

| ID | AC | Test scenario | Technique | Pre-conditions | Test steps | Test data | Expected result | Forbidden side effects | Layer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AC1-H1 | AC1, AC6 | Each requested type gets its own requested/available/shortfall | Happy | Rows `P10`, `S4`; no reservations | Call `check_availability` | Event Wed 14 → Wed 14 at `v-big`; items Projector 5, Speaker 2 | `Projector: {requested: 5, available: 10, shortfall: 0}`, `Speaker: {requested: 2, available: 4, shortfall: 0}`; no other keys | Input lists not mutated | Unit |
| AC1-H2 | AC1 | The endpoint wires venueService, both queries and the calculation together | Happy | Fake returns rows `P10`, `S4` and no reservations; venueService stub returns `VENUES` | Send `REQ` with items Projector 5, Speaker 2 | As left | `200`; body as AC1-H1; venueService `GET /venues` called once with the caller's `Authorization` header; equipment query filtered on `operational_status = AVAILABLE` | No insert, update or RPC call | API |
| AC1-P1 | AC1 | A type split across several rows is summed | Partition | Projector rows of 6 (Store Room B) and 4 (Store Room C); no reservations | Call `check_availability` | Event Wed 14; Projector 5 | `available: 10` | — | Unit |
| AC1-P2 | AC1 | Requested type matches the catalogue ignoring case and spaces (proposal 7) | Partition | Row `P10` (type "Projector") | Call `check_availability` | Item type `"  projector "`, quantity 5 | Key `"  projector "` (as requested) with `available: 10` | — | Unit |
| AC1-P3 | AC1 | Catalogue rows whose types differ only in case and spaces count together (proposal 7) | Partition | Rows "Projector" ×6 and "projector " ×4 | Call `check_availability` | Item "Projector" 5 | `available: 10` | — | Unit |
| AC1-P4 | AC1, AC6 | Unknown type is reported unavailable, not an error (proposal 5) | Partition | Row `P10`; no "Hologram" rows | Send `REQ` | Items Projector 5, Hologram 3 | `200`; `Hologram: {requested: 3, available: 0, shortfall: 3}`; Projector still `{5, 10, 0}` | No 4xx; no writes | API |
| AC1-P5 | AC1 | A past start date is allowed (proposal 5) | Partition | Row `P10` | Send `REQ` | `start_date = end_date = 2026-10-01` | `200`; `Projector: {5, 10, 0}` | Not refused | API |
| AC1-P6 | AC1 | A type missing its space is unknown: `norm()` changes spaces but never deletes them (proposal 7) | Partition | Row "Projector Stand" ×10 | Call `check_availability` | Item `"projectorstand"`, quantity 3 | `projectorstand: {requested: 3, available: 0, shortfall: 3}` | Not matched to "Projector Stand" | Unit |
| AC1-B1 | AC1 | One-day event (end = start) is accepted | Boundary | Row `P10` | Send `REQ` | start = end = 2026-10-14 | `200` | — | API |
| AC1-B2 | AC1 | End one day before start is refused | Boundary | Row `P10` | Send `REQ` | start 2026-10-14, end 2026-10-13 | `422` | No venueService call, no query | API |
| AC1-B3 | AC1 | Quantity 1 is accepted | Boundary | Row `P10` | Send `REQ` | Projector quantity 1 | `200`; `{1, 10, 0}` | — | API |
| AC1-B4 | AC1 | Quantity 0 is refused | Boundary | — | Send `REQ` | Projector quantity 0 | `422` | No venueService call, no query | API |
| AC1-N1 | AC1 | Invalid quantities are refused | Negative | — | Send `REQ` (parametrized) | quantity `-1`; `2.5`; `"five"` | `422` for each | No venueService call, no query | API |
| AC1-N2 | AC1 | Empty item list is refused | Negative | — | Send `REQ` | `items: []` | `422` | No venueService call, no query | API |
| AC1-N3 | AC1 | Duplicate types are refused, compared with `norm()` (proposal 7) | Negative | — | Send `REQ` (parametrized) | `["Projector", "Projector"]`; `["Projector", " projector "]` | `422` for each | No venueService call, no query | API |
| AC1-N4 | AC1 | Missing or malformed fields are refused | Negative | — | Send `REQ` (parametrized) | no `venue_id`; `start_date = "14/10/2026"`; `end_date = "2026-11-31"` (impossible date); no `items` | `422` for each | No venueService call, no query | API |
| AC1-N5 | AC1 | Unknown venue is 404 | Negative | venueService stub returns `VENUES` | Send `REQ` | `venue_id = "v-missing"` | `404` "Venue not found" | No equipment or reservation query | API |
| AC1-N6 | AC1 | venueService rejecting the token is passed on as 401 | Negative | venueService stub returns `401` | Send `REQ` | — | `401` | No equipment or reservation query | API |
| AC1-N7 | AC1 | venueService unreachable or failing is 502 | Negative | Stub raises `httpx.ConnectError`; separately returns `500` | Send `REQ` (parametrized) | — | `502` "Venue service unavailable" for each | No equipment or reservation query | API |
| AC1-N8 | AC1 | Database failure is a clean 500, not a crash | Negative | Fake equipment query raises `APIError` | Send `REQ` | — | `500` "Database operation failed" | No writes | API |
| AC1-X1 | AC1 | The check requires a session | Cross-cutting | No `Authorization` header | Send `REQ` | — | `401` | No venueService call, no query | API |
| AC1-X2 | AC1 | An event coordinator may not run the check | Cross-cutting | authService stub returns roles `["event_coordinator"]` | Send `REQ` | — | `403` | No venueService call, no query | API |
| AC1-X3 | AC1 | An Operations Manager who also holds `technical_support` may run it | Cross-cutting | authService stub returns roles `["event_operations_manager", "technical_support"]`; row `P10` | Send `REQ` | — | `200`; `{5, 10, 0}` | — | API |

### AC2: damaged, under-repair, under-maintenance (and retired) stock excluded

| ID | AC | Test scenario | Technique | Pre-conditions | Test steps | Test data | Expected result | Forbidden side effects | Layer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AC2-H1 | AC2 | Partly damaged stock counts only the working row (proposal 2) | Happy | Projector ×8 `AVAILABLE` and ×2 `DAMAGED` | Call `check_availability` | Event Wed 14; Projector 10 | `{requested: 10, available: 8, shortfall: 2}` | — | Unit |
| AC2-P1 | AC2 | `DAMAGED` row counts 0 | Partition | One Projector row ×5 with the status | Call `check_availability` (parametrized) | Event Wed 14; Projector 1 | `available: 0` | — | Unit |
| AC2-P2 | AC2 | `UNDER_REPAIR` row counts 0 | Partition | As AC2-P1 | As AC2-P1 | As AC2-P1 | `available: 0` | — | Unit |
| AC2-P3 | AC2 | `UNDER_MAINTENANCE` row counts 0 | Partition | As AC2-P1 | As AC2-P1 | As AC2-P1 | `available: 0` | — | Unit |
| AC2-P4 | AC2 (clarify) | `RETIRED` row counts 0 | Partition | As AC2-P1 | As AC2-P1 | As AC2-P1 | `available: 0` | — | Unit |
| AC2-P5 | AC2, AC3 | A reservation on an excluded row is not subtracted again | Partition | Projector ×8 `AVAILABLE`, ×2 `DAMAGED`; `R(DAMAGED row, 2, Tue 13 → Wed 14)` | Call `check_availability` | Event Wed 14; Projector 8 | `available: 8` (not 6) | — | Unit |
| AC2-H2 | AC2 | The endpoint only reads `AVAILABLE` rows | Happy | Fake returns `P10` | Send `REQ` | — | `200`; equipment query has filter `operational_status = AVAILABLE` | No writes | API |

### AC3: units committed to overlapping events excluded

| ID | AC | Test scenario | Technique | Pre-conditions | Test steps | Test data | Expected result | Forbidden side effects | Layer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AC3-H1 | AC3 | Units reserved for an overlapping event are subtracted | Happy | `P10`; `R(P10, 4, Sun 11 → Mon 12)` | Call `check_availability` | Event Mon 12 (hold Sun 11 → Mon 12); Projector 5 | `available: 6` | — | Unit |
| AC3-H2 | AC3 | The endpoint subtracts fetched reservations | Happy | Fake returns `P10` and `R(P10, 4, Tue 13 → Wed 14)` | Send `REQ` | — | `200`; `{5, 6, 0}` | No writes | API |
| AC3-P1 | AC3 | A reservation outside the hold is ignored | Partition | `P10`; `R(P10, 10, Fri 30 Oct → Sat 31 Oct)` | Call `check_availability` | Event Wed 14 | `available: 10` | — | Unit |
| AC3-P2 | AC3 | A reservation on another type is ignored | Partition | `P10`, `S4`; `R(S4, 4, Tue 13 → Wed 14)` | Call `check_availability` | Event Wed 14; Projector 5 | Projector `available: 10` | — | Unit |
| AC3-P3 | AC3 | Reservations that overlap each other add up | Partition | `P10`; `R(P10, 3, Sun 11 → Mon 12)`, `R(P10, 4, Sun 11 → Mon 12)` | Call `check_availability` | Event Mon 12 | `available: 3` | — | Unit |
| AC3-P4 | AC3 | Busiest day, not the sum, of reservations that never overlap | Partition | `P10`; `R(P10, 5, Mon 12 → Mon 12)`, `R(P10, 5, Fri 16 → Fri 16)` | Call `check_availability` | Event Mon 12 → Fri 16 (hold Sun 11 → Fri 16) | `available: 5` (not 0) | — | Unit |
| AC3-P5 | AC3 | Busiest day is per row, not per type | Partition | Projector rows X ×5 and Y ×5; `R(X, 5, Mon 12 → Mon 12)`, `R(Y, 5, Fri 16 → Fri 16)` | Call `check_availability` | Event Mon 12 → Fri 16 | `available: 0` (not 5) | — | Unit |
| AC3-B1 | AC3 | Over-reserved row floors at 0 and does not eat into other rows | Boundary | Projector rows X ×5 and Y ×4; `R(X, 4, Tue 13 → Wed 14)`, `R(X, 3, Tue 13 → Wed 14)` | Call `check_availability` | Event Wed 14 | `available: 4` (X gives 0, not −2) | — | Unit |
| AC3-B2 | AC3, AC5 | The reservation query fetches back to the widest possible hold start | Boundary | Fake returns `P10` | Send `REQ` | Event Wed 14 → Wed 14 | Reservation query filters: `equipment_id` in the fetched row ids, `collection_date <= 2026-10-14`, `return_date >= 2026-10-12` (start − 1 − `TRANSFER_DAYS`) | No writes | API |
| AC3-H3 | AC3 | `GET /status` subtracts units reserved today | Happy | Today = Mon 12; row `P10` `AVAILABLE`; `R(P10, 4, Sun 11 → Tue 13)` | `GET /equipment/{id}/status` | — | `200`; `available: true`, `available_quantity: 6` | No writes | API |
| AC3-B3 | AC3 | `GET /status`: a reservation that returned yesterday is not subtracted | Boundary | Today = Mon 12; `R(P10, 4, Sat 10 → Sun 11)` | `GET` status | — | `available_quantity: 10` | — | API |
| AC3-B4 | AC3 | `GET /status`: a reservation returning today is subtracted | Boundary | Today = Mon 12; `R(P10, 4, Sun 11 → Mon 12)` | `GET` status | — | `available_quantity: 6` | — | API |
| AC3-B5 | AC3 | `GET /status`: a reservation collecting today is subtracted | Boundary | Today = Mon 12; `R(P10, 4, Mon 12 → Tue 13)` | `GET` status | — | `available_quantity: 6` | — | API |
| AC3-B6 | AC3 | `GET /status`: a reservation collecting tomorrow is not subtracted | Boundary | Today = Mon 12; `R(P10, 4, Tue 13 → Wed 14)` | `GET` status | — | `available_quantity: 10` | — | API |
| AC3-P6 | AC3 | `GET /status`: fully reserved working stock stays `available: true` (proposal 6) | Partition | Today = Mon 12; `R(P10, 10, Sun 11 → Mon 12)` | `GET` status | — | `available: true`, `available_quantity: 0` | — | API |
| AC3-P7 | AC3 | `GET /status`: a non-`AVAILABLE` row with a reservation stays at 0, never negative | Partition | Today = Mon 12; row ×10 `DAMAGED`; `R(row, 4, Sun 11 → Mon 12)` | `GET` status | — | `available: false`, `available_quantity: 0` | — | API |
| AC3-X1 | AC3 | "Today" is Singapore time, not server time | Cross-cutting | — | Call `get_today` with the clock at `2026-10-11T16:30Z` (00:30 Mon 12 in Singapore) | — | Returns `2026-10-12` (a UTC-based date would be Sun 11) | — | Unit |
| AC3-H4 | AC3 | A valid reservation row can be stored | Happy | Migrations through `0020` applied | Run `verify_equipment_reservations.sql` | Insert quantity 2, Sun 11 → Mon 12, existing equipment and event request | Insert succeeds; rolled back at the end | Data left behind | DB (manual) |
| AC3-N1 | AC3 | Quantity must be positive | Negative | As AC3-H4 | Run the script | quantity 0 | Check-constraint violation | Row stored | DB (manual) |
| AC3-N2 | AC3 | Return date cannot be before collection date | Negative | As AC3-H4 | Run the script | Mon 12 → Sun 11 | Check-constraint violation (same-day Mon 12 → Mon 12 accepted) | Row stored | DB (manual) |
| AC3-N3 | AC3 | Reservation must point at real equipment and a real event request | Negative | As AC3-H4 | Run the script | unknown `equipment_id`; unknown `event_request_id` | Foreign-key violation for each | Row stored | DB (manual) |
| AC3-X2 | AC3 | Browser roles cannot read or write reservations | Cross-cutting | `0020` applied with RLS on and grants revoked | `GET /rest/v1/equipment_reservations` with the publishable key | — | Permission denied / empty, matching the other equipment tables | Rows exposed | DB (manual, REST) |

### AC4: unavailable from D-1 until Return Day + 1

Store-stock rows only (no transfer day). Event A on Mon 12 holds every projector: `R(P10, 10, Sun 11 → Mon 12)`. Each case checks a new one-day event B; "clash" means `available: 0`, "free" means `available: 10`.

| ID | AC | Test scenario | Technique | Pre-conditions | Test steps | Test data | Expected result | Forbidden side effects | Layer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AC4-H1 | AC4 | The hold window runs from D-1 to the end date | Happy | Store-stock row | Call `hold_window` | Event Wed 14 → Fri 16 | `(Tue 13, Fri 16)` | — | Unit |
| AC4-B1 | AC4 | Event B the day after A's return collects on A's return day: clash | Boundary | Event A as above | Call `check_availability` | B on Tue 13 (hold Mon 12 → Tue 13) | Clash (`available: 0`). Comparing against B's `start_date` instead of its hold start would wrongly give 10 | — | Unit |
| AC4-B2 | AC4 | Return Day + 1 is the earliest free collection day | Boundary | Event A as above | Call `check_availability` | B on Wed 14 (hold Tue 13 → Wed 14) | Free (`available: 10`) | — | Unit |
| AC4-B3 | AC4 | Event B on A's collection day (D-1) clashes | Boundary | Event A as above | Call `check_availability` | B on Sun 11 (hold Sat 10 → Sun 11) | Clash | — | Unit |
| AC4-B4 | AC4 | Event B ending the day before A's collection is free | Boundary | Event A as above | Call `check_availability` | B on Sat 10 (hold Fri 9 → Sat 10) | Free | — | Unit |
| AC4-B5 | AC4 | Multi-day A: the day after its last day still clashes | Boundary | `R(P10, 10, Sun 11 → Wed 14)` (A runs Mon 12 → Wed 14) | Call `check_availability` | B on Thu 15 (hold Wed 14 → Thu 15) | Clash | — | Unit |
| AC4-B6 | AC4 | Multi-day A: two days after its last day is free | Boundary | As AC4-B5 | Call `check_availability` | B on Fri 16 (hold Thu 15 → Fri 16) | Free | — | Unit |

### AC5: transfer time for equipment in another building

`TRANSFER_DAYS = 1` (proposal 1). Event venue `v-big` (Search Wing).

| ID | AC | Test scenario | Technique | Pre-conditions | Test steps | Test data | Expected result | Forbidden side effects | Layer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AC5-H1 | AC5 | Equipment in another building is still counted when nothing clashes | Happy | Projector ×10 with `home_location = "Harbour Room"`; no reservations | Call `check_availability` | Event Wed 14; Projector 5 | `available: 10` | — | Unit |
| AC5-B1 | AC5, AC4 | Transfer day: event B two days after A's return clashes | Boundary | Row ×10 at "Harbour Room"; `R(row, 10, Sat 10 → Mon 12)` (A on Mon 12) | Call `check_availability` | B on Wed 14 (hold Mon 12 → Wed 14) | `available: 0` | — | Unit |
| AC5-B2 | AC5, AC4 | Transfer day: three days after A's return is free | Boundary | As AC5-B1 | Call `check_availability` | B on Thu 15 (hold Tue 13 → Thu 15) | `available: 10` | — | Unit |
| AC5-P1 | AC5, AC4 | Store stock gets D-1 only in the same scenario (proposal 4) | Partition | Row `P10` (Store Room B); `R(P10, 10, Sun 11 → Mon 12)` | Call `check_availability` | B on Wed 14 | `available: 10` (contrast with AC5-B1) | — | Unit |
| AC5-P2 | AC5 | Building given as the event's location, with odd spacing and case | Partition | `VENUES`; event venue `v-big` | Call `hold_window` for a row | `home_location = "search wing "`; event Wed 14 | Hold start Tue 13 (no transfer) | — | Unit |
| AC5-P3 | AC5 | Building given as the event venue's own name | Partition | As AC5-P2 | As AC5-P2 | `"Search Big Hall"` | Tue 13 (no transfer) | — | Unit |
| AC5-P4 | AC5 | Another venue in the same building | Partition | As AC5-P2 | As AC5-P2 | `"Search Small Room"` | Tue 13 (no transfer) | — | Unit |
| AC5-P5 | AC5 | A blocked venue still identifies its building | Partition | As AC5-P2 | As AC5-P2 | `"Search Closed Hall"` | Tue 13 (no transfer) | — | Unit |
| AC5-P6 | AC5 | Another building given by location | Partition | As AC5-P2 | As AC5-P2 | `"Harbour Block"` | Mon 12 (transfer) | — | Unit |
| AC5-P7 | AC5 | Another building given by venue name, any case | Partition | As AC5-P2 | As AC5-P2 | `"harbour room"` | Mon 12 (transfer) | — | Unit |
| AC5-P8 | AC5 | Unrecognised location is store stock (proposal 4) | Partition | As AC5-P2 | As AC5-P2 | `"Store Room B"` | Tue 13 (no transfer) | — | Unit |
| AC5-P9 | AC5 | A venue name shared across two buildings gets the transfer day (proposal 4) | Partition | `VENUES` plus "Studio" in Search Wing and "Studio" in Harbour Block | As AC5-P2 | `"Studio"` | Mon 12 (transfer) | — | Unit |
| AC5-P10 | AC5 | Venue names are matched before locations (proposal 4) | Partition | `VENUES` plus a venue named "Harbour Block" located in Search Wing | As AC5-P2 | `"Harbour Block"` | Tue 13 (resolved by name to Search Wing; no transfer) | — | Unit |
| AC5-X1 | AC5 | The transfer buffer is a setting, not a hard-coded 1 | Cross-cutting | Row at "Harbour Room"; `TRANSFER_DAYS = 2` | Call `hold_window` | Event Wed 14 | Hold start Sun 11 | — | Unit |
| AC5-H2 | AC5 | The endpoint uses the venue list to apply the transfer day | Happy | Fake returns a row ×10 at "Harbour Room" and `R(row, 10, Sat 10 → Mon 12)`; venueService returns `VENUES` | Send `REQ` | Event Wed 14 | `200`; `{5, 0, 5}` | No writes | API |

### AC6: shortfall when A < Q

Row `P10`, no reservations, event Wed 14, unless stated.

| ID | AC | Test scenario | Technique | Pre-conditions | Test steps | Test data | Expected result | Forbidden side effects | Layer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AC6-B1 | AC6 | One more requested than available | Boundary | `P10` | Call `check_availability` | Projector 11 | `{11, 10, 1}` | — | Unit |
| AC6-B2 | AC6 | Exactly what is available | Boundary | `P10` | Call `check_availability` | Projector 10 | `{10, 10, 0}` | — | Unit |
| AC6-B3 | AC6 | One fewer than available | Boundary | `P10` | Call `check_availability` | Projector 9 | `{9, 10, 0}` | — | Unit |
| AC6-P1 | AC6 | Each type is judged on its own | Partition | `P10`, `S4` | Call `check_availability` | Projector 12, Speaker 2 | Projector `{12, 10, 2}`; Speaker `{2, 4, 0}` | — | Unit |
| AC6-P2 | AC6 | Nothing free: the shortfall is the whole request | Partition | `P10`; `R(P10, 10, Tue 13 → Wed 14)` | Call `check_availability` | Projector 5 | `{5, 0, 5}` | — | Unit |
| AC6-H1 | AC6 | A shortfall is reported, not refused | Happy | Fake returns `P10` | Send `REQ` | Projector 12 | `200` (not `409`); `{12, 10, 2}` | No writes | API |

### Regression from SCRUM-16

`GET /status` now also queries reservations. The existing SCRUM-16 cases (its AC2-H1, AC2-P1 to P4, AC2-B1, AC2-N1, AC2-N2, AC2-X1, AC2-X2 in `tests/test_status.py`) must still pass with an empty reservation result and are re-run as part of this story.

## Latest execution record

**Run 5 October 2026: Green (implementation complete).** Branch `feat/scrum-10-equipment-availability`, commits `8750725` (clock), `0d9c357` (pure availability module), `4dd4044` (migration 0020 + verify script), `e946445` (status subtracts reservations), `6681a91` (availability-check endpoint). Environment: macOS (Darwin 24.6.0), Python 3.14.2 (project `.venv`), dependencies installed from `pyproject.toml` (`.[dev]`). Dependencies **fully mocked**: `FakeSupabase` for the database; authService and venueService stubbed at `httpx.get`; the clock frozen via `app.dependency_overrides[get_today]`.

Command: `pytest -q` from `backend/equipmentService/` → **136 passed, 0 failed, 0 skipped** (54 pre-existing SCRUM-16/SCRUM-45 tests + 82 SCRUM-10 test runs). `ruff check .` → all checks passed. The one warning is a pre-existing starlette `anyio` deprecation, unrelated to this story.

Migration 0020 and `verify_equipment_reservations.sql` were **not** applied to the shared Supabase database (pending story-owner approval), so the manual database cases are recorded **Blocked**, not Pass.

| ID | Automation status | Actual result | Execution status | Build or commit | Executed by and date | Remarks and evidence |
| --- | --- | --- | --- | --- | --- | --- |
| AC1-H1, AC1-P1–P3, AC1-P6, AC2-H1, AC2-P1–P5, AC3-H1, AC3-P1–P5, AC3-B1, AC4-H1, AC4-B1–B6, AC5-H1, AC5-B1, AC5-B2, AC5-P1–P10, AC5-X1, AC6-B1–B3, AC6-P1, AC6-P2 | Automated | Expected results | Pass | `6681a91` | Claude (AI), 5 Oct 2026 | `pytest tests/test_availability.py -q` → 44 passed |
| AC3-X1 | Automated | Singapore date, not UTC | Pass | `6681a91` | Claude (AI), 5 Oct 2026 | `pytest tests/test_clock.py -q` → 1 passed |
| AC1-H2, AC1-P4, AC1-P5, AC1-B1–B4, AC1-N1–N8, AC1-X1–X3, AC2-H2, AC3-H2, AC3-B2, AC5-H2, AC6-H1 | Automated | Expected results, including no venue call and no table queried on any refusal | Pass | `6681a91` | Claude (AI), 5 Oct 2026 | `pytest tests/test_availability_check.py -q` → 30 passed |
| AC3-H3, AC3-B3–B6, AC3-P6, AC3-P7 | Automated | Expected results | Pass | `6681a91` | Claude (AI), 5 Oct 2026 | `pytest tests/test_status.py -q` → 31 passed (incl. SCRUM-16 regression) |
| SCRUM-16 / SCRUM-45 regression | Automated | 54 existing tests pass with reservations unseeded (`data = None` → `[]`) | Pass | `6681a91` | Claude (AI), 5 Oct 2026 | `pytest -q` → 136 passed |
| AC3-H4, AC3-N1–N3 | Manual | — | **Blocked** | `4dd4044` | — | Migration `0020` and `verify_equipment_reservations.sql` not yet applied to the shared Supabase database; awaiting story-owner approval. Run in the SQL editor, expect `ALL EQUIPMENT RESERVATION VERIFICATIONS PASSED` |
| AC3-X2 | Manual | — | **Blocked** | `4dd4044` | — | Needs the real Supabase RLS roles and the publishable key over REST after `0020` is applied |
| Integration (`testing.md` §5) | Manual | — | **Blocked** | `6681a91` | — | `docker compose up` + real-token POST to `:8002/equipment/availability-check` needs live authService/venueService/Supabase credentials |

**Run 5 October 2026: Red (tests written, behaviour not implemented).** Branch `feat/scrum-10-equipment-availability` from `dev` at `7ed6df6`, uncommitted. Environment: Linux VM, Python 3.12.14, dependencies installed from `pyproject.toml` (`.[dev]`). Dependencies **fully mocked**: `FakeSupabase` for the database; authService and venueService stubbed at `httpx.get`. `app/availability.py` and `app/clock.py` are interface stubs that raise `NotImplementedError`; `POST /equipment/availability-check` does not exist yet.

Command: `pytest -q` from `backend/equipmentService/` → **79 failed, 57 passed, 0 skipped**. `ruff check .` → all checks passed. The 57 passes are the 54 existing tests on `dev` plus the three SCRUM-10 guard cases noted below.

| ID | Automation status | Actual result | Execution status | Build or commit | Executed by and date | Remarks and evidence |
| --- | --- | --- | --- | --- | --- | --- |
| AC1-H1, AC1-P1–P3, AC1-P6, AC2-H1, AC2-P1–P5, AC3-H1, AC3-P1–P5, AC3-B1, AC4-H1, AC4-B1–B6, AC5-H1, AC5-B1, AC5-B2, AC5-P1–P10, AC5-X1, AC6-B1–B3, AC6-P1, AC6-P2 | Red | `NotImplementedError` (all 45 test runs) | Fail (expected) | `7ed6df6` + uncommitted | Claude (AI), 5 Oct 2026 | `tests/test_availability.py` |
| AC3-X1 | Red | `NotImplementedError` | Fail (expected) | As above | Claude (AI), 5 Oct 2026 | `tests/test_clock.py` |
| AC1-H2, AC1-P4, AC1-P5, AC1-B1–B4, AC1-N1–N8, AC1-X1–X3, AC2-H2, AC3-H2, AC3-B2, AC5-H2, AC6-H1 | Red | `405 Method Not Allowed` (route missing; 30 test runs) | Fail (expected) | As above | Claude (AI), 5 Oct 2026 | `tests/test_availability_check.py` |
| AC3-H3, AC3-B4, AC3-B5, AC3-P6 | Red | `available_quantity` 10 instead of 6 / 0: reservations not subtracted | Fail (expected) | As above | Claude (AI), 5 Oct 2026 | `tests/test_status.py` |
| AC3-B3, AC3-B6, AC3-P7 | Green before implementation | 10, 10, 0 as expected | Pass | As above | Claude (AI), 5 Oct 2026 | Guards: they pin that out-of-window reservations and non-`AVAILABLE` rows are *not* over-subtracted, so they cannot fail against today's code. They prove their value once the subtraction exists |
| AC3-H4, AC3-N1–N3 | Planned | — | Not executed | — | — | `database/verify_equipment_reservations.sql` (manual; expected Red before migration `0020`: relation does not exist) |
| AC3-X2 | Planned | — | Not executed | — | — | Manual REST check with the publishable key |
| SCRUM-16 / SCRUM-45 regression | Green | 54 existing tests pass with the extended `FakeSupabase` | Pass | As above | Claude (AI), 5 Oct 2026 | `pytest -q` |

## Assumptions and open questions

- **Approval.** The scenario-form ACs and proposals 1 to 7 were approved by the story owner on 5 October 2026 before implementation started (testing.md §1).
- **No frontend in scope.** The summary delivers the API only. Confirm with the team that an API-only check is enough for this story, or whether a Technical Support screen belongs here or in SCRUM-13. If a screen is added, its cases (and one Playwright journey) go back through the AC review gate.
- **Event dates come from the request.** The check takes `start_date` and `end_date` directly rather than reading them from an event request; SCRUM-13 links reservations to events.
- **Stored windows depend on SCRUM-13.** These cases assume reservations already carry `collection_date` = hold start (D-1 plus any transfer day). SCRUM-13 must save them that way.
- **Typo risk (proposal 4 trade-off).** A mistyped venue-based `home_location` reads as store stock, so it loses its transfer day and availability is over-reported by one day.
- **Test seams constrain the implementation.** The API tests stub authService and venueService at `httpx.get` (as `deps.py` does) and assert the reservation query uses `.in_`, `.lte` and `.gte` with ISO date strings. The response is a JSON object keyed by each type exactly as requested.
- **Database cases are manual.** CI runs no Postgres, so AC3-H4, AC3-N1 to N3 and AC3-X2 are only proven by running the verification script by hand.
- **Concurrency is out of scope.** Two staff reserving the last units at once is SCRUM-13's write-path problem.

## Review

| Reviewed by | Date | Outcome |
| --- | --- | --- |
| — | — | Pending (testing.md §10) |
