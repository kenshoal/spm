# SCRUM-33 Implementation Plan: Record Equipment Requirements for an Event

Drafted 6 October 2026 by Claude (Cowork) for Yang Xue (story owner). **Status: Gate 0 approved by Yang Xue on 6 October 2026** (AC1–AC7, D1–D8, A1–A5, and the recommended answers to Q1–Q3). Leg 1 in progress.

**Goal:** an assigned Event Coordinator records the equipment an event needs (type, quantity, technical requirements); Technical Support Staff see every recorded requirement and update it as arrangements are made.

**Branch:** `feat/scrum-33-equipment-requirements` (from `origin/dev` at `6673a21`). PR into `dev`.

**Architecture decision (agreed 6 Oct):** equipmentService owns a new `equipment_requirements` table. It does **not** read `event_coordinator_assignments`; it asks eventRequestService with the caller's own token, exactly as venueService does for SCRUM-32 (`backend/venueService/app/event_requests.py`):

1. `GET /event-requests/{id}/coordinator` and compare `coordinator_id` to the caller's id (a 200 alone is not proof: the owning organiser, and after SCRUM-39 any same-organisation organiser, also get 200).
2. On record only, `GET /event-requests/{id}` for the event status and the snapshot (name, proposed date-times).

Technical Support never calls eventRequestService (it returns 403 for `technical_support`); the snapshot on the row is what they see.

**Dependencies and related stories**

| Story | Relationship |
| --- | --- |
| SCRUM-13 Reserve Equipment (Yang) | Blocked by this story. Its AC1 reserves "against an equipment requirement", so it will add a `requirement_id` to `equipment_reservations`. Not done here. |
| SCRUM-39 Restrict Data Access (Jaren) | Unmerged (`feat/scoped-resource-access`). Touches equipmentService `deps.py`, `equipment.py`, `status.py` and adds `EVENT_COORDINATOR_ROLE`. Merge `dev` in once it lands; do not redefine the constant. Its rule "Technical Support: equipment requirements and reservations" is what AC4 implements. |
| SCRUM-10 (merged) | Supplies `norm()` for type matching and the catalogue conventions. |
| SCRUM-32 (Kennedy) | Template for the event client, test layout and evidence format. |

---

## Gate 0: AC review (approved by Yang Xue, 6 October 2026)

Issue tracker criteria read on 6 October 2026, reviewed with `docs/standards/testing.md` §1.

| issue tracker criterion | Outcome | Reason |
| --- | --- | --- |
| J1 "The Coordinator can record required equipment for an event, including type, quantity, and relevant technical requirements." | **Clarify, Split** → AC1, AC2 | "Type" and valid quantity are undefined; the happy path and input rules are independently testable. |
| J2 "Given a recorded requirement, when saved, then it is associated with the event and visible to Technical Support Staff for review." | **Split** → AC3, AC4 | Association (per-event list) and the Technical Support review queue are separate behaviours. |
| J3 "Technical Support Staff can review and update the request as arrangements are made." | **Clarify** → AC5 | "Update" is undefined: which fields, which states, who records it. |
| none | **Add** → AC6 | Relationship access (assigned Coordinator only) is required by SCRUM-39 and `security-and-state.md`. |
| none | **Add** → AC7 | Recording equipment for a closed event is a business-rule exception that needs a stated outcome. |

### Proposed acceptance criteria

- **AC1** Given a Coordinator currently assigned to an event, when they record a requirement with an equipment type, a quantity and optional technical requirements, then it is stored linked to that event with status `requested`, recorded by that Coordinator, with a snapshot of the event's name and proposed date-times.
- **AC2** Given a requirement being recorded, when the type does not match a non-retired catalogue type (ignoring case and extra spaces), the quantity is not a whole number of at least 1, or the technical requirements exceed 2,000 characters, then it is refused (422) and nothing is stored.
- **AC3** Given recorded requirements for an event, when the assigned Coordinator or Technical Support lists that event's requirements or opens one, then each shows its type, quantity, technical requirements, status, support note, event snapshot, recorder and times, oldest first.
- **AC4** Given recorded requirements across events, when Technical Support opens the review queue, then requirements with the chosen status (default `requested`) from every event appear oldest first, each identifying its event.
- **AC5** Given a requirement, when Technical Support updates its arrangement status and support note along an allowed transition, then the change is stored with who made it and when, and the Coordinator sees it; a disallowed or stale update is refused (409) and leaves the row unchanged.
- **AC6** Given a caller who is not the Coordinator currently assigned to the event, when they record or read that event's requirements, then they get 404 (indistinguishable from a missing event) and nothing is stored; callers without the required role get 403; only Technical Support may update arrangements.
- **AC7** Given an event whose status is Cancelled, Completed or Rejected, when its assigned Coordinator records a requirement, then it is refused (409) and nothing is stored.

### Decisions proposed with the review

| ID | Decision |
| --- | --- |
| D1 | Type is the catalogue `equipment.type`, matched with SCRUM-10's `norm()`; the stored value is the catalogue's spelling. A type whose only rows are `RETIRED` is unknown. Damaged or under-repair types are accepted: availability is SCRUM-13. |
| D2 | Quantity may exceed what is owned; the shortfall is reported by SCRUM-13, not refused here. |
| D3 | Arrangement statuses: `requested` → `in_progress` → `arranged`, plus `requested` → `arranged`, `arranged` → `in_progress` (an arrangement fell through) and `in_progress` → `in_progress` (note-only update, note required). Nothing returns to `requested`; no other self-transition. |
| D4 | The update body carries `expected_status`; the database function locks the row (`FOR UPDATE`) and refuses if the current status differs (stale action), using the team's error codes: `P0002` not found → 404, `P0004` transition not allowed → 409. |
| D5 | The row keeps `updated_by` / `updated_at` for the latest arrangement change; no separate history table (Q2). |
| D6 | The Technical Support queue and reads are role-wide, as SCRUM-39 states, until individual staff assignment exists. |
| D7 | Coordinator access follows the **current** assignment: after reassignment the former Coordinator loses access and the new one gains it. `recorded_by` still names who recorded it. |
| D8 | Check order on record: 401 → 403 (role) → 422 (body) → assignment check (404 / 401 / 502) → event status (409) → catalogue type (422) → insert. |

### Assumptions and open questions

| ID | Item | Used by |
| --- | --- | --- |
| A1 | Two requirements of the same type for one event may coexist (as SCRUM-32 AC4). | AC1-P4 |
| A2 | Draft events cannot have an assigned Coordinator, so no Draft case is needed. | AC7 |
| A3 | Snapshot = `event_name` and `proposed_date_times`; it is not refreshed when the event changes. | AC1, AC3-X1 |
| A4 | `recorded_by` / `updated_by` are plain `uuid` columns without a foreign key, as in `equipment` and `equipment_reservations`. | AC1, AC5 |
| A5 | Path ids use FastAPI `UUID` like the rest of equipmentService, so a malformed id is 422. | AC3-N2 |
| Q1 | Should the Coordinator be able to edit or withdraw a requirement while it is `requested`? **Recommended: no, new backlog item**, to keep this story proportional. | scope |
| Q2 | Is a full arrangement history needed (one row per change), or is latest-change-only enough? **Recommended: latest only** (D5). | AC5 |
| Q3 | Frontend screens (Coordinator form on `/coordination`, queue on `/equipment`)? **Recommended: separate story**, as SCRUM-32 did; this plan is backend only. | scope |

### Included and excluded

| | Behaviour | issue tracker |
| --- | --- | --- |
| Included | `equipment_requirements` table, transition function, server-only access; record, list, queue, read-one and arrangement-update endpoints; event client | SCRUM-33 |
| Excluded | Reserving units and linking reservations to requirements | SCRUM-13 |
| Excluded | Coordinator edit/withdraw (Q1), notifications, frontend (Q3) | none yet |

---

## Endpoints under test (all in equipmentService)

| Endpoint | Caller | Purpose |
| --- | --- | --- |
| `POST /equipment-requirements` | `event_coordinator` (assigned) | Body: `event_request_id`, `equipment_type`, `quantity`, `technical_requirements?`. Extra fields forbidden. 201. |
| `GET /equipment-requirements/by-event/{event_request_id}` | assigned `event_coordinator`, any `technical_support` | One event's requirements, oldest first. Declared before `/{id}`. |
| `GET /equipment-requirements/{id}` | assigned `event_coordinator`, any `technical_support` | One requirement. |
| `GET /equipment-requirements?status=` | `technical_support` | Review queue, default `requested`, oldest first. |
| `PATCH /equipment-requirements/{id}/arrangement` | `technical_support` | Body: `expected_status`, `status`, `support_note?`. Calls `transition_equipment_requirement`. |

## Test data used throughout

| Name | Value |
| --- | --- |
| Coordinator C1 (caller in most API cases) | `11111111-1111-1111-1111-111111111111` (`USER_ID` in `conftest.py`) |
| Coordinator C2 | `22222222-2222-2222-2222-222222222222` |
| Event E1 | `aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1`, "Annual Gala", status `Under Review`, proposed `2027-03-15T09:00:00+08:00`, assigned to C1 |
| Catalogue | `Projector` ×10 AVAILABLE; `Wireless Microphone` ×4 DAMAGED; `Fog Machine` ×2 RETIRED (only row of that type) |
| Manual accounts | `event_coordinator1@example.com`, `event_coordinator2@example.com`, `technical_support@example.com`, `event_organiser@example.com`, password `12345678` (`database/seed_test_accounts.sql`) |

"Nothing stored" in an API case means `FakeSupabase.inserts` and `rpc_calls` are empty. "No lookup" means the fake eventRequestService received no request.

---

## Test cases

### Database layer: `database/verify_equipment_requirements.sql`

Needs `0021_equipment_requirements.sql` applied and one `auth.users` row; one transaction, rolled back. Run by Yang in the Supabase SQL Editor (shared dev project).

| ID | AC | Scenario | Technique | Steps / data | Expected result | Forbidden side effects |
| --- | --- | --- | --- | --- | --- | --- |
| AC1-H1 | AC1 | Minimal row defaults correctly | Happy | Insert event, `Projector`, qty 1, `recorded_by` | Stored; status `requested`; `recorded_at` set; `technical_requirements`, `support_note`, `updated_by`, `updated_at` NULL | none |
| AC1-H2 | AC1, AC3 | Technical requirements and snapshot round-trip | Happy | Insert with "HDMI, 4K", name "Annual Gala", two date-times; read back | Values returned unchanged | none |
| AC1-N1 | AC1 | Unknown event refused | Negative | random `event_request_id` | `23503` | no row |
| AC1-N2 to AC1-N5 | AC1 | Required columns | Negative | NULL `event_request_id`; NULL `equipment_type`; NULL `quantity`; NULL `recorded_by` | `23502` each | no row |
| AC1-X1 | AC1 | An event with requirements cannot be deleted | Cross-cutting | Delete the event row | `23503` | event and requirement remain |
| AC2-B1 | AC2 | Quantity just below minimum | Boundary | qty 0 | `23514` | no row |
| AC2-B2 | AC2 | Quantity at minimum | Boundary | qty 1 | stored | none |
| AC2-B3 | AC2 | Quantity just above minimum | Boundary | qty 2 | stored | none |
| AC2-N1 | AC2 | Blank type refused | Negative | `'   '` | `23514` | no row |
| AC2-B4 | AC2 | Technical requirements at limit | Boundary | 2,000 chars | stored | none |
| AC2-B5 | AC2 | Technical requirements over limit | Boundary | 2,001 chars | `23514` | no row |
| AC5-P1 to AC5-P3 | AC5 | Each status value storable with consistent audit fields | Partition | `requested` (audit NULL); `in_progress` and `arranged` (audit set) | stored | none |
| AC5-N1 | AC5 | Unknown status refused | Negative | `cancelled` | `23514` | no row |
| AC5-N2 | AC5 | Non-`requested` status without `updated_by` refused | Negative | `in_progress`, `updated_by` NULL | `23514` | no row |
| AC5-N3 | AC5 | `updated_by` without `updated_at` refused | Negative | `updated_at` NULL | `23514` | no row |
| AC5-H1 | AC5 | Function moves `requested` → `in_progress` with note | Happy | `transition_equipment_requirement(id, 'requested', 'in_progress', 'Sourcing spare', staff)` | Row returned; status, note, `updated_by`, `updated_at` set; type, qty, snapshot unchanged | none |
| AC5-P4 to AC5-P7 | AC5 | Allowed transitions (D3) | Partition | `requested`→`arranged`; `in_progress`→`arranged`; `arranged`→`in_progress`; `in_progress`→`in_progress` with new note | Each succeeds | none |
| AC5-N4 to AC5-N7 | AC5 | Disallowed transitions | Negative | `requested`→`requested`; `arranged`→`arranged`; `in_progress`→`requested`; `arranged`→`requested` | `P0004` each | row unchanged |
| AC5-N8 | AC5 | Stale update refused | Negative | Row is `in_progress`; call with expected `requested` → `arranged` | `P0004` | row unchanged |
| AC5-N9 | AC5 | Unknown requirement | Negative | random id | `P0002` | none |
| AC5-N10 | AC5 | Note-only update without a note | Negative | `in_progress`→`in_progress`, note NULL; then `'  '` | `P0004` each | row unchanged |
| AC5-X1 | AC5 | Support note over limit | Cross-cutting | 2,001-char note | `23514` | row unchanged |
| AC5-X2 | AC5 | The function locks the row | Cross-cutting | `pg_get_functiondef` contains `FOR UPDATE` | true | none |
| AC4-X1 | AC3, AC4 | Lookup indexes exist | Cross-cutting | `pg_indexes` | `(event_request_id, recorded_at, id)` and `(status, recorded_at, id)` present | none |
| AC6-X1 | AC6 | Browser roles have no table privilege | Cross-cutting | `has_table_privilege` for `anon`, `authenticated` × SELECT/INSERT/UPDATE/DELETE | all 8 false | none |
| AC6-X2 | AC6 | RLS enabled | Cross-cutting | `relrowsecurity` | true | none |
| AC6-X3 | AC6 | Service role can SELECT, INSERT, UPDATE | Cross-cutting | `has_table_privilege('service_role', …)` | 3 true | none |
| AC6-X4 | AC6 | Only the service role executes the function | Cross-cutting | `has_function_privilege` for `anon`, `authenticated`, `service_role` | false, false, true | none |

### Unit layer: event client, `tests/test_event_requests_client.py`

Uses an injectable `httpx.MockTransport`, as venueService's event client does. Test-design choice: the auth fixtures in `conftest.py` replace `httpx.get` wholesale, so a client built on `httpx.get` would need a URL-routing stub like `test_availability_check.py` uses for SCRUM-10. An injectable transport leaves the existing auth fixtures untouched.

| ID | AC | Scenario | Technique | Steps / data | Expected result | Forbidden side effects |
| --- | --- | --- | --- | --- | --- | --- |
| AC6-X5 | AC6 | Caller's token forwarded, assignment compared | Cross-cutting | `snapshot_for_coordinator(E1, "abc", C1)` | `GET /event-requests/E1/coordinator` then `GET /event-requests/E1`, both `Authorization: Bearer abc`; returns name, date-times, status | no service credential sent |
| AC6-X6 | AC6 | Different `coordinator_id` means not assigned | Cross-cutting | assignment C2, caller C1 | 404 "Event request not found"; second GET not made | event body not read |
| AC6-X7 | AC6 | `assert_assigned` (read path) makes only the assignment call | Cross-cutting | assigned | one GET to `/coordinator` | no `GET /event-requests/{id}` |
| AC6-N1 | AC6 | 403 or 404 from eventRequestService becomes 404 | Negative | each status | 404 "Event request not found" | none |
| AC6-N2 | AC6 | 401 passes through | Negative | 401 | 401 "Invalid session" | none |
| AC6-N3 | AC6 | Unavailable service | Negative | connect error; timeout; 500 | 502 "Event request service unavailable" | none |
| AC6-N4 | AC6 | Malformed replies | Negative | non-JSON; list body; no `coordinator_id`; event body without `status` | 502 | none |
| AC6-N5 | AC6 | Unset URL setting | Negative | `EVENT_REQUEST_SERVICE_URL` invalid | 503 "Service is not configured" | no request |

### API layer: record, `tests/test_requirements_record.py`

| ID | AC | Scenario | Technique | Steps / data | Expected result | Forbidden side effects |
| --- | --- | --- | --- | --- | --- | --- |
| AC1-H3 | AC1 | Assigned Coordinator records a requirement | Happy | C1 posts E1, `Projector`, 2, "HDMI, 4K" | 201; all fields echoed; status `requested`; `recorded_by` C1 from token; `event_name` "Annual Gala"; date-times echoed; audit fields null; exactly one insert with exactly the expected columns | no second insert, no rpc |
| AC1-H4 | AC1 | Technical requirements optional | Happy | omit field | 201, `technical_requirements` null | none |
| AC1-P1 | AC1, AC2 | Type matched ignoring case and spaces, stored in catalogue spelling | Partition | `"  projector "` | 201, `equipment_type` "Projector" | none |
| AC1-P2 | AC1 | A type with only damaged units is accepted (D1) | Partition | `Wireless Microphone` | 201 | none |
| AC1-P3 | AC1 | Quantity above owned is accepted (D2) | Partition | `Projector`, 50 | 201 | none |
| AC1-P4 | AC1 | Second requirement of same type coexists (A1) | Partition | post twice | both 201, different ids | none |
| AC1-P5 to AC1-P10 | AC1, AC7 | Every open event status accepted | Partition | event status `Submitted`, `Under Review`, `Changes Requested`, `Approved`, `Planning`, `Confirmed` | 201 each | none |
| AC1-N6 to AC1-N9 | AC1 | Server-owned fields cannot be set | Negative | add `recorded_by`; `status: "arranged"`; `event_name`; `support_note` | 422 `extra_forbidden` | nothing stored, no lookup |
| AC1-N10 | AC1, AC6 | No bearer token | Negative | no `Authorization` | 401 "Authentication required" | nothing stored, no lookup |
| AC1-X2 | AC1 | Store failure is not reported as created | Cross-cutting | insert raises `APIError` | 500 "Database operation failed" | no 201 |
| AC2-B6 | AC2 | Quantity 0 | Boundary | 0 | 422 on `body.quantity` | nothing stored, no lookup |
| AC2-B7 | AC2 | Quantity 1 | Boundary | 1 | 201 | none |
| AC2-B8 | AC2 | Quantity at integer max | Boundary | 2147483647 | 201 | none |
| AC2-B9 | AC2 | Quantity above integer max | Boundary | 2147483648 | 422 | nothing stored |
| AC2-N2 to AC2-N5 | AC2 | Quantity not a whole number | Negative | `"abc"`; 1.5; null; omitted | 422 | nothing stored, no lookup |
| AC2-N6 to AC2-N8 | AC2 | Type missing, null or blank | Negative | omitted; null; `"   "` | 422 | nothing stored, no lookup |
| AC2-N9 | AC2 | Type not in catalogue | Negative | `Hologram` | 422 "Unknown equipment type" | nothing stored |
| AC2-N10 | AC2 | Retired-only type is unknown (D1) | Negative | `Fog Machine` | 422 "Unknown equipment type" | nothing stored |
| AC2-B10 | AC2 | Technical requirements at limit | Boundary | 2,000 chars | 201 | none |
| AC2-B11 | AC2 | Technical requirements over limit | Boundary | 2,001 chars | 422 | nothing stored, no lookup |
| AC2-P1 | AC2 | Blank technical requirements stored as none | Partition | `"   "` | 201, null | none |
| AC2-N11, AC2-N12 | AC2 | Event reference invalid | Negative | `"not-a-uuid"`; omitted | 422 | nothing stored, no lookup |
| AC7-N1 to AC7-N3 | AC7 | Closed events refused | Negative | event status `Cancelled`; `Completed`; `Rejected` | 409 "Event is closed" | nothing stored |
| AC6-X8 | AC6 | Unassigned Coordinator | Cross-cutting | E1 assigned to C2 | 404 "Event request not found" | nothing stored |
| AC6-X9 | AC6 | Event with no Coordinator yet | Cross-cutting | `/coordinator` answers 404 | 404, body identical to AC6-X8 | nothing stored |
| AC6-X10 | AC6 | Event that does not exist | Cross-cutting | both GETs 404 | 404, body identical to AC6-X8 | nothing stored |
| AC6-X11 | AC6 | Owning organiser who also holds the coordinator role but is not assigned | Cross-cutting | roles `[event_organiser, event_coordinator]`; `/coordinator` 200 with C2 | 404 | nothing stored |
| AC6-X12 to AC6-X16 | AC6 | Other roles cannot record | Cross-cutting | `technical_support`; `event_organiser`; `venue_staff`; `event_operations_manager`; `attendee` | 403 "Insufficient permissions" | nothing stored, no lookup |
| AC6-N6 | AC6 | Event service down on record | Negative | connection error | 502 | nothing stored |
| AC6-N7 | AC6 | Event service 401 on record | Negative | 401 | 401 "Invalid session" | nothing stored |

### API layer: reads, `tests/test_requirements_read.py`

Rows are seeded in `FakeSupabase.table_data["equipment_requirements"]`.

| ID | AC | Scenario | Technique | Steps / data | Expected result | Forbidden side effects |
| --- | --- | --- | --- | --- | --- | --- |
| AC3-H1 | AC3 | Assigned Coordinator lists an event's requirements | Happy | two rows for E1 | 200, both, every field; query filters `event_request_id=E1`, orders `recorded_at`, `id` ascending | none |
| AC3-H2 | AC3 | Technical Support lists the same without asking eventRequestService | Happy | as AC3-H1 as `technical_support` | 200, same items | no lookup |
| AC3-H3 | AC3 | Assigned Coordinator opens one | Happy | one row | 200, every field | none |
| AC3-H4 | AC3 | Technical Support opens one | Happy | one row | 200 | no lookup |
| AC3-B1 | AC3 | Event with no requirements | Boundary | no rows | 200 `[]` | none |
| AC3-X1 | AC3 | Snapshot comes from the row, not a fresh event read | Cross-cutting | row name "Annual Gala"; fake event now "Gala 2027" | "Annual Gala" | no `GET /event-requests/{id}` |
| AC3-N1 | AC3 | Unknown id | Negative | random uuid | 404 "Equipment requirement not found" | none |
| AC3-N2 | AC3 | Malformed id (A5) | Negative | `not-a-uuid` | 422 | no store query |
| AC4-H1 | AC4 | Default queue shows only `requested`, oldest first, with event reference and name | Happy | query recorded | filter `status=requested`, order `recorded_at`, `id` asc; each item has `event_request_id`, `event_name` | none |
| AC4-P1, AC4-P2 | AC4 | Status filter | Partition | `?status=in_progress`; `?status=arranged` | filter sent with that value | none |
| AC4-B1 | AC4 | Empty queue | Boundary | no rows | 200 `[]` | none |
| AC4-N1 | AC4 | Unknown status filter | Negative | `?status=cancelled` | 422 | no store query |
| AC6-X17, AC6-X18 | AC6 | Coordinators and organisers cannot read the queue | Cross-cutting | `event_coordinator`; `event_organiser` | 403 | no data |
| AC6-X19 | AC6 | Unassigned Coordinator cannot list or open | Cross-cutting | E1 assigned to C2 | 404 for list and one, identical to unknown | no data |
| AC6-X20 | AC6 | Reassignment moves access (D7) | Cross-cutting | row recorded by C1; E1 now assigned to C2 | C1 → 404; C2 → 200 with `recorded_by` C1 | none |
| AC6-X21 | AC6 | Organiser who owns the event cannot read | Cross-cutting | `event_organiser` | 403 on list and one | no data |
| AC6-X22 | AC6 | No token on every read | Cross-cutting | queue, by-event, one | 401 each | no data |
| AC6-N8 | AC6 | Event service down on a Coordinator read | Negative | connection error | 502 | no data |

### API layer: arrangement, `tests/test_requirements_arrangement.py`

The transition table lives in the database function (one source of truth, under the row lock); these cases prove the API contract and error mapping.

| ID | AC | Scenario | Technique | Steps / data | Expected result | Forbidden side effects |
| --- | --- | --- | --- | --- | --- | --- |
| AC5-H2 | AC5 | Technical Support moves a requirement to `in_progress` | Happy | `{expected_status: requested, status: in_progress, support_note: "Sourcing spare"}` | 200 with updated row; rpc `transition_equipment_requirement` called once with id, both statuses, note and `p_updated_by` = caller | no table insert |
| AC5-P8 | AC5 | Multi-role staff can update | Partition | roles `[event_operations_manager, technical_support]` | 200 | none |
| AC5-X3 | AC5 | Coordinator sees the update | Cross-cutting | seeded row `in_progress`, note, `updated_by`; GET as assigned C1 | status, note, `updated_by`, `updated_at` returned | none |
| AC5-N11 | AC5 | Disallowed or stale transition | Negative | rpc raises `P0004` | 409 "Transition not allowed" | none |
| AC5-N12 | AC5 | Unknown requirement | Negative | rpc raises `P0002` | 404 "Equipment requirement not found" | none |
| AC5-N13 | AC5 | Other database error | Negative | rpc raises other `APIError` | 500 "Database operation failed" | none |
| AC5-N14 | AC5 | Unknown status | Negative | `status: done` | 422 | no rpc |
| AC5-N15 | AC5 | `expected_status` missing | Negative | omitted | 422 | no rpc |
| AC5-N16 | AC5 | Note over limit | Negative | 2,001 chars | 422 | no rpc |
| AC5-N17 to AC5-N19 | AC5 | Coordinator-owned or server fields cannot be changed | Negative | add `quantity`; `equipment_type`; `updated_by` | 422 `extra_forbidden` | no rpc |
| AC6-X23, AC6-X24 | AC6 | Only Technical Support updates | Cross-cutting | assigned `event_coordinator`; `event_organiser` | 403 | no rpc |
| AC6-X25 | AC6 | No token | Cross-cutting | none | 401 | no rpc |

### Integration layer (manual, Leg 2, Docker Compose stack + shared dev database)

Seed: one event `MANUAL-S33 Gala` submitted by `event_organiser@example.com` and assigned to `event_coordinator1@example.com`; catalogue row `MANUAL-S33 Projector`. Cleanup SQL removes every `MANUAL-S33` row afterwards.

| ID | AC | Scenario | Steps | Expected result |
| --- | --- | --- | --- | --- |
| AC1-X3 | AC1 | Real record through real services | Log in as coordinator1; `POST /equipment-requirements` qty 2 | 201; row in Supabase with snapshot "MANUAL-S33 Gala" |
| AC6-X26 | AC6 | Real unassigned Coordinator | Same body as coordinator2 | 404; no new row |
| AC4-X2 | AC4 | Real queue | Log in as technical_support; `GET /equipment-requirements` | the row is listed |
| AC5-X4 | AC5 | Real transitions and Coordinator view | TSS: `requested`→`in_progress`→`arranged`; repeat the last call | 200, 200, then 409; coordinator1 GET shows `arranged` with TSS as `updated_by` |
| AC6-X27 | AC6 | Browser key blocked | `GET /rest/v1/equipment_requirements` with the publishable key | 401, `42501` |

**Totals:** 101 matrix rows: 28 database, 8 client unit, 30 record, 18 read, 12 arrangement, 5 manual integration. Ranges expand to more individual checks. IDs are unique across layers and never reused.

---

## Leg 1: build and document every test (no production behaviour)

Starts after Gate 0 is approved. Ends with every automated test written, failing for the intended reason, and recorded.

- [x] **1.1 Story contract and matrix.** Create `docs/testcases/scrum_33_testcases.md` in the SCRUM-32 format: story table, approved AC review, decisions D1–D8, assumptions and questions, the full specification matrix above (with the Pre-conditions and Layer columns), and an empty execution record.
- [x] **1.2 Database verification script.** Write `database/verify_equipment_requirements.sql` (one `DO` block per case, `RAISE EXCEPTION` on failure, final `NOTICE`, `ROLLBACK`), modelled on `verify_equipment_reservations.sql`, with each case labelled `-- AC5-N8 (negative): …`.
- [x] **1.3 Contract stubs, so Red is a real Red.** `testing.md` §5 says an import error is not a valid Red. Add only signatures, no behaviour:
  - `app/event_requests_client.py`: `EventRequestClient(base_url, transport=None)` with `snapshot_for_coordinator` and `assert_assigned` raising `NotImplementedError`; `get_event_request_client()` dependency.
  - `event_request_service_url` in `app/config.py` (default `http://127.0.0.1:8003`).
  - No router is registered, so every endpoint test fails with 404/405 for the missing behaviour.
- [x] **1.4 Test helpers.** `tests/requirements_support.py`: a fake eventRequestService (`httpx.MockTransport`) whose assignment, event status/body and failure mode each test sets; fixtures for C1, C2, roles and seeded rows; extend `FakeSupabase` so `insert` and `rpc` can raise `APIError`. Import it as `requirements_support`, not `tests.requirements_support` (SCRUM-32 failed CI on that because CI runs plain `pytest`).
- [x] **1.5 Write the four test files** listed above, one label comment per test (`# AC2-B6 (boundary): …`), parametrized ranges with `ids=[…]`.
- [ ] **1.6 Run Red and record it.** Automated part done 6 Oct (102 failed for the intended reason, 146 existing passed); Supabase SQL Editor run pending Yang.
  - `cd backend/equipmentService && .venv/bin/ruff check . && .venv/bin/python -m pytest -q` and plain `pytest -q`: expected every new test to fail (endpoints 404/405, client `NotImplementedError`) and every existing test to pass. Any new test that passes or errors during collection is a defect in the test.
  - Yang runs the verification script in the SQL Editor **before** `0021` exists: expected stop during compilation, before AC1-H1, with `42P01 relation "public.equipment_requirements" does not exist` (the precedent from SCRUM-10 and SCRUM-32).
  - Record `Red` with command, counts and commit/working tree in the execution record.
- [x] **1.7 Human review of the test design** (`testing.md` §10): Yang, ideally plus one teammate for AC6. Record the reviewer and date in Disclosures.
  - Done 7 October 2026: Yang Xue reviewed and approved the test cases, including D9 and D10. Recorded in Disclosures. A teammate review for AC6 remains optional and outstanding.
- [x] **1.8 Commit the documents only:** `docs(scrum-33): record story contract and test design`. Test files (and the stub and conftest changes) stay uncommitted (or committed locally, never pushed) until they pass, because `commits.md` §4 forbids pushing a red commit.
  - Done 7 October 2026: commit `ad6f5ca` (testcases doc + plan doc). The verify SQL script follows the SCRUM-32 precedent and will be committed with the 0021 migration in 2.1.

**Leg 1 exit:** Gate 0 approved; matrix complete; all automated tests Red for the right reason; DB script Red at `42P01`; review recorded; docs commit pushed.

---

## Leg 2: implement to Green, integrate, evidence, PR

One behaviour slice per commit; each commit carries its tests and passes on its own.

- [ ] **2.1 Database.** `database/migrations/0021_equipment_requirements.sql`: table, CHECKs, indexes, RLS, `REVOKE` from `anon`/`authenticated`, grants to `service_role`; `transition_equipment_requirement(p_requirement_id, p_expected_status, p_new_status, p_support_note, p_updated_by)` with `FOR UPDATE`, `P0002`/`P0004`, `REVOKE EXECUTE … FROM PUBLIC, anon, authenticated`, `GRANT EXECUTE … TO service_role`, fixed `search_path` (as 0015). Yang applies it to the shared dev project and re-runs the script → Green. Update `database/README.md`. Commit `feat(database): add equipment_requirements and its transition function (SCRUM-33)`.
- [ ] **2.2 Event client.** Implement the stubs, add `EVENT_REQUEST_SERVICE_URL: http://event-request-service:8000` to `equipment-service` in `docker-compose.yaml` (no `depends_on`, like venue-service). Client tests Green. Commit `feat(equipment): ask eventRequestService who coordinates an event (SCRUM-33)`.
- [ ] **2.3 Record.** `app/routers/requirements.py` `POST`, catalogue match through `norm()`, check order D8. Record and AC7 tests Green. Commit `feat(equipment): coordinators record equipment requirements (SCRUM-33)`.
- [ ] **2.4 Reads and queue.** Read tests Green. Commit `feat(equipment): list equipment requirements by event and for review (SCRUM-33)`.
- [ ] **2.5 Arrangement update.** Add a requirement-specific RPC error mapper (the current `rpc_error_to_http` hard-codes "Equipment not found"). Arrangement tests Green. Commit `feat(equipment): technical support updates arrangement status (SCRUM-33)`.
- [ ] **2.6 Refactor and whole-suite check.** `ruff check .`, `python -m pytest -q` and plain `pytest -q` in equipmentService; eventRequestService suite unchanged. Manual mutation check, each must turn at least one test red:

  | Mutant | Expected catcher |
  | --- | --- |
  | M1 assignment compared with `==` instead of `!=` | AC1-H3, AC6-X8 |
  | M2 request body allows extra fields | AC1-N6 |
  | M3 coordinator role check removed on POST | AC6-X12 |
  | M4 Technical Support shortcut applied to coordinators on reads | AC6-X19 |
  | M5 `quantity` `ge=0` | AC2-B6 |
  | M6 `Rejected` missing from closed statuses | AC7-N3 |
  | M7 token not forwarded | AC6-X5 |
  | M8 queue default `in_progress` | AC4-H1 |
  | M9 type compared case-sensitively | AC1-P1 |
  | M10 retired rows counted as catalogue types | AC2-N10 |
  | M11 `expected_status` check removed in SQL | AC5-N8 |
  | M12 `FOR UPDATE` removed in SQL | AC5-X2 |

- [ ] **2.7 Manual integration** on `docker compose up --build -d` against the shared database: the five manual cases, seed and cleanup SQL kept outside the repo as for SCRUM-10.
- [ ] **2.8 Documentation.** equipmentService README endpoint section; `docs/event-domain-boundaries.md` (Technical Support access now covers requirements; the service-to-service link list); Postman collection under `docs/postman`; fill the execution record and "Latest verification". Commit `docs(scrum-33): record green test evidence and endpoint docs`.
- [ ] **2.9 Sync and PR.** If SCRUM-39 has merged, `git merge dev` with message `chore: merge dev into feat/scrum-33-equipment-requirements` and re-run 2.6. Push, open PR into `dev` with the nine sections from `commits.md` §6, confirm CI (`Lint and test equipmentService`, conventional commits).
- [ ] **2.10 Done check** against `definition-of-done.md`; move SCRUM-33 to Done only after merge and integrated-stack run; unblock SCRUM-13.

## Risks

| Risk | Handling |
| --- | --- |
| A reassignment between the assignment check and the insert | Cannot be tested at this layer; recorded as a known limit, as in SCRUM-32. |
| SCRUM-39 merge conflicts in equipmentService | Rebase plan in 2.9; keep edits to `deps.py` minimal. |
| eventRequestService contract changes (e.g. SCRUM-39 alters `/coordinator`) | AC6-X5/X6 pin the contract; re-run after merging dev. |
| `FakeSupabase` does not persist inserts | Reads are seeded explicitly; the manual run proves the real round-trip. |
