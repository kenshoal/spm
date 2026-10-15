# SCRUM-13 Test Cases: Reserve Equipment for an Event

Last reviewed: 15 October 2026

Test catalogue for the equipment-reservation story, designed **before implementation** (testing.md §2). It covers **AC1 to AC5, the whole story**. The two Jira criteria about flagging reservations for review (J6, J7) moved to SCRUM-64, owned by Tiong Heng Rui, on 13 October 2026; see the AC review and "Excluded".

Companion catalogues: [scrum_10_testcases.md](scrum_10_testcases.md) (availability rules and the `equipment_reservations` table this story writes to), [scrum_33_testcases.md](scrum_33_testcases.md) (the equipment requirements reserved against) and [scrum_39_testcases.md](scrum_39_testcases.md) (its AC7, the Technical Support read of reservations, was deferred to this story).

> **Status: implemented, unit and API Green on the branch.** The scenario-form ACs, decisions D1 to D10 and the recommended answers to Q1 to Q5 were approved by Yang Xue (story owner) on 12 October 2026. J6 and J7 were moved to SCRUM-64 by agreement between Yang Xue and Tiong Heng Rui on 13 October 2026. Migration `0027` was applied to shared development on 14 October 2026; the DB verify scripts, the AC3-N2 two-session race and the AC3-X1 integration check are the remaining owner steps. The AI-drafted cases still need a team-member review (testing.md §10); record the reviewer under "Review" before the story is marked Done.
>
> **15 October 2026, review round:** a teammate review found that the reservation endpoint fails against the real venueService (F1) and that `reserve_equipment` does not check the equipment type (F3). Decisions D11 and D12 and the cases AC1-X3 to X7, AC1-N10 to N13 and L1 were added for the fixes and are Green locally and on a disposable database; `0028` on shared Supabase, the live run (L1, AC3-X1) and PR CI are the remaining owner steps; see "Disclosures" and the plan `docs/superpowers/plans/2026-10-15-scrum-13-review-fixes.md`.

## Story contract

- **Jira key:** [SCRUM-13](https://is212g9t4.atlassian.net/browse/SCRUM-13), "Reserve Equipment for an Event". Sprint 3. Blocked by SCRUM-10 and SCRUM-33 (both Done). Blocks SCRUM-60. SCRUM-58 needs its reservations before an event can go to the safety check. Related: SCRUM-64 (flag affected arrangements; owns J6 and J7 from 13 October 2026), SCRUM-16 (equipment status).
- **User story:** As a Technical Support Staff member, I want to reserve available equipment for an event, so that the same limited equipment is not simultaneously committed to incompatible events.

### AC review

Jira criteria read on 12 October 2026.

| Jira criterion | Outcome | Reason | Scenario wording |
| --- | --- | --- | --- |
| J1 "A reservation is made against an equipment requirement the Event Coordinator has recorded for the event." | **Clarify** → AC1 | "Against" is undefined: which catalogue row, how much, and whether a requirement can be over-reserved. Q&A #19 fixes the workflow (EC records → TSS reviews → reserve). | **AC1** Given an equipment requirement recorded for an event, when Technical Support reserves a quantity of one catalogue row of the same type against it, then the reservation is linked to that requirement and its event; the total reserved against a requirement may not exceed the requirement's quantity. |
| J2 "Only equipment that is available — not committed elsewhere, and not damaged/under repair/under maintenance — can be reserved." | **Narrow** → AC2 | "Not committed elsewhere" is exactly J3; keeping it in both duplicates the cases (testing.md §1, non-duplication). AC2 keeps the status rule; AC3 owns commitment. `RETIRED` added, as in SCRUM-10 AC2. | **AC2** Given a catalogue row whose status is `DAMAGED`, `UNDER_REPAIR`, `UNDER_MAINTENANCE` or `RETIRED`, when Technical Support tries to reserve from it, then it is refused (409) and nothing is stored. |
| J3 "Given a quantity reserved for one event, when another event requests the same items for an overlapping availability period, then the reserved quantity is not offered to the second event." | **Clarify** → AC3 | "Overlapping availability period" is SCRUM-10's hold window (D-1 to Return Day + 1, plus a transfer day for another building). Must also hold when two staff reserve the last units at once. | **AC3** Given units of a catalogue row already reserved for any event (or another requirement of the same event) whose hold overlaps the new hold, when Technical Support reserves from that row, then only the units free on the row's busiest overlapping day can be reserved, including when two reservations race for the last units. |
| J4 "A successful reservation records which equipment, what quantity, and the event and period it is held for." | **Clarify** → AC4 | "Period" must be stored the way SCRUM-10 reads it (`collection_date` = hold start, `return_date` = event end). "Records" needs an observable read, which also closes SCRUM-39 AC7. | **AC4** Given a successful reservation, when it is stored, then it records the catalogue row, quantity, requirement, event, `collection_date` (hold start), `return_date` (event end), who made it and when; and Technical Support can list an event's reservations. |
| J5 "Given a requested quantity exceeding what is available, when reservation is attempted, then it is refused and the shortfall is reported." | **Keep** → AC5 | Testable as written. Q&A #90 adds that a shortfall on one requirement does not stop other requirements being reserved. | **AC5** Given requested quantity Q and available quantity A on the chosen row, when A < Q, then the reservation is refused (409) and the response reports requested, available and shortfall `Q − A`; nothing is stored. |
| J6 "Given the event is rescheduled to a new date, when the reservation is evaluated, then it is flagged for re-review because availability may have changed." | **Move** → SCRUM-64 | SCRUM-64 already flags every equipment arrangement on a significant change, date or time included; building it here would duplicate it. Agreed with Tiong Heng Rui (SCRUM-64 owner) on 13 October 2026. | Not in this story. |
| J7 "Given reserved equipment is later marked damaged/unavailable, when its status changes, then the affected event's reservation is flagged for review." | **Move** → SCRUM-64 | It writes to SCRUM-64's "needs review" state, so all flagging for review lives in one story. Agreed with Tiong Heng Rui (SCRUM-64 owner) on 13 October 2026: SCRUM-64 adds the equipment-status trigger alongside its significant-change triggers. | Not in this story. |

### Scope

| | Behaviour | Jira |
| --- | --- | --- |
| Included | `POST /equipment-reservations`: reserve units of one catalogue row against one requirement | SCRUM-13 |
| Included | `GET /equipment-reservations/by-event/{event_request_id}`: Technical Support lists an event's reservations | SCRUM-13 (closes SCRUM-39 AC7) |
| Included | Migration `0027`: `requirement_id` column on `equipment_reservations`; RPC `reserve_equipment` that locks the row and re-checks before inserting | SCRUM-13 |
| Included | A pure row-availability function in `app/availability.py`, reusing SCRUM-10's `hold_window`, `needs_transfer` and `committed_peak` | SCRUM-13 |
| Included | `GET /venues/locations` in venueService: every venue's `id`, `name` and `location`, readable by Technical Support (D11). equipmentService (this story and SCRUM-10's availability check) reads it instead of `GET /venues` | SCRUM-13 (fixes SCRUM-10's live path) |
| Included | Migration `0028`: `reserve_equipment` checks the equipment type against the requirement under the lock (D12) | SCRUM-13 |
| Excluded | Flagging a reservation for review when the event is rescheduled, a requirement changes, or reserved equipment is marked damaged or unavailable | SCRUM-64 (J6, J7; Q&A #16, #114), moved 13 October 2026. SCRUM-64 reads the rows this story stores in `equipment_reservations` (linked by `equipment_id` and `requirement_id`) |
| Excluded | Releasing or cancelling a reservation; releasing on event cancellation | Q4; backlog E1-2 |
| Excluded | Moving the requirement's arrangement status | SCRUM-33 `PATCH …/arrangement` (D8) |
| Excluded | Frontend screen | Q5 |

### Actors and relationship permissions

- **Technical Support Staff** (`technical_support`) reserve and list reservations. Role-wide, as SCRUM-33 D6 and SCRUM-39 state. An Operations Manager who also holds the role is let through by `require_role`.
- **Everyone else** (Event Coordinators, organisers, Venue Staff, attendees) get 403. No browser role reaches the table or the RPC (`0020` revokes `anon` and `authenticated`).

### State transitions

None on the event or the requirement. A reservation is created once; it has no status in this story.

### Persistence and atomicity

- The API computes the hold window and a pre-check (for the shortfall report), then calls `reserve_equipment`. The RPC locks the `equipment` row (`FOR UPDATE`), re-checks status, the committed peak in the window and the requirement's outstanding quantity, then inserts. A refusal under the lock writes nothing.
- Error codes follow the team convention: `P0002` not found → 404, `P0004` conflict → 409. From `0028`, `22023` (type mismatch under the lock, D12) → 422.

### Decisions

| ID | Decision |
| --- | --- |
| D1 | **Body:** `requirement_id`, `equipment_id`, `quantity`, `start_date`, `end_date`, `venue_id`. Extra fields are forbidden. Technical Support supplies the dates and venue because it cannot call eventRequestService (SCRUM-33 plan: that service returns 403 to `technical_support`). The requirement's snapshot shows the event's dates to copy from. Same inputs as SCRUM-10's availability check. |
| D2 | **One catalogue row per reservation.** A requirement met from several rows (split by location or status, SCRUM-10 proposal 2) gets several reservations. |
| D3 | **No over-reserving a requirement:** the sum of reservations against a requirement may not exceed its quantity. Excess → 409 "Exceeds the equipment requirement". |
| D4 | **Availability is per row:** row total − units reserved on the row's busiest day in the hold window, using SCRUM-10's functions unchanged. Spare units on a different row of the same type do not help (the caller picks the row). |
| D5 | **Stored period** follows SCRUM-10's contract: `collection_date` = `start_date − 1` (one more day, `TRANSFER_DAYS`, if the row is based in another building from `venue_id`); `return_date` = `end_date` (Q&A #5; #113 says the team proposes the return date). |
| D6 | **Race safety:** the Python pre-check produces the shortfall numbers; `reserve_equipment` repeats the status, peak and outstanding-quantity checks under the row lock. A check that fails only under the lock → 409 "Equipment no longer available". |
| D6a | **The requirement row is locked too** (added 14 October 2026, story decision P1): `reserve_equipment` locks the `equipment_requirements` row `FOR UPDATE` before the `equipment` row, so two reservations against the same requirement from different catalogue rows cannot both pass the D3 check. Lock order is requirement → equipment; no other function locks equipment then requirement, so the two orders cannot deadlock. |
| D7 | **Migration `0027`** adds `requirement_id uuid NOT NULL REFERENCES equipment_requirements (id)`. The RPC copies `event_request_id` from the requirement; the caller cannot set it. |
| D8 | **Reserving does not change the requirement's arrangement status.** Technical Support still moves it with SCRUM-33's `PATCH …/arrangement` (Q&A #90: the Coordinator judges readiness). |
| D9 | **Read:** `GET /equipment-reservations/by-event/{event_request_id}`, Technical Support only, oldest first (`created_at`, then `id`). |
| D10 | **Messages:** 404 "Equipment requirement not found" / "Equipment not found" / "Venue not found"; 422 "Equipment type does not match the requirement"; 409 "Equipment not available", "Exceeds the equipment requirement", "Equipment no longer available"; shortfall 409 body `{"detail": {"message": "Insufficient equipment available", "requested": Q, "available": A, "shortfall": Q − A}}`. Amended 15 October 2026: the RPC's `22023` (D12) also maps to 422 "Equipment type does not match the requirement"; an empty RPC result maps to 500 "Database operation failed". |
| D11 | **Venue-locations contract** (added 15 October 2026). venueService exposes a read-only `GET /venues/locations` returning `[{"id", "name", "location"}]` for every venue, blocked venues included (a blocked room still locates the stock stored in it). Allowed for `technical_support`, `event_coordinator` and `venue_staff`; every other venue route keeps its guard, so Technical Support still gets 403 on `/venues`, `/venues/search`, `/venues/{id}`, blocks, suitability and booking routes. equipmentService calls it with the caller's token for this story and SCRUM-10's availability check. Rejected: adding `technical_support` to `require_venue_viewer` (grants the whole catalogue), a service credential (no service auth exists), reading `public.venues` directly (crosses the service boundary), copying venue buildings (goes stale). **Agreed by Jaren (SCRUM-39) and koeiloo23 / Kennedy (venue catalogue), 15 October 2026**; adds "venue locations (id, name, building)" to Technical Support's row in the SCRUM-39 role matrix. |
| D12 | **Type check under the lock** (added 15 October 2026). `reserve_equipment` (migration `0028`) refuses a catalogue row whose type differs from the requirement's, comparing as Python's `norm()` does: surrounding spaces trimmed, internal whitespace collapsed, case ignored. It raises SQLSTATE `22023` (`invalid_parameter_value`, a bad request rather than a lost race), which equipmentService maps to 422 "Equipment type does not match the requirement". The check runs after both rows are locked and before the status check, the same order as the API (D10). Known limit: SQL `lower()` and Python `casefold()` differ for a few non-ASCII letters (for example "ß"); equipment types are ASCII in practice. |

### Open questions

| ID | Question | Recommended answer |
| --- | --- | --- |
| Q1 | Should a reservation be refused when the event is Cancelled, Completed or Rejected? Technical Support cannot read event status. | **Not in this story.** Releasing reservations of cancelled events is backlog E1-2 (Q&A #60). |
| Q2 | What does SCRUM-58 mean by "equipment is reserved": reservations summing to each requirement's quantity, or the requirement marked `arranged`? | **Agree with SCRUM-58's owner.** This story exposes both: the reservation list and the requirement status. |
| Q3 | Should the dates come from the requirement's `event_date_times` snapshot instead of the body? | **No.** The snapshot holds candidate date-times and is not refreshed when the event changes (SCRUM-33 A3). |
| Q4 | Can Technical Support release or reduce a reservation? | **New backlog item.** Not in the Jira ACs. |
| Q5 | Frontend screen in this story? | **Separate story**, as SCRUM-10 and SCRUM-33 did. Backend only here. |

## Shared test data

Dates are October 2026: **Fri 9, Sat 10, Sun 11, Mon 12, Tue 13, Wed 14, Thu 15, Fri 16**.

**People.** `TSS` = `33333333-3333-3333-3333-333333333333` (Technical Support). `C1` = `11111111-1111-1111-1111-111111111111` (Event Coordinator).

**Events.** `E1` = the event being reserved for. `E2` = another event.

**Requirements** (`equipment_requirements` rows, status `requested`):

| Name | Event | Type | Quantity |
| --- | --- | --- | --- |
| `REQ1` | E1 | Projector | 5 |
| `REQ2` | E1 | Speaker | 2 |
| `REQ3` | E1 | Projector | 3 (a second Projector requirement, SCRUM-33 A1) |
| `REQB` | E2 | Projector | 10 |

**Catalogue rows** (`AVAILABLE` unless stated):

| Name | Type | Units | `home_location` |
| --- | --- | --- | --- |
| `P10` | Projector | 10 | Store Room B (store stock) |
| `PX` | Projector | 6 | Store Room C (store stock) |
| `PH10` | Projector | 10 | Harbour Room (another building: transfer day) |
| `PS10` | Projector | 10 | Search Small Room (same building as the event venue) |
| `S4` | Speaker | 4 | Store Room B |

**Venues:** SCRUM-10's `VENUES` (`v-big` Search Big Hall / Search Wing, `v-small` Search Small Room / Search Wing, `v-closed` Search Closed Hall / Search Wing, `v-harbour` Harbour Room / Harbour Block). The event venue is **`v-big`**.

**Reservation shorthand.** `R(row, qty, collect → return)` is an existing reservation for `E2` / `REQB` unless a requirement is named, e.g. `R(P10, 6, Tue 13 → Wed 14)`.

**Base request (`RES`):** `POST /equipment-reservations`, header `Authorization: Bearer staff-token` (authService stub returns roles `["technical_support"]`, id `TSS`), body `{"requirement_id": REQ1, "equipment_id": P10, "quantity": 5, "start_date": "2026-10-14", "end_date": "2026-10-14", "venue_id": "v-big"}`. Hold window for `P10`: Tue 13 → Wed 14.

"Nothing stored" means no insert and no `reserve_equipment` call reached the fake Supabase client.

## How the suites will run

| Area | Command | Notes |
| --- | --- | --- |
| Unit | `pytest tests/test_reservation_rules.py -q` | Pure row-availability function, no mocks |
| API | `pytest tests/test_reservations_api.py -q` | Fake Supabase that holds requirements, rows and reservations; authService and venueService stubbed at `httpx.get` (as SCRUM-10) |
| Whole service | `pytest -q` from `backend/equipmentService/` | SCRUM-10, -16, -33, -45 regression |
| venueService | `pytest -q tests/test_venue_locations.py` from `backend/venueService/` | AC1-X3 to X5 (D11) |
| Cross-service | `pytest -q tests/test_venue_contract.py` from `backend/equipmentService/` | AC1-X4, X6, X7. Starts the real venueService in a subprocess (in-memory store) and a fake authService; marker `cross_service`, included in plain `pytest` and CI |
| DB (manual) | `database/verify_equipment_reservation_writes.sql` in the Supabase SQL editor after `0027` and `0028` | One transaction, rolled back. AC3-N2 runs on a disposable PostgreSQL database (team convention for race tests, `database/README.md`) |
| Lint | `ruff check .` | |

## Acceptance-criterion test matrix

Layers: **Unit** = the row-availability function called directly; **API** = FastAPI `TestClient` with fakes; **DB** = manual SQL verification; **Integration** = full stack against the shared database.

### AC1: reservation against a recorded requirement

| ID | AC | Test scenario | Technique | Pre-conditions | Test steps | Test data | Expected result | Forbidden side effects | Layer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AC1-H1 | AC1, AC4 | Technical Support reserves units against a requirement | Happy | `REQ1`, `P10`; no reservations | Send `RES` | As `RES` | `201`; one `reserve_equipment` call with requirement `REQ1`, equipment `P10`, quantity 5, collection `2026-10-13`, return `2026-10-14`, created by `TSS` | Requirement row not updated; no eventRequestService call | API |
| AC1-P1 | AC1 | A user holding `technical_support` among other roles can reserve | Partition | As AC1-H1; authService returns roles `["event_operations_manager", "technical_support"]` | Send `RES` | — | `201` | — | API |
| AC1-P2 | AC1 | A requirement can be met from several rows (D2) | Partition | `REQ1` (5); `R(PX, 3, Tue 13 → Wed 14)` against `REQ1` / `E1` | Send `RES` | `quantity: 2` | `201` | — | API |
| AC1-P3 | AC1 | Row and requirement types match ignoring case and extra spaces | Partition | `REQ1` type "Projector"; row ×10 with type `"projector "` | Send `RES` with that row | — | `201` | — | API |
| AC1-B1 | AC1 | One below the requirement's outstanding quantity (D3) | Boundary | `REQ1` (5); `R(PX, 3, Tue 13 → Wed 14)` against `REQ1` (outstanding 2) | Send `RES` | `quantity: 1` | `201` | — | API |
| AC1-B2 | AC1 | Exactly the outstanding quantity | Boundary | As AC1-B1 | Send `RES` | `quantity: 2` | `201` | — | API |
| AC1-B3 | AC1 | One above the outstanding quantity | Boundary | As AC1-B1 | Send `RES` | `quantity: 3` | `409` "Exceeds the equipment requirement" | Nothing stored | API |
| AC1-B4 | AC1 | Quantity 0 is refused | Boundary | — | Send `RES` | `quantity: 0` | `422` | Nothing stored; no venueService call | API |
| AC1-N1 | AC1 | Invalid quantities are refused | Negative | — | Send `RES` (parametrized) | `-1`; `2.5`; `"five"`; `null` | `422` each | Nothing stored; no venueService call | API |
| AC1-N2 | AC1 | Missing or malformed fields are refused | Negative | — | Send `RES` (parametrized) | no `requirement_id`; `requirement_id: "abc"`; no `equipment_id`; `start_date: "14/10/2026"`; end Tue 13 before start Wed 14; no `venue_id` | `422` each | Nothing stored; no venueService call | API |
| AC1-N3 | AC1 | Unknown requirement | Negative | No requirement with that id | Send `RES` | `requirement_id` = random UUID | `404` "Equipment requirement not found" | Nothing stored | API |
| AC1-N4 | AC1 | Unknown catalogue row | Negative | `REQ1` | Send `RES` | `equipment_id` = random UUID | `404` "Equipment not found" | Nothing stored | API |
| AC1-N5 | AC1 | Row type differs from the requirement's type | Negative | `REQ1` (Projector); `S4` | Send `RES` | `equipment_id: S4`, `quantity: 2` | `422` "Equipment type does not match the requirement" | Nothing stored | API |
| AC1-N6 | AC1 | Unknown venue | Negative | venueService returns `VENUES` | Send `RES` | `venue_id: "v-missing"` | `404` "Venue not found" | Nothing stored | API |
| AC1-N7 | AC1 | venueService unreachable or failing | Negative | Stub raises `httpx.ConnectError`; separately returns `500` | Send `RES` (parametrized) | — | `502` "Venue service unavailable" each | Nothing stored | API |
| AC1-N8 | AC1 | Database failure is a clean 500 | Negative | Fake raises `APIError` (code `XX000`) on the requirement read; separately on the RPC | Send `RES` (parametrized) | — | `500` "Database operation failed" each | Nothing stored | API |
| AC1-N9 | AC1 | The stored reservation must name a real requirement | Negative | `0027` applied | Run the script | Insert with unknown `requirement_id`; with `NULL` | `23503`; `23502` | No row | DB |
| AC1-X1 | AC1 | Reserving requires a session | Cross-cutting | No `Authorization` header | Send `RES` | — | `401` | Nothing stored; no table queried | API |
| AC1-X2 | AC1 | Roles other than Technical Support may not reserve | Cross-cutting | authService returns the role | Send `RES` (parametrized) | `event_coordinator`; `venue_staff`; `attendee` | `403` "Insufficient permissions" each | Nothing stored; no table queried | API |
| AC1-N10 | AC1 | The RPC refuses a row of another type under the lock (D12) | Negative | `0028` applied; Projector requirement; `VERIFY-13 Speaker` row ×10 | Call `reserve_equipment` with the Speaker row | Quantity 1 | `22023` | No row inserted for the Speaker row | DB |
| AC1-N11 | AC1 | The RPC treats a type differing only by case and spacing as the same type (D12) | Partition | `0028` applied; row typed `'  verify-13   PROJECTOR '` | Call `reserve_equipment` with that row | Quantity 1 | Row returned | — | DB |
| AC1-N12 | AC1 | A type mismatch caught only under the lock is a 422, not a 500 | Negative | `REQ1`, `P10`; the fake RPC raises `22023` | Send `RES` | — | `422` "Equipment type does not match the requirement" | No reservation row | API |
| AC1-N13 | AC1 | An empty RPC result is a clean 500 | Negative | `REQ1`, `P10`; the fake RPC returns `[]` | Send `RES` | — | `500` "Database operation failed" | — | API |
| AC1-X3 | AC1 | Technical Support reads venue locations, and only id, name and location (D11) | Cross-cutting | venueService, in-memory store; two buildings, one blocked venue | `GET /venues/locations` as `technical_support`; also as `venue_staff` (route declared before `/{venue_id}`) | — | `200`; every seeded venue, blocked one included; each item's keys exactly `id`, `name`, `location`; no capacity, facilities, status or timestamps | — | API (venueService) |
| AC1-X4 | AC1 | Technical Support still cannot read the venue catalogue (D11) | Cross-cutting | As AC1-X3 | As `technical_support`: `GET /venues`, `/venues/search`, `/venues/{id}`, `/venues/{id}/blocks`, `POST /venues/{id}/suitability`, `GET /booking-requests`; and `GET /venues` against the real venueService over HTTP | — | `403` each | — | API (venueService); cross-service |
| AC1-X5 | AC1 | Who may read venue locations (D11) | Cross-cutting | As AC1-X3 | `GET /venues/locations` (parametrized) | `event_coordinator`; `venue_staff`; `event_operations_manager` + `technical_support` → allowed. `attendee`; `event_organiser`; `event_operations_manager` → refused. No session | `200` each allowed; `403` "Insufficient permissions" each refused; `401` without a session | — | API (venueService) |
| AC1-X6 | AC1, AC4 | Reserving works against the real venueService and its real role check (F1 regression) | Cross-cutting | venueService running for real (subprocess, in-memory store); fake authService over HTTP; equipmentService in-process with `ReservationStore` | `POST /equipment-reservations` as `technical_support` with `PH10`; with `PS10`; with `venue_id: "v-missing"` | Venue ids from the real service | `201` with collection `2026-10-12` (transfer day from real venue data); `201` with collection `2026-10-13`; `404` "Venue not found" | Nothing stored on the 404 | Cross-service |
| AC1-X7 | AC1 (SCRUM-10 regression) | SCRUM-10's availability check works against the real venueService | Cross-cutting | As AC1-X6 | `POST /equipment/availability-check` as `technical_support`, one Projector item | — | `200` (not `502`); `available` is a number | — | Cross-service |
| L1 | AC1–AC5 | Live authenticated workflow on the shared database | Integration | Branch head with `0028` applied; `docker compose up`; seeded test accounts; rows prefixed `MANUAL-13` | Steps L1-1 to L1-12 in the review-fixes plan §8.4 | — | Locations 200 and catalogue 403 for Technical Support; availability check 200; reservation 201 with the transfer day; list 200; over-reserve 409; type mismatch 422 (API) and `22023` (RPC); venue staff 403 | `MANUAL-13` rows cleaned up afterwards | Integration |

### AC2: only working equipment can be reserved

| ID | AC | Test scenario | Technique | Pre-conditions | Test steps | Test data | Expected result | Forbidden side effects | Layer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AC2-P1 | AC2 | `DAMAGED` row refused | Partition | `REQ1`; Projector row ×10 with the status; no reservations | Send `RES` with that row (parametrized) | — | `409` "Equipment not available" | Nothing stored | API |
| AC2-P2 | AC2 | `UNDER_REPAIR` row refused | Partition | As AC2-P1 | As AC2-P1 | — | As AC2-P1 | Nothing stored | API |
| AC2-P3 | AC2 | `UNDER_MAINTENANCE` row refused | Partition | As AC2-P1 | As AC2-P1 | — | As AC2-P1 | Nothing stored | API |
| AC2-P4 | AC2 | `RETIRED` row refused | Partition | As AC2-P1 | As AC2-P1 | — | As AC2-P1 | Nothing stored | API |
| AC2-X1 | AC2, AC4 | The status is checked on the chosen row, not the type: free `AVAILABLE` Projectors elsewhere do not let a damaged row through | Cross-cutting | `REQ1`; Projector row ×10 `DAMAGED`; `P10` free | Send `RES` with the damaged row | — | `409` "Equipment not available" | Nothing stored | API |
| AC2-N1 | AC2 | The row stops being available between the pre-check and the write (D6) | Negative | `REQ1`, `P10`; the fake RPC raises `P0004` | Send `RES` | — | `409` "Equipment no longer available" | No reservation row | API |
| AC2-N2 | AC2 | The RPC refuses a non-`AVAILABLE` row under the lock | Negative | `0027` applied; row set to `DAMAGED` in the script | Call `reserve_equipment` | Quantity 1 | `P0004` | No row inserted | DB |

### AC3: units committed to an overlapping hold are not offered again

Unit cases call the row-availability function with event venue `v-big`. "Clash" means 0 free, "free" means 10 free.

| ID | AC | Test scenario | Technique | Pre-conditions | Test steps | Test data | Expected result | Forbidden side effects | Layer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AC3-H1 | AC3 | Units reserved for an overlapping event are not offered; the rest are | Happy | `REQ1`; `R(P10, 6, Tue 13 → Wed 14)` | Send `RES` | `quantity: 4` | `201` | — | API |
| AC3-H2 | AC3 | The endpoint reads the row's reservations over its hold window | Happy | As AC3-H1 | Send `RES` | — | Reservation query filters `equipment_id = P10`, `collection_date <= 2026-10-14`, `return_date >= 2026-10-13` | No other row's reservations used | API |
| AC3-P1 | AC3 | A reservation outside the hold is ignored | Partition | `P10`; `R(P10, 10, Fri 30 → Sat 31)` | Call the function | Event Wed 14 | Free | — | Unit |
| AC3-P2 | AC3 | A reservation on another row of the same type is ignored | Partition | `P10`, `PX`; `R(PX, 6, Tue 13 → Wed 14)` | Call the function for `P10` | Event Wed 14 | Free | — | Unit |
| AC3-P3 | AC3 | Units held by another requirement of the **same** event still count | Partition | `REQ1`; `R(P10, 6, Tue 13 → Wed 14)` against `REQ3` / `E1` | Send `RES` | `quantity: 5` | `409`; available 4 | Nothing stored | API |
| AC3-P4 | AC3 | Busiest day, not the sum, of reservations that never overlap each other | Partition | `R(P10, 5, Mon 12 → Mon 12)`, `R(P10, 5, Fri 16 → Fri 16)` | Call the function | Event Mon 12 → Fri 16 | 5 free (not 0) | — | Unit |
| AC3-B1 | AC3 | An event the day after A's return collects on A's return day: clash | Boundary | `R(P10, 10, Sun 11 → Mon 12)` (event A on Mon 12) | Call the function | Event Tue 13 (hold Mon 12 → Tue 13) | Clash | — | Unit |
| AC3-B2 | AC3 | Return Day + 1 is the first free collection day | Boundary | As AC3-B1 | Call the function | Event Wed 14 (hold Tue 13 → Wed 14) | Free | — | Unit |
| AC3-B3 | AC3 | Event on A's collection day (D-1) clashes | Boundary | As AC3-B1 | Call the function | Event Sun 11 (hold Sat 10 → Sun 11) | Clash | — | Unit |
| AC3-B4 | AC3 | Event ending the day before A's collection is free | Boundary | As AC3-B1 | Call the function | Event Sat 10 (hold Fri 9 → Sat 10) | Free | — | Unit |
| AC3-B5 | AC3 | Transfer day: another-building row two days after A's return clashes | Boundary | `R(PH10, 10, Sat 10 → Mon 12)` | Call the function for `PH10` | Event Wed 14 (hold Mon 12 → Wed 14) | Clash | — | Unit |
| AC3-B6 | AC3 | Transfer day: three days after A's return is free | Boundary | As AC3-B5 | Call the function for `PH10` | Event Thu 15 (hold Tue 13 → Thu 15) | Free | — | Unit |
| AC3-N1 | AC3 | The RPC re-checks the peak under the lock | Negative | `0027` applied; 8 of a 10-unit row already reserved Tue 13 → Wed 14 | Call `reserve_equipment` for 5, Tue 13 → Wed 14 | — | `P0004` | No row inserted | DB |
| AC3-N2 | AC3 | Two staff reserving the last units at once: one wins, one is refused | Negative | `0027` applied; 10-unit row, no reservations; two SQL sessions | Session 1: `BEGIN`; reserve 6. Session 2: reserve 6 (waits). Session 1: `COMMIT` | — | Session 1 succeeds; session 2 gets `P0004`; 6 units reserved in total | Session 2 inserts nothing | DB (manual, two sessions) |
| AC3-X1 | AC3 | A stored reservation is seen by SCRUM-10's check and status | Cross-cutting | Full stack on the shared database; `MANUAL-` test rows | Reserve 5 of a 10-unit row for Wed 14; then `POST /equipment/availability-check` for an overlapping event; `GET /equipment/{id}/status` on a date inside the hold | — | Check reports 5 available; status reports `available_quantity` 5 on a day inside the hold | — | Integration |

### AC4: the reservation records equipment, quantity, event and period

| ID | AC | Test scenario | Technique | Pre-conditions | Test steps | Test data | Expected result | Forbidden side effects | Layer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AC4-H1 | AC4 | The response is the stored reservation | Happy | As AC1-H1; fake RPC returns the inserted row | Send `RES` | — | `201`; body has `id`, `requirement_id` `REQ1`, `event_request_id` `E1`, `equipment_id` `P10`, `quantity` 5, `collection_date` `2026-10-13`, `return_date` `2026-10-14`, `created_by` `TSS`, `created_at` | — | API |
| AC4-H2 | AC4 | The RPC stores every column and takes the event from the requirement | Happy | `0027` applied; one requirement for the script's event | Call `reserve_equipment` | Quantity 2, Tue 13 → Wed 14 | Row returned; `event_request_id` equals the requirement's event | — | DB |
| AC4-P1 | AC4 | Multi-day event: return date is the last day | Partition | `REQ1`, `P10` | Send `RES` | Wed 14 → Fri 16 | RPC gets collection `2026-10-13`, return `2026-10-16` | — | API |
| AC4-P2 | AC4 | Row in another building gets the transfer day (D5) | Partition | `REQ1`, `PH10` | Send `RES` | `equipment_id: PH10` | RPC gets collection `2026-10-12` | — | API |
| AC4-P3 | AC4 | Row in the event venue's building gets no transfer day | Partition | `REQ1`, `PS10` | Send `RES` | `equipment_id: PS10` | RPC gets collection `2026-10-13` | — | API |
| AC4-X1 | AC4 | The caller cannot choose the event; it comes from the requirement | Cross-cutting | `REQ1` | Send `RES` | Extra field `event_request_id: E2` | `422` | Nothing stored | API |
| AC4-X2 | AC4 | The caller cannot choose who made it; it is the session user | Cross-cutting | `REQ1` | Send `RES` | Extra field `created_by: C1` | `422` | Nothing stored | API |
| AC4-H3 | AC4 | Technical Support lists an event's reservations, oldest first | Happy | Three reservations for `E1` with different `created_at`, one for `E2` | `GET /equipment-reservations/by-event/{E1}` | — | `200`; the three `E1` rows, oldest first, each with all AC4-H1 fields | `E2` row absent | API |
| AC4-P4 | AC4 | An event with no reservations returns an empty list | Partition | No reservations for `E1` | `GET …/by-event/{E1}` | — | `200`; `[]` | — | API |
| AC4-N1 | AC4 | Malformed event id | Negative | — | `GET …/by-event/abc` | — | `422` | No table queried | API |
| AC4-X3 | AC4 | Only Technical Support may list reservations | Cross-cutting | — | `GET …/by-event/{E1}` (parametrized) | No session; `event_coordinator` | `401`; `403` | No table queried | API |

### AC5: a shortfall is refused and reported

Unless stated: `REQ1`, `R(P10, 6, Tue 13 → Wed 14)` so **A = 4** for `RES`.

| ID | AC | Test scenario | Technique | Pre-conditions | Test steps | Test data | Expected result | Forbidden side effects | Layer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AC5-H1 | AC5 | A request over what is free is refused with the numbers | Happy | `R(P10, 8, Tue 13 → Wed 14)` (A = 2) | Send `RES` | `quantity: 5` | `409`; `detail` = `{"message": "Insufficient equipment available", "requested": 5, "available": 2, "shortfall": 3}` | Nothing stored | API |
| AC5-B1 | AC5 | One more than available | Boundary | A = 4 | Send `RES` | `quantity: 5` | `409`; requested 5, available 4, shortfall 1 | Nothing stored | API |
| AC5-B2 | AC5 | Exactly what is available | Boundary | A = 4 | Send `RES` | `quantity: 4` | `201` | — | API |
| AC5-B3 | AC5 | One fewer than available | Boundary | A = 4 | Send `RES` | `quantity: 3` | `201` | — | API |
| AC5-P1 | AC5 | Nothing free: the shortfall is the whole request | Partition | `R(P10, 10, Tue 13 → Wed 14)` | Send `RES` | `quantity: 5` | `409`; requested 5, available 0, shortfall 5 | Nothing stored | API |
| AC5-P2 | AC5 | A shortfall on one requirement does not block another (Q&A #90) | Partition | A = 4 for `P10`; `REQ2`, `S4` free | Send `RES` (5 Projectors), then `RES` with `REQ2`, `S4`, quantity 2 | — | First `409`; second `201` | First call stores nothing | API |
| AC5-P3 | AC5 | Availability is the chosen row's, not the type's (D4) | Partition | A = 4 for `P10`; `PX` has 6 free | Send `RES` | `quantity: 5` | `409`; available 4 (not 10) | Nothing stored | API |
| AC5-X1 | AC5 | The reserve rule and SCRUM-10's check agree for a one-row catalogue | Cross-cutting | Each of AC3-P1, AC3-P4, AC3-B1, AC3-B5 setups | Call the row function and `check_availability` with the same inputs (parametrized) | — | Same available quantity each time | — | Unit |
| AC5-N1 | AC5 | A refused reservation leaves existing reservations unchanged | Negative | A = 4 | Send `RES` with `quantity: 5`, then list `E2`'s reservations | — | `409`; `E2` still holds exactly `R(P10, 6, …)` | No update or delete on any reservation | API |

## Test files

| File | Holds |
| --- | --- |
| `backend/equipmentService/tests/test_reservation_rules.py` | Unit cases for `row_available` |
| `backend/equipmentService/tests/test_reservations_api.py` | API cases for `POST /equipment-reservations` and `GET /equipment-reservations/by-event/{id}` |
| `backend/equipmentService/tests/reservations_support.py` | `ReservationStore` (fake Supabase that applies filters and simulates `reserve_equipment`), `Services` (authService and venueService stub; from 15 October 2026 it answers `GET /venues/locations`), shared data |
| `backend/venueService/tests/test_venue_locations.py` | AC1-X3 to X5: the `GET /venues/locations` contract and that Technical Support's catalogue access is not widened |
| `backend/equipmentService/tests/test_venue_contract.py` | AC1-X4, X6, X7: equipmentService against the real venueService and its real role check |
| `backend/equipmentService/tests/test_availability_check.py` | SCRUM-10's venue stub, updated to `GET /venues/locations` with this story's D11 |
| `database/verify_equipment_reservation_writes.sql` | DB cases AC1-N9, AC1-N10, AC1-N11, AC2-N2, AC3-N1, AC4-H2; manual two-session steps for AC3-N2 |
| `backend/equipmentService/app/availability.py` | `row_hold` and `row_available` — the implemented per-row rule; `check_availability` counts through `row_available`, so the reserve path and SCRUM-10's check share one rule (AC5-X1) |

## Disclosures

Recorded 15 October 2026, after the teammate review.

- **F1, venue reads refused (fixed by D11).** equipmentService forwarded the Technical Support token to venueService `GET /venues`, which since `6859656 fix(auth): restrict resource reads by role` (4 October 2026) admits only `event_coordinator` and `venue_staff`. venueService answered 403 and equipmentService reported 502 "Venue service unavailable", so every real `POST /equipment-reservations` failed. SCRUM-10's `POST /equipment/availability-check` (merged, Done) was broken the same way from 4 October until this fix.
- **F2, why CI missed it.** Both equipmentService venue stubs returned 200 for `/venues` whatever the caller's role, so they agreed with equipmentService rather than with venueService. AC1-X6 and AC1-X7 now run venueService's real permission code.
- **F3, type not checked in the database (fixed by D12).** `reserve_equipment` in `0027` did not compare the row's type with the requirement's; only the API did. Any other caller of the function could store one type against another type's requirement.
- **F4, evidence corrections.** The 14 October run cited `288daa9`, a pre-rebase commit no branch contains; it is corrected to `48638ce`. The 14 October Green runs were written and run by GLM (via Claude Code), run by Yang Xue, not by "Claude (Sonnet 5.5)".
- **F5, environments kept apart.** A disposable-PostgreSQL pass is not recorded as shared-Supabase verification (testing.md §8). AC3-N2 runs on a disposable database by team convention; the other DB cases run on shared Supabase.
- **F6, Red commits pushed.** `afc544c`, `6268726` and `ca03bed` committed Red tests on their own, against commits.md §4. They are already on the shared branch and are left as they are; from this round each test is committed with the change that makes it pass.

## Latest execution record

**Run 15 October 2026: review fixes (D11, D12) Red then Green, locally and on a disposable database.** Branch `feat/scrum-13-reserve-equipment`; Green results at `2822a9f` (dev `6b36647` merged in at `8a91d14`). Each fix was test-first: the tests were written and run Red, the fix was made, and test and fix were committed together (commits.md §4). Run by Claude (Cowork) for Yang Xue.

Environments, kept separate as testing.md §8 requires:
- **Local, mocked:** Linux (aarch64) workspace VM on Yang's Mac, Python 3.12.14 in a scratch virtual environment outside the repo, dependencies from each service's `pyproject.toml` (`.[dev]`).
- **Local, cross-service:** same VM; `tests/test_venue_contract.py` starts the real venueService (in-memory store) in a subprocess and a fake authService over HTTP; equipmentService in-process with `ReservationStore`.
- **Disposable PostgreSQL:** PostgreSQL 16.15 cluster created for this run in the Cowork cloud workspace (Ubuntu), migrations `0001`–`0028` applied on top of the team's auth test doubles (`anon`, `authenticated`, `service_role`, `auth.users`, as `database/tests/bootstrap_event_status_history.py`), then discarded. **Not shared Supabase.**

Commands and totals at `2822a9f`:
- equipmentService `pytest -q` → **330 passed, 0 failed** (323 before this round + AC1-N12, AC1-N13 and 5 cross-service tests); `ruff check .` clean.
- venueService `pytest -q` → **371 passed, 0 failed** (360 before + 11); `ruff check .` clean.
- equipmentService `pytest -q tests/test_venue_contract.py` → 5 passed in under 1 s.

| ID | Automation status | Actual result | Execution status | Build or commit | Executed by and date | Remarks and evidence |
| --- | --- | --- | --- | --- | --- | --- |
| AC1-X3, AC1-X5 | Red | `403` for `technical_support`; `404` "Venue not found" for `venue_staff`, `event_coordinator` and multi-role (the path matched `GET /venues/{venue_id}`): 6 failed | Fail (expected) | `00e0571` + new test file, Local, mocked | Claude (Cowork), 15 Oct 2026 | `backend/venueService`: `pytest -q tests/test_venue_locations.py`. The refusal and no-session cases and AC1-X4 already passed (5) |
| AC1-X3, AC1-X4, AC1-X5 | Green | 11 passed | Pass | `98b6eaa` and `2822a9f`, Local, mocked | Claude (Cowork), 15 Oct 2026 | As above |
| AC1-X6, AC1-X7 | Red | `502` "Venue service unavailable" (F1 reproduced, with Part A already in place): 4 failed; AC1-X4 cross-service passed | Fail (expected) | `98b6eaa` + new test file, Local, cross-service | Claude (Cowork), 15 Oct 2026 | `pytest -q tests/test_venue_contract.py` |
| Stub change (SCRUM-10 and SCRUM-13 API suites) | Red | Stubs updated to `/venues/locations` before the client: 46 failed with `AssertionError: unexpected GET …/venues` | Fail (expected) | `98b6eaa` + working tree, Local, mocked | Claude (Cowork), 15 Oct 2026 | `pytest -q` |
| AC1-X4, AC1-X6, AC1-X7 | Green | 5 passed | Pass | `7879164` and `2822a9f`, Local, cross-service | Claude (Cowork), 15 Oct 2026 | `pytest -q tests/test_venue_contract.py` |
| AC1-N12 | Red | `500` "Database operation failed" | Fail (expected) | `7879164` + working tree, Local, mocked | Claude (Cowork), 15 Oct 2026 | `pytest -q tests/test_reservations_api.py` |
| AC1-N13 | Red | `IndexError: list index out of range` | Fail (expected) | `8fb14f3` + working tree, Local, mocked | Claude (Cowork), 15 Oct 2026 | As above |
| AC1-N12, AC1-N13 and every 14 Oct unit and API case | Green | 73 passed (13 unit, 60 API) | Pass | `2822a9f`, Local, mocked | Claude (Cowork), 15 Oct 2026 | `pytest -q tests/test_reservation_rules.py tests/test_reservations_api.py` |
| AC1-N10 | Red | Script stopped at `AC1-N10: a Speaker row must not be reserved against a Projector requirement` (the function stored the row) | Fail (expected) | Migrations `0001`–`0027`, verify script at `8fb14f3`, Disposable PostgreSQL 16.15 | Claude (Cowork), 15 Oct 2026 | `verify_equipment_reservation_writes.sql` |
| AC1-N9, AC1-N10, AC1-N11, AC2-N2, AC3-N1, AC4-H2 | Green | `ALL EQUIPMENT RESERVATION WRITE VERIFICATIONS PASSED`; `0028` re-run safe | Pass | `8fb14f3`, migrations `0001`–`0028`, Disposable PostgreSQL 16.15 | Claude (Cowork), 15 Oct 2026 | Supplementary only; shared Supabase is the environment of record for these rows (below). SCRUM-10's `verify_equipment_reservations.sql` also passed. `routine_privileges` for `reserve_equipment`: `service_role` and the owner only |
| AC3-N2 | Green | Session 2 waited on the lock, then failed with `P0004` ("exceeds requirement"); 6 units reserved in total | Pass | `8fb14f3`, migrations `0001`–`0028`, Disposable PostgreSQL 16.15 | Claude (Cowork), 15 Oct 2026 | Race test, local by team convention (`database/README.md`). Two `psql` sessions; session 1 held its transaction open with `pg_sleep(2)`. Re-run after `0028`, which changed the function. The teammate's earlier disposable-PostgreSQL run (before `0028`) is not committed on the branch, so it is not recorded here |
| AC1-N9, AC1-N10, AC1-N11, AC2-N2, AC3-N1, AC4-H2 | Planned | — | Not executed | — | — | **Shared Supabase dev, SQL Editor**: owner step. Run the verify script once before applying `0028` (expected Red at AC1-N10), apply `0028`, run both verify scripts, check the grants, and screenshot into `docs/testcases/screenshots/scrum_13/` (plan §6.5) |
| AC3-X1, L1 | Planned | — | Not executed | — | — | **Live stack on shared Supabase**: owner step after `0028` is applied (plan §8.4) |
| PR CI | Planned | — | Not executed | — | — | GitHub Actions on the PR head once pushed |

**Run 14 October 2026: Green (unit and API; implementation on the branch).** Branch `feat/scrum-13-reserve-equipment` at `48638ce` (dev at `11dae05` plus this story's commits; corrected 15 October 2026 from `288daa9`, a pre-rebase commit no branch contains). Environment: macOS (Darwin 24.6.0) on Yang's Mac, Python 3.14.2 in `backend/equipmentService/.venv`, dependencies from `pyproject.toml` (`.[dev]`). Dependencies **fully mocked**: `ReservationStore` for Supabase; authService and venueService stubbed at `httpx.get`. Migration `0027` was applied to shared development on 14 October 2026, after this run; the DB-layer cases and AC3-X1 are not executed yet.

Commands from `backend/equipmentService/`:
- `pytest -q` → **323 passed, 0 failed, 0 skipped** (one pre-existing starlette `DeprecationWarning` from the test client, present before this story).
- `ruff check .` → all checks passed.

| ID | Automation status | Actual result | Execution status | Build or commit | Executed by and date | Remarks and evidence |
| --- | --- | --- | --- | --- | --- | --- |
| AC3-P1, AC3-P2, AC3-P4, AC3-B1–B6, AC5-X1 | Green | 13 runs pass | Pass | `48638ce`, Local, mocked | GLM (via Claude Code), run by Yang Xue, 14 Oct 2026 | `pytest -q tests/test_reservation_rules.py` |
| AC1-H1, AC1-P1–P3, AC1-B1–B4, AC1-N1–N8, AC1-X1, AC1-X2, AC2-P1–P4, AC2-X1, AC2-N1, AC3-H1, AC3-H2, AC3-P3, AC4-H1, AC4-H3, AC4-P1–P4, AC4-N1, AC4-X1–X3, AC5-H1, AC5-B1–B3, AC5-P1–P3, AC5-N1 | Green | 58 runs pass | Pass | `48638ce`, Local, mocked | GLM (via Claude Code), run by Yang Xue, 14 Oct 2026 | `pytest -q tests/test_reservations_api.py` |
| AC1-N9, AC2-N2, AC3-N1, AC4-H2 | Planned | — | Not executed | — | — | `database/verify_equipment_reservation_writes.sql` after `0027` is applied; expected Red before that (column `requirement_id` / function `reserve_equipment` missing) |
| AC3-N2 | Planned | — | Not executed | — | — | Manual, two SQL sessions; steps at the end of the verify script |
| AC3-X1 | Planned | — | Not executed | — | — | Manual integration on the full stack once `0027` is applied |
| SCRUM-10/16/33/45 regression | Green | 252 existing tests pass | Pass | `48638ce`, Local, mocked | GLM (via Claude Code), run by Yang Xue, 14 Oct 2026 | `pytest -q` |

**Run 12 October 2026: Red (tests written, behaviour not implemented).** `dev` at `dd0036b` plus the uncommitted SCRUM-13 test files. Environment: Linux workspace VM on Yang's Mac, Python 3.13.15 in a scratch virtual environment outside the repo, dependencies from `pyproject.toml` (`.[dev]`). Dependencies **fully mocked**: `ReservationStore` for Supabase; authService and venueService stubbed at `httpx.get`. `POST /equipment-reservations` and `GET /equipment-reservations/by-event/{id}` do not exist yet; `row_available` is a stub.

Commands from `backend/equipmentService/`:
- `pytest -q tests/test_reservation_rules.py tests/test_reservations_api.py` → **71 failed, 0 passed**. Every failure is the intended one: 13 `NotImplementedError` (unit) and 58 `404 Not Found` from the missing routes (API).
- `pytest -q` → **71 failed, 252 passed, 0 skipped**. The 252 are the existing SCRUM-10, -16, -33, -45 tests, unchanged.
- `ruff check .` → all checks passed.

| ID | Automation status | Actual result | Execution status | Build or commit | Executed by and date | Remarks and evidence |
| --- | --- | --- | --- | --- | --- | --- |
| AC3-P1, AC3-P2, AC3-P4, AC3-B1–B6, AC5-X1 | Red | `NotImplementedError` (13 test runs) | Fail (expected) | `dd0036b` + uncommitted | Claude (Cowork), 12 Oct 2026 | `tests/test_reservation_rules.py` |
| AC1-H1, AC1-P1–P3, AC1-B1–B4, AC1-N1–N8, AC1-X1, AC1-X2, AC2-P1–P4, AC2-X1, AC2-N1, AC3-H1, AC3-H2, AC3-P3, AC4-H1, AC4-H3, AC4-P1–P4, AC4-N1, AC4-X1–X3, AC5-H1, AC5-B1–B3, AC5-P1–P3, AC5-N1 | Red | `404 Not Found`: route missing (58 test runs) | Fail (expected) | `dd0036b` + uncommitted | Claude (Cowork), 12 Oct 2026 | `tests/test_reservations_api.py` |
| AC1-N9, AC2-N2, AC3-N1, AC4-H2 | Planned | — | Not executed | — | — | `database/verify_equipment_reservation_writes.sql`; expected Red before `0027`: column `requirement_id` / function `reserve_equipment` does not exist |
| AC3-N2 | Planned | — | Not executed | — | — | Manual, two SQL sessions; steps at the end of the verify script |
| AC3-X1 | Planned | — | Not executed | — | — | Manual integration on the full stack after implementation |
| SCRUM-10/16/33/45 regression | Green | 252 existing tests pass | Pass | `dd0036b` + uncommitted | Claude (Cowork), 12 Oct 2026 | `pytest -q` |

Traceability: a script comparing this matrix with the test files found all 61 IDs in a test or the SQL script except AC3-X1 (manual integration, by design), and no unknown IDs.

### Regression to watch

Migration `0027` makes `requirement_id` NOT NULL, so SCRUM-10's `database/verify_equipment_reservations.sql` (which inserts reservations without a requirement) must be updated to insert one in the same change, or it will fail.

## Review

| Reviewed by | Date | Outcome |
| --- | --- | --- |
| — | — | Pending story-owner approval (testing.md §1) and team review (testing.md §10) |
