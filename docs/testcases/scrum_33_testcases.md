# SCRUM-33 Test Cases: Record Equipment Requirements for an Event

Last reviewed: 6 October 2026

Status: **the AC review below was approved as proposed by the story owner (Yang Xue) on 6 October 2026**, including decisions D1 to D8, assumptions A1 to A5 and the recommended answers to Q1 to Q3. D9 and D10 were added while writing the tests and approved by Yang Xue on 7 October 2026. Leg 1 (tests first) is in progress; no production behaviour exists yet. Plan: [`docs/superpowers/plans/2026-10-06-scrum-33-equipment-requirements.md`](../superpowers/plans/2026-10-06-scrum-33-equipment-requirements.md).

## Story

| Field | Value |
| --- | --- |
| Jira key | SCRUM-33 |
| Title | Record Equipment Requirements for an Event |
| User story | As an Event Coordinator, I want to record the equipment an event requires, so that Technical Support Staff can review and arrange it. |
| Blocks | SCRUM-13 Reserve Equipment for an Event |

## Story contract

Jira criteria read on 6 October 2026, reviewed with `docs/standards/testing.md` §1.

| Jira criterion | Outcome | Reason |
| --- | --- | --- |
| J1 "The Coordinator can record required equipment for an event, including type, quantity, and relevant technical requirements." | **Clarify, Split** → AC1, AC2 | "Type" and valid quantity are undefined; the happy path and input rules are independently testable. |
| J2 "Given a recorded requirement, when saved, then it is associated with the event and visible to Technical Support Staff for review." | **Split** → AC3, AC4 | Association (per-event list) and the Technical Support review queue are separate behaviours. |
| J3 "Technical Support Staff can review and update the request as arrangements are made." | **Clarify** → AC5 | "Update" is undefined: which fields, which states, who records it. |
| none | **Add** → AC6 | Relationship access (assigned Coordinator only) is required by SCRUM-39 and `security-and-state.md`. |
| none | **Add** → AC7 | Recording equipment for a closed event is a business-rule exception that needs a stated outcome. |

### Acceptance criteria

- **AC1** Given a Coordinator currently assigned to an event, when they record a requirement with an equipment type, a quantity and optional technical requirements, then it is stored linked to that event with status `requested`, recorded by that Coordinator, with a snapshot of the event's name and proposed date-times.
- **AC2** Given a requirement being recorded, when the type does not match a non-retired catalogue type (ignoring case and extra spaces), the quantity is not a whole number of at least 1, or the technical requirements exceed 2,000 characters, then it is refused (422) and nothing is stored.
- **AC3** Given recorded requirements for an event, when the assigned Coordinator or Technical Support lists that event's requirements or opens one, then each shows its type, quantity, technical requirements, status, support note, event snapshot, recorder and times, oldest first.
- **AC4** Given recorded requirements across events, when Technical Support opens the review queue, then requirements with the chosen status (default `requested`) from every event appear oldest first, each identifying its event.
- **AC5** Given a requirement, when Technical Support updates its arrangement status and support note along an allowed transition, then the change is stored with who made it and when, and the Coordinator sees it; a disallowed or stale update is refused (409) and leaves the row unchanged.
- **AC6** Given a caller who is not the Coordinator currently assigned to the event, when they record or read that event's requirements, then they get 404 (indistinguishable from a missing event) and nothing is stored; callers without the required role get 403; only Technical Support may update arrangements.
- **AC7** Given an event whose status is Cancelled, Completed or Rejected, when its assigned Coordinator records a requirement, then it is refused (409) and nothing is stored.

### Decisions

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
| D9 | On an arrangement update, a blank or omitted support note keeps the existing note; a non-blank note replaces it. |
| D10 | Opening one requirement as an unassigned Coordinator returns the same 404 as an unknown requirement ("Equipment requirement not found"); listing an unassigned event returns the same 404 as an unknown event ("Event request not found"). |

### Included and excluded behaviour

| | Behaviour | Jira |
|

### Actors and relationship permissions

- **Event Coordinator:** records requirements for, and reads the requirements of, events they are currently assigned to. Checked through eventRequestService (`GET /event-requests/{id}/coordinator`, comparing `coordinator_id` to the caller) with the caller's own token. Cannot update arrangements.
- **Technical Support Staff:** reads every requirement and the review queue (role-wide, as SCRUM-39 states) and updates arrangement status and notes. Never calls eventRequestService. Cannot record requirements.
- **Everyone else** (organisers, Venue Staff, Operations Managers, attendees): 403. No browser role reaches the table or the function.

### State transitions

| From | To | Allowed |
| --- | --- | --- |
| `requested` | `in_progress`, `arranged` | yes |
| `in_progress` | `arranged`; `in_progress` (note-only, note required) | yes |
| `arranged` | `in_progress` | yes |
| any | `requested` | no |
| `requested` | `requested`; `arranged` → `arranged` | no |

Each update names the status it expects to find; a mismatch is a stale action and is refused.

### Persistence and atomicity

- Recording is a single-row insert. The status, note, `updated_by` and `updated_at` change together inside `transition_equipment_requirement`, which locks the row (`FOR UPDATE`) and checks the expected status before writing.
- Error codes follow the team convention: `P0002` not found (404), `P0004` transition not allowed (409).

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

## Endpoints under test

| Endpoint | Caller | Purpose |
| --- | --- | --- |
| `POST /equipment-requirements` | `event_coordinator` (assigned) | Body: `event_request_id`, `equipment_type`, `quantity`, `technical_requirements?`. Extra fields forbidden. 201. |
| `GET /equipment-requirements/by-event/{event_request_id}` | assigned `event_coordinator`, any `technical_support` | One event's requirements, oldest first. Declared before `/{id}`. |
| `GET /equipment-requirements/{id}` | assigned `event_coordinator`, any `technical_support` | One requirement. |
| `GET /equipment-requirements?status=` | `technical_support` | Review queue, default `requested`, oldest first. |
| `PATCH /equipment-requirements/{id}/arrangement` | `technical_support` | Body: `expected_status`, `status`, `support_note?`. Calls `transition_equipment_requirement`. |

## Test data

| Name | Value |
|

"Nothing stored" in an API case means the fake Supabase client recorded no insert and no RPC call. "No lookup" means the fake eventRequestService received no request.

## Test-case matrix

A row with an ID range is one parametrized test (or one loop in the SQL script) whose cases carry those IDs.

### Specification: Database layer

Automated in `database/verify_equipment_requirements.sql`.

| ID | AC | Test scenario | Technique | Pre-conditions | Test steps | Test data | Expected result | Forbidden side effects | Layer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AC1-H1 | AC1 | Minimal row defaults correctly | Happy | `0021` applied; the script's setup event and one `auth.users` row | Run the script; the case's statement | Insert event, `Projector`, qty 1, `recorded_by` | Stored; status `requested`; `recorded_at` set; `technical_requirements`, `support_note`, `updated_by`, `updated_at` NULL | none | DB |
| AC1-H2 | AC1, AC3 | Technical requirements and snapshot round-trip | Happy | `0021` applied; the script's setup event and one `auth.users` row | Run the script; the case's statement | Insert with "HDMI, 4K", name "Annual Gala", two date-times; read back | Values returned unchanged | none | DB |
| AC1-N1 | AC1 | Unknown event refused | Negative | `0021` applied; the script's setup event and one `auth.users` row | Run the script; the case's statement | random `event_request_id` | `23503` | no row | DB |
| AC1-N2 to AC1-N5 | AC1 | Required columns | Negative | `0021` applied; the script's setup event and one `auth.users` row | Run the script; the case's statement | NULL `event_request_id`; NULL `equipment_type`; NULL `quantity`; NULL `recorded_by` | `23502` each | no row | DB |
| AC1-X1 | AC1 | An event with requirements cannot be deleted | Cross-cutting | `0021` applied; the script's setup event and one `auth.users` row | Run the script; the case's statement | Delete the event row | `23503` | event and requirement remain | DB |
| AC2-B1 | AC2 | Quantity just below minimum | Boundary | `0021` applied; the script's setup event and one `auth.users` row | Run the script; the case's statement | qty 0 | `23514` | no row | DB |
| AC2-B2 | AC2 | Quantity at minimum | Boundary | `0021` applied; the script's setup event and one `auth.users` row | Run the script; the case's statement | qty 1 | stored | none | DB |
| AC2-B3 | AC2 | Quantity just above minimum | Boundary | `0021` applied; the script's setup event and one `auth.users` row | Run the script; the case's statement | qty 2 | stored | none | DB |
| AC2-N1 | AC2 | Blank type refused | Negative | `0021` applied; the script's setup event and one `auth.users` row | Run the script; the case's statement | `'   '` | `23514` | no row | DB |
| AC2-B4 | AC2 | Technical requirements at limit | Boundary | `0021` applied; the script's setup event and one `auth.users` row | Run the script; the case's statement | 2,000 chars | stored | none | DB |
| AC2-B5 | AC2 | Technical requirements over limit | Boundary | `0021` applied; the script's setup event and one `auth.users` row | Run the script; the case's statement | 2,001 chars | `23514` | no row | DB |
| AC5-P1 to AC5-P3 | AC5 | Each status value storable with consistent audit fields | Partition | `0021` applied; the script's setup event and one `auth.users` row | Run the script; the case's statement | `requested` (audit NULL); `in_progress` and `arranged` (audit set) | stored | none | DB |
| AC5-N1 | AC5 | Unknown status refused | Negative | `0021` applied; the script's setup event and one `auth.users` row | Run the script; the case's statement | `cancelled` | `23514` | no row | DB |
| AC5-N2 | AC5 | Non-`requested` status without `updated_by` refused | Negative | `0021` applied; the script's setup event and one `auth.users` row | Run the script; the case's statement | `in_progress`, `updated_by` NULL | `23514` | no row | DB |
| AC5-N3 | AC5 | `updated_by` without `updated_at` refused | Negative | `0021` applied; the script's setup event and one `auth.users` row | Run the script; the case's statement | `updated_at` NULL | `23514` | no row | DB |
| AC5-H1 | AC5 | Function moves `requested` → `in_progress` with note | Happy | `0021` applied; the script's setup event and one `auth.users` row | Run the script; the case's statement | `transition_equipment_requirement(id, 'requested', 'in_progress', 'Sourcing spare', staff)` | Row returned; status, note, `updated_by`, `updated_at` set; type, qty, snapshot unchanged | none | DB |
| AC5-P4 to AC5-P7 | AC5 | Allowed transitions (D3) | Partition | `0021` applied; the script's setup event and one `auth.users` row | Run the script; the case's statement | `requested`→`arranged`; `in_progress`→`arranged`; `arranged`→`in_progress`; `in_progress`→`in_progress` with new note | Each succeeds | none | DB |
| AC5-N4 to AC5-N7 | AC5 | Disallowed transitions | Negative | `0021` applied; the script's setup event and one `auth.users` row | Run the script; the case's statement | `requested`→`requested`; `arranged`→`arranged`; `in_progress`→`requested`; `arranged`→`requested` | `P0004` each | row unchanged | DB |
| AC5-N8 | AC5 | Stale update refused | Negative | `0021` applied; the script's setup event and one `auth.users` row | Run the script; the case's statement | Row is `in_progress`; call with expected `requested` → `arranged` | `P0004` | row unchanged | DB |
| AC5-N9 | AC5 | Unknown requirement | Negative | `0021` applied; the script's setup event and one `auth.users` row | Run the script; the case's statement | random id | `P0002` | none | DB |
| AC5-N10 | AC5 | Note-only update without a note | Negative | `0021` applied; the script's setup event and one `auth.users` row | Run the script; the case's statement | `in_progress`→`in_progress`, note NULL; then `'  '` | `P0004` each | row unchanged | DB |
| AC5-X1 | AC5 | Support note over limit | Cross-cutting | `0021` applied; the script's setup event and one `auth.users` row | Run the script; the case's statement | 2,001-char note | `23514` | row unchanged | DB |
| AC5-X2 | AC5 | The function locks the row | Cross-cutting | `0021` applied; the script's setup event and one `auth.users` row | Run the script; the case's statement | `pg_get_functiondef` contains `FOR UPDATE` | true | none | DB |
| AC4-X1 | AC3, AC4 | Lookup indexes exist | Cross-cutting | `0021` applied; the script's setup event and one `auth.users` row | Run the script; the case's statement | `pg_indexes` | `(event_request_id, recorded_at, id)` and `(status, recorded_at, id)` present | none | DB |
| AC6-X1 | AC6 | Browser roles have no table privilege | Cross-cutting | `0021` applied; the script's setup event and one `auth.users` row | Run the script; the case's statement | `has_table_privilege` for `anon`, `authenticated` × SELECT/INSERT/UPDATE/DELETE | all 8 false | none | DB |
| AC6-X2 | AC6 | RLS enabled | Cross-cutting | `0021` applied; the script's setup event and one `auth.users` row | Run the script; the case's statement | `relrowsecurity` | true | none | DB |
| AC6-X3 | AC6 | Service role can SELECT, INSERT, UPDATE | Cross-cutting | `0021` applied; the script's setup event and one `auth.users` row | Run the script; the case's statement | `has_table_privilege('service_role', …)` | 3 true | none | DB |
| AC6-X4 | AC6 | Only the service role executes the function | Cross-cutting | `0021` applied; the script's setup event and one `auth.users` row | Run the script; the case's statement | `has_function_privilege` for `anon`, `authenticated`, `service_role` | false, false, true | none | DB |

### Specification: Unit layer: event client

Automated in `backend/equipmentService/tests/test_event_requests_client.py`.

| ID | AC | Test scenario | Technique | Pre-conditions | Test steps | Test data | Expected result | Forbidden side effects | Layer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AC6-X5 | AC6 | Caller's token forwarded, assignment compared | Cross-cutting | `EventRequestClient` over `httpx.MockTransport` (fake eventRequestService) | Call the client | `snapshot_for_coordinator(E1, "abc", C1)` | `GET /event-requests/E1/coordinator` then `GET /event-requests/E1`, both `Authorization: Bearer abc`; returns name, date-times, status | no service credential sent | Unit |
| AC6-X6 | AC6 | Different `coordinator_id` means not assigned | Cross-cutting | `EventRequestClient` over `httpx.MockTransport` (fake eventRequestService) | Call the client | assignment C2, caller C1 | 404 "Event request not found"; second GET not made | event body not read | Unit |
| AC6-X7 | AC6 | `assert_assigned` (read path) makes only the assignment call | Cross-cutting | `EventRequestClient` over `httpx.MockTransport` (fake eventRequestService) | Call the client | assigned | one GET to `/coordinator` | no `GET /event-requests/{id}` | Unit |
| AC6-N1 | AC6 | 403 or 404 from eventRequestService becomes 404 | Negative | `EventRequestClient` over `httpx.MockTransport` (fake eventRequestService) | Call the client | each status | 404 "Event request not found" | none | Unit |
| AC6-N2 | AC6 | 401 passes through | Negative | `EventRequestClient` over `httpx.MockTransport` (fake eventRequestService) | Call the client | 401 | 401 "Invalid session" | none | Unit |
| AC6-N3 | AC6 | Unavailable service | Negative | `EventRequestClient` over `httpx.MockTransport` (fake eventRequestService) | Call the client | connect error; timeout; 500 | 502 "Event request service unavailable" | none | Unit |
| AC6-N4 | AC6 | Malformed replies | Negative | `EventRequestClient` over `httpx.MockTransport` (fake eventRequestService) | Call the client | non-JSON; list body; no `coordinator_id`; event body without `status` | 502 | none | Unit |
| AC6-N5 | AC6 | Unset URL setting | Negative | `EventRequestClient` over `httpx.MockTransport` (fake eventRequestService) | Call the client | `EVENT_REQUEST_SERVICE_URL` invalid | 503 "Service is not configured" | no request | Unit |

### Specification: API layer: record

Automated in `backend/equipmentService/tests/test_requirements_record.py`.

| ID | AC | Test scenario | Technique | Pre-conditions | Test steps | Test data | Expected result | Forbidden side effects | Layer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AC1-H3 | AC1 | Assigned Coordinator records a requirement | Happy | Fake eventRequestService: E1 assigned to C1, status `Under Review`; catalogue seeded; caller C1 (`event_coordinator`) unless stated | `POST /equipment-requirements` | C1 posts E1, `Projector`, 2, "HDMI, 4K" | 201; all fields echoed; status `requested`; `recorded_by` C1 from token; `event_name` "Annual Gala"; date-times echoed; audit fields null; exactly one insert with exactly the expected columns | no second insert, no rpc | API |
| AC1-H4 | AC1 | Technical requirements optional | Happy | Fake eventRequestService: E1 assigned to C1, status `Under Review`; catalogue seeded; caller C1 (`event_coordinator`) unless stated | `POST /equipment-requirements` | omit field | 201, `technical_requirements` null | none | API |
| AC1-P1 | AC1, AC2 | Type matched ignoring case and spaces, stored in catalogue spelling | Partition | Fake eventRequestService: E1 assigned to C1, status `Under Review`; catalogue seeded; caller C1 (`event_coordinator`) unless stated | `POST /equipment-requirements` | `"  projector "` | 201, `equipment_type` "Projector" | none | API |
| AC1-P2 | AC1 | A type with only damaged units is accepted (D1) | Partition | Fake eventRequestService: E1 assigned to C1, status `Under Review`; catalogue seeded; caller C1 (`event_coordinator`) unless stated | `POST /equipment-requirements` | `Wireless Microphone` | 201 | none | API |
| AC1-P3 | AC1 | Quantity above owned is accepted (D2) | Partition | Fake eventRequestService: E1 assigned to C1, status `Under Review`; catalogue seeded; caller C1 (`event_coordinator`) unless stated | `POST /equipment-requirements` | `Projector`, 50 | 201 | none | API |
| AC1-P4 | AC1 | Second requirement of same type coexists (A1) | Partition | Fake eventRequestService: E1 assigned to C1, status `Under Review`; catalogue seeded; caller C1 (`event_coordinator`) unless stated | `POST /equipment-requirements` | post twice | both 201, different ids | none | API |
| AC1-P5 to AC1-P10 | AC1, AC7 | Every open event status accepted | Partition | Fake eventRequestService: E1 assigned to C1, status `Under Review`; catalogue seeded; caller C1 (`event_coordinator`) unless stated | `POST /equipment-requirements` | event status `Submitted`, `Under Review`, `Changes Requested`, `Approved`, `Planning`, `Confirmed` | 201 each | none | API |
| AC1-N6 to AC1-N9 | AC1 | Server-owned fields cannot be set | Negative | Fake eventRequestService: E1 assigned to C1, status `Under Review`; catalogue seeded; caller C1 (`event_coordinator`) unless stated | `POST /equipment-requirements` | add `recorded_by`; `status: "arranged"`; `event_name`; `support_note` | 422 `extra_forbidden` | nothing stored, no lookup | API |
| AC1-N10 | AC1, AC6 | No bearer token | Negative | Fake eventRequestService: E1 assigned to C1, status `Under Review`; catalogue seeded; caller C1 (`event_coordinator`) unless stated | `POST /equipment-requirements` | no `Authorization` | 401 "Authentication required" | nothing stored, no lookup | API |
| AC1-X2 | AC1 | Store failure is not reported as created | Cross-cutting | Fake eventRequestService: E1 assigned to C1, status `Under Review`; catalogue seeded; caller C1 (`event_coordinator`) unless stated | `POST /equipment-requirements` | insert raises `APIError` | 500 "Database operation failed" | no 201 | API |
| AC2-B6 | AC2 | Quantity 0 | Boundary | Fake eventRequestService: E1 assigned to C1, status `Under Review`; catalogue seeded; caller C1 (`event_coordinator`) unless stated | `POST /equipment-requirements` | 0 | 422 on `body.quantity` | nothing stored, no lookup | API |
| AC2-B7 | AC2 | Quantity 1 | Boundary | Fake eventRequestService: E1 assigned to C1, status `Under Review`; catalogue seeded; caller C1 (`event_coordinator`) unless stated | `POST /equipment-requirements` | 1 | 201 | none | API |
| AC2-B8 | AC2 | Quantity at integer max | Boundary | Fake eventRequestService: E1 assigned to C1, status `Under Review`; catalogue seeded; caller C1 (`event_coordinator`) unless stated | `POST /equipment-requirements` | 2147483647 | 201 | none | API |
| AC2-B9 | AC2 | Quantity above integer max | Boundary | Fake eventRequestService: E1 assigned to C1, status `Under Review`; catalogue seeded; caller C1 (`event_coordinator`) unless stated | `POST /equipment-requirements` | 2147483648 | 422 | nothing stored | API |
| AC2-N2 to AC2-N5 | AC2 | Quantity not a whole number | Negative | Fake eventRequestService: E1 assigned to C1, status `Under Review`; catalogue seeded; caller C1 (`event_coordinator`) unless stated | `POST /equipment-requirements` | `"abc"`; 1.5; null; omitted | 422 | nothing stored, no lookup | API |
| AC2-N6 to AC2-N8 | AC2 | Type missing, null or blank | Negative | Fake eventRequestService: E1 assigned to C1, status `Under Review`; catalogue seeded; caller C1 (`event_coordinator`) unless stated | `POST /equipment-requirements` | omitted; null; `"   "` | 422 | nothing stored, no lookup | API |
| AC2-N9 | AC2 | Type not in catalogue | Negative | Fake eventRequestService: E1 assigned to C1, status `Under Review`; catalogue seeded; caller C1 (`event_coordinator`) unless stated | `POST /equipment-requirements` | `Hologram` | 422 "Unknown equipment type" | nothing stored | API |
| AC2-N10 | AC2 | Retired-only type is unknown (D1) | Negative | Fake eventRequestService: E1 assigned to C1, status `Under Review`; catalogue seeded; caller C1 (`event_coordinator`) unless stated | `POST /equipment-requirements` | `Fog Machine` | 422 "Unknown equipment type" | nothing stored | API |
| AC2-B10 | AC2 | Technical requirements at limit | Boundary | Fake eventRequestService: E1 assigned to C1, status `Under Review`; catalogue seeded; caller C1 (`event_coordinator`) unless stated | `POST /equipment-requirements` | 2,000 chars | 201 | none | API |
| AC2-B11 | AC2 | Technical requirements over limit | Boundary | Fake eventRequestService: E1 assigned to C1, status `Under Review`; catalogue seeded; caller C1 (`event_coordinator`) unless stated | `POST /equipment-requirements` | 2,001 chars | 422 | nothing stored, no lookup | API |
| AC2-P1 | AC2 | Blank technical requirements stored as none | Partition | Fake eventRequestService: E1 assigned to C1, status `Under Review`; catalogue seeded; caller C1 (`event_coordinator`) unless stated | `POST /equipment-requirements` | `"   "` | 201, null | none | API |
| AC2-N11, AC2-N12 | AC2 | Event reference invalid | Negative | Fake eventRequestService: E1 assigned to C1, status `Under Review`; catalogue seeded; caller C1 (`event_coordinator`) unless stated | `POST /equipment-requirements` | `"not-a-uuid"`; omitted | 422 | nothing stored, no lookup | API |
| AC7-N1 to AC7-N3 | AC7 | Closed events refused | Negative | Fake eventRequestService: E1 assigned to C1, status `Under Review`; catalogue seeded; caller C1 (`event_coordinator`) unless stated | `POST /equipment-requirements` | event status `Cancelled`; `Completed`; `Rejected` | 409 "Event is closed" | nothing stored | API |
| AC6-X8 | AC6 | Unassigned Coordinator | Cross-cutting | Fake eventRequestService: E1 assigned to C1, status `Under Review`; catalogue seeded; caller C1 (`event_coordinator`) unless stated | `POST /equipment-requirements` | E1 assigned to C2 | 404 "Event request not found" | nothing stored | API |
| AC6-X9 | AC6 | Event with no Coordinator yet | Cross-cutting | Fake eventRequestService: E1 assigned to C1, status `Under Review`; catalogue seeded; caller C1 (`event_coordinator`) unless stated | `POST /equipment-requirements` | `/coordinator` answers 404 | 404, body identical to AC6-X8 | nothing stored | API |
| AC6-X10 | AC6 | Event that does not exist | Cross-cutting | Fake eventRequestService: E1 assigned to C1, status `Under Review`; catalogue seeded; caller C1 (`event_coordinator`) unless stated | `POST /equipment-requirements` | both GETs 404 | 404, body identical to AC6-X8 | nothing stored | API |
| AC6-X11 | AC6 | Owning organiser who also holds the coordinator role but is not assigned | Cross-cutting | Fake eventRequestService: E1 assigned to C1, status `Under Review`; catalogue seeded; caller C1 (`event_coordinator`) unless stated | `POST /equipment-requirements` | roles `[event_organiser, event_coordinator]`; `/coordinator` 200 with C2 | 404 | nothing stored | API |
| AC6-X12 to AC6-X16 | AC6 | Other roles cannot record | Cross-cutting | Fake eventRequestService: E1 assigned to C1, status `Under Review`; catalogue seeded; caller C1 (`event_coordinator`) unless stated | `POST /equipment-requirements` | `technical_support`; `event_organiser`; `venue_staff`; `event_operations_manager`; `attendee` | 403 "Insufficient permissions" | nothing stored, no lookup | API |
| AC6-N6 | AC6 | Event service down on record | Negative | Fake eventRequestService: E1 assigned to C1, status `Under Review`; catalogue seeded; caller C1 (`event_coordinator`) unless stated | `POST /equipment-requirements` | connection error | 502 | nothing stored | API |
| AC6-N7 | AC6 | Event service 401 on record | Negative | Fake eventRequestService: E1 assigned to C1, status `Under Review`; catalogue seeded; caller C1 (`event_coordinator`) unless stated | `POST /equipment-requirements` | 401 | 401 "Invalid session" | nothing stored | API |

### Specification: API layer: reads and queue

Automated in `backend/equipmentService/tests/test_requirements_read.py`.

| ID | AC | Test scenario | Technique | Pre-conditions | Test steps | Test data | Expected result | Forbidden side effects | Layer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AC3-H1 | AC3 | Assigned Coordinator lists an event's requirements | Happy | Rows seeded in `equipment_requirements`; fake eventRequestService: E1 assigned to C1 | `GET` the endpoint named in the data | two rows for E1 | 200, both, every field; query filters `event_request_id=E1`, orders `recorded_at`, `id` ascending | none | API |
| AC3-H2 | AC3 | Technical Support lists the same without asking eventRequestService | Happy | Rows seeded in `equipment_requirements`; fake eventRequestService: E1 assigned to C1 | `GET` the endpoint named in the data | as AC3-H1 as `technical_support` | 200, same items | no lookup | API |
| AC3-H3 | AC3 | Assigned Coordinator opens one | Happy | Rows seeded in `equipment_requirements`; fake eventRequestService: E1 assigned to C1 | `GET` the endpoint named in the data | one row | 200, every field | none | API |
| AC3-H4 | AC3 | Technical Support opens one | Happy | Rows seeded in `equipment_requirements`; fake eventRequestService: E1 assigned to C1 | `GET` the endpoint named in the data | one row | 200 | no lookup | API |
| AC3-B1 | AC3 | Event with no requirements | Boundary | Rows seeded in `equipment_requirements`; fake eventRequestService: E1 assigned to C1 | `GET` the endpoint named in the data | no rows | 200 `[]` | none | API |
| AC3-X1 | AC3 | Snapshot comes from the row, not a fresh event read | Cross-cutting | Rows seeded in `equipment_requirements`; fake eventRequestService: E1 assigned to C1 | `GET` the endpoint named in the data | row name "Annual Gala"; fake event now "Gala 2027" | "Annual Gala" | no `GET /event-requests/{id}` | API |
| AC3-N1 | AC3 | Unknown id | Negative | Rows seeded in `equipment_requirements`; fake eventRequestService: E1 assigned to C1 | `GET` the endpoint named in the data | random uuid | 404 "Equipment requirement not found" | none | API |
| AC3-N2 | AC3 | Malformed id (A5) | Negative | Rows seeded in `equipment_requirements`; fake eventRequestService: E1 assigned to C1 | `GET` the endpoint named in the data | `not-a-uuid` | 422 | no store query | API |
| AC4-H1 | AC4 | Default queue shows only `requested`, oldest first, with event reference and name | Happy | Rows seeded in `equipment_requirements`; fake eventRequestService: E1 assigned to C1 | `GET` the endpoint named in the data | query recorded | filter `status=requested`, order `recorded_at`, `id` asc; each item has `event_request_id`, `event_name` | none | API |
| AC4-P1, AC4-P2 | AC4 | Status filter | Partition | Rows seeded in `equipment_requirements`; fake eventRequestService: E1 assigned to C1 | `GET` the endpoint named in the data | `?status=in_progress`; `?status=arranged` | filter sent with that value | none | API |
| AC4-B1 | AC4 | Empty queue | Boundary | Rows seeded in `equipment_requirements`; fake eventRequestService: E1 assigned to C1 | `GET` the endpoint named in the data | no rows | 200 `[]` | none | API |
| AC4-N1 | AC4 | Unknown status filter | Negative | Rows seeded in `equipment_requirements`; fake eventRequestService: E1 assigned to C1 | `GET` the endpoint named in the data | `?status=cancelled` | 422 | no store query | API |
| AC6-X17, AC6-X18 | AC6 | Coordinators and organisers cannot read the queue | Cross-cutting | Rows seeded in `equipment_requirements`; fake eventRequestService: E1 assigned to C1 | `GET` the endpoint named in the data | `event_coordinator`; `event_organiser` | 403 | no data | API |
| AC6-X19 | AC6 | Unassigned Coordinator cannot list or open | Cross-cutting | Rows seeded in `equipment_requirements`; fake eventRequestService: E1 assigned to C1 | `GET` the endpoint named in the data | E1 assigned to C2 | 404 for list and one, identical to unknown | no data | API |
| AC6-X20 | AC6 | Reassignment moves access (D7) | Cross-cutting | Rows seeded in `equipment_requirements`; fake eventRequestService: E1 assigned to C1 | `GET` the endpoint named in the data | row recorded by C1; E1 now assigned to C2 | C1 → 404; C2 → 200 with `recorded_by` C1 | none | API |
| AC6-X21 | AC6 | Organiser who owns the event cannot read | Cross-cutting | Rows seeded in `equipment_requirements`; fake eventRequestService: E1 assigned to C1 | `GET` the endpoint named in the data | `event_organiser` | 403 on list and one | no data | API |
| AC6-X22 | AC6 | No token on every read | Cross-cutting | Rows seeded in `equipment_requirements`; fake eventRequestService: E1 assigned to C1 | `GET` the endpoint named in the data | queue, by-event, one | 401 each | no data | API |
| AC6-N8 | AC6 | Event service down on a Coordinator read | Negative | Rows seeded in `equipment_requirements`; fake eventRequestService: E1 assigned to C1 | `GET` the endpoint named in the data | connection error | 502 | no data | API |

### Specification: API layer: arrangement

Automated in `backend/equipmentService/tests/test_requirements_arrangement.py`.

| ID | AC | Test scenario | Technique | Pre-conditions | Test steps | Test data | Expected result | Forbidden side effects | Layer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AC5-H2 | AC5 | Technical Support moves a requirement to `in_progress` | Happy | Caller `technical_support` unless stated; RPC result or error set on the fake | `PATCH /equipment-requirements/{id}/arrangement` | `{expected_status: requested, status: in_progress, support_note: "Sourcing spare"}` | 200 with updated row; rpc `transition_equipment_requirement` called once with id, both statuses, note and `p_updated_by` = caller | no table insert | API |
| AC5-P8 | AC5 | Multi-role staff can update | Partition | Caller `technical_support` unless stated; RPC result or error set on the fake | `PATCH /equipment-requirements/{id}/arrangement` | roles `[event_operations_manager, technical_support]` | 200 | none | API |
| AC5-X3 | AC5 | Coordinator sees the update | Cross-cutting | Caller `technical_support` unless stated; RPC result or error set on the fake | `PATCH /equipment-requirements/{id}/arrangement` | seeded row `in_progress`, note, `updated_by`; GET as assigned C1 | status, note, `updated_by`, `updated_at` returned | none | API |
| AC5-N11 | AC5 | Disallowed or stale transition | Negative | Caller `technical_support` unless stated; RPC result or error set on the fake | `PATCH /equipment-requirements/{id}/arrangement` | rpc raises `P0004` | 409 "Transition not allowed" | none | API |
| AC5-N12 | AC5 | Unknown requirement | Negative | Caller `technical_support` unless stated; RPC result or error set on the fake | `PATCH /equipment-requirements/{id}/arrangement` | rpc raises `P0002` | 404 "Equipment requirement not found" | none | API |
| AC5-N13 | AC5 | Other database error | Negative | Caller `technical_support` unless stated; RPC result or error set on the fake | `PATCH /equipment-requirements/{id}/arrangement` | rpc raises other `APIError` | 500 "Database operation failed" | none | API |
| AC5-N14 | AC5 | Unknown status | Negative | Caller `technical_support` unless stated; RPC result or error set on the fake | `PATCH /equipment-requirements/{id}/arrangement` | `status: done` | 422 | no rpc | API |
| AC5-N15 | AC5 | `expected_status` missing | Negative | Caller `technical_support` unless stated; RPC result or error set on the fake | `PATCH /equipment-requirements/{id}/arrangement` | omitted | 422 | no rpc | API |
| AC5-N16 | AC5 | Note over limit | Negative | Caller `technical_support` unless stated; RPC result or error set on the fake | `PATCH /equipment-requirements/{id}/arrangement` | 2,001 chars | 422 | no rpc | API |
| AC5-N17 to AC5-N19 | AC5 | Coordinator-owned or server fields cannot be changed | Negative | Caller `technical_support` unless stated; RPC result or error set on the fake | `PATCH /equipment-requirements/{id}/arrangement` | add `quantity`; `equipment_type`; `updated_by` | 422 `extra_forbidden` | no rpc | API |
| AC6-X23, AC6-X24 | AC6 | Only Technical Support updates | Cross-cutting | Caller `technical_support` unless stated; RPC result or error set on the fake | `PATCH /equipment-requirements/{id}/arrangement` | assigned `event_coordinator`; `event_organiser` | 403 | no rpc | API |
| AC6-X25 | AC6 | No token | Cross-cutting | Caller `technical_support` unless stated; RPC result or error set on the fake | `PATCH /equipment-requirements/{id}/arrangement` | none | 401 | no rpc | API |

### Specification: integration layer (manual, Leg 2)

Docker Compose stack against the shared development database. Seed: event `MANUAL-S33 Gala` submitted by `event_organiser@example.com` and assigned to `event_coordinator1@example.com`; catalogue row `MANUAL-S33 Projector`. Passwords `12345678`. Cleanup SQL removes every `MANUAL-S33` row afterwards.

| ID | AC | Test scenario | Technique | Pre-conditions | Test steps | Test data | Expected result | Forbidden side effects | Layer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AC1-X3 | AC1 | Real record through real services | Cross-cutting | Seed above; stack up with `docker compose up --build -d` | Log in as coordinator1; `POST /equipment-requirements` qty 2 | as in steps | 201; row in Supabase with snapshot "MANUAL-S33 Gala" | No row left after cleanup | Integration (manual) |
| AC6-X26 | AC6 | Real unassigned Coordinator | Cross-cutting | Seed above; stack up with `docker compose up --build -d` | Same body as coordinator2 | as in steps | 404; no new row | No row left after cleanup | Integration (manual) |
| AC4-X2 | AC4 | Real queue | Cross-cutting | Seed above; stack up with `docker compose up --build -d` | Log in as technical_support; `GET /equipment-requirements` | as in steps | the row is listed | No row left after cleanup | Integration (manual) |
| AC5-X4 | AC5 | Real transitions and Coordinator view | Cross-cutting | Seed above; stack up with `docker compose up --build -d` | TSS: `requested`→`in_progress`→`arranged`; repeat the last call | as in steps | 200, 200, then 409; coordinator1 GET shows `arranged` with TSS as `updated_by` | No row left after cleanup | Integration (manual) |
| AC6-X27 | AC6 | Browser key blocked | Cross-cutting | Seed above; stack up with `docker compose up --build -d` | `GET /rest/v1/equipment_requirements` with the publishable key | as in steps | 401, `42501` | No row left after cleanup | Integration (manual) |

### Latest execution record

| ID | Automation status | Actual result | Execution status | Build or commit | Executed by and date | Remarks and evidence |
| ID | Green | passed | Pass | `d77b736` (local branch, unpushed) | Claude (Cowork), 7 Oct 2026 | Remarks and evidence; fakes only, no real service |
| --- | Green | passed | Pass | `d77b736` (local branch, unpushed) | Claude (Cowork), 7 Oct 2026 | ---; fakes only, no real service |
| AC1-H1 | Planned | not run on Supabase | Not executed | n/a | pending Yang | Red run in the SQL Editor before `0021` is applied |
| AC1-H2 | Planned | not run on Supabase | Not executed | n/a | pending Yang | Red run in the SQL Editor before `0021` is applied |
| AC1-N1 | Planned | not run on Supabase | Not executed | n/a | pending Yang | Red run in the SQL Editor before `0021` is applied |
| AC1-N2 to AC1-N5 | Planned | not run on Supabase | Not executed | n/a | pending Yang | Red run in the SQL Editor before `0021` is applied |
| AC1-X1 | Planned | not run on Supabase | Not executed | n/a | pending Yang | Red run in the SQL Editor before `0021` is applied |
| AC2-B1 | Planned | not run on Supabase | Not executed | n/a | pending Yang | Red run in the SQL Editor before `0021` is applied |
| AC2-B2 | Planned | not run on Supabase | Not executed | n/a | pending Yang | Red run in the SQL Editor before `0021` is applied |
| AC2-B3 | Planned | not run on Supabase | Not executed | n/a | pending Yang | Red run in the SQL Editor before `0021` is applied |
| AC2-N1 | Planned | not run on Supabase | Not executed | n/a | pending Yang | Red run in the SQL Editor before `0021` is applied |
| AC2-B4 | Planned | not run on Supabase | Not executed | n/a | pending Yang | Red run in the SQL Editor before `0021` is applied |
| AC2-B5 | Planned | not run on Supabase | Not executed | n/a | pending Yang | Red run in the SQL Editor before `0021` is applied |
| AC5-P1 to AC5-P3 | Planned | not run on Supabase | Not executed | n/a | pending Yang | Red run in the SQL Editor before `0021` is applied |
| AC5-N1 | Planned | not run on Supabase | Not executed | n/a | pending Yang | Red run in the SQL Editor before `0021` is applied |
| AC5-N2 | Planned | not run on Supabase | Not executed | n/a | pending Yang | Red run in the SQL Editor before `0021` is applied |
| AC5-N3 | Planned | not run on Supabase | Not executed | n/a | pending Yang | Red run in the SQL Editor before `0021` is applied |
| AC5-H1 | Planned | not run on Supabase | Not executed | n/a | pending Yang | Red run in the SQL Editor before `0021` is applied |
| AC5-P4 to AC5-P7 | Planned | not run on Supabase | Not executed | n/a | pending Yang | Red run in the SQL Editor before `0021` is applied |
| AC5-N4 to AC5-N7 | Planned | not run on Supabase | Not executed | n/a | pending Yang | Red run in the SQL Editor before `0021` is applied |
| AC5-N8 | Planned | not run on Supabase | Not executed | n/a | pending Yang | Red run in the SQL Editor before `0021` is applied |
| AC5-N9 | Planned | not run on Supabase | Not executed | n/a | pending Yang | Red run in the SQL Editor before `0021` is applied |
| AC5-N10 | Planned | not run on Supabase | Not executed | n/a | pending Yang | Red run in the SQL Editor before `0021` is applied |
| AC5-X1 | Planned | not run on Supabase | Not executed | n/a | pending Yang | Red run in the SQL Editor before `0021` is applied |
| AC5-X2 | Planned | not run on Supabase | Not executed | n/a | pending Yang | Red run in the SQL Editor before `0021` is applied |
| AC4-X1 | Planned | not run on Supabase | Not executed | n/a | pending Yang | Red run in the SQL Editor before `0021` is applied |
| AC6-X1 | Planned | not run on Supabase | Not executed | n/a | pending Yang | Red run in the SQL Editor before `0021` is applied |
| AC6-X2 | Planned | not run on Supabase | Not executed | n/a | pending Yang | Red run in the SQL Editor before `0021` is applied |
| AC6-X3 | Planned | not run on Supabase | Not executed | n/a | pending Yang | Red run in the SQL Editor before `0021` is applied |
| AC6-X4 | Planned | not run on Supabase | Not executed | n/a | pending Yang | Red run in the SQL Editor before `0021` is applied |
| AC6-X5 | Green | passed | Pass | `d77b736` (local branch, unpushed) | Claude (Cowork), 7 Oct 2026 | `tests/test_event_requests_client.py`; fakes only, no real service |
| AC6-X6 | Green | passed | Pass | `d77b736` (local branch, unpushed) | Claude (Cowork), 7 Oct 2026 | `tests/test_event_requests_client.py`; fakes only, no real service |
| AC6-X7 | Green | passed | Pass | `d77b736` (local branch, unpushed) | Claude (Cowork), 7 Oct 2026 | `tests/test_event_requests_client.py`; fakes only, no real service |
| AC6-N1 | Green | passed | Pass | `d77b736` (local branch, unpushed) | Claude (Cowork), 7 Oct 2026 | `tests/test_event_requests_client.py`; fakes only, no real service |
| AC6-N2 | Green | passed | Pass | `d77b736` (local branch, unpushed) | Claude (Cowork), 7 Oct 2026 | `tests/test_event_requests_client.py`; fakes only, no real service |
| AC6-N3 | Green | passed | Pass | `d77b736` (local branch, unpushed) | Claude (Cowork), 7 Oct 2026 | `tests/test_event_requests_client.py`; fakes only, no real service |
| AC6-N4 | Green | passed | Pass | `d77b736` (local branch, unpushed) | Claude (Cowork), 7 Oct 2026 | `tests/test_event_requests_client.py`; fakes only, no real service |
| AC6-N5 | Green | passed | Pass | `d77b736` (local branch, unpushed) | Claude (Cowork), 7 Oct 2026 | `tests/test_event_requests_client.py`; fakes only, no real service |
| AC1-H3 | Green | passed | Pass | `d77b736` (local branch, unpushed) | Claude (Cowork), 7 Oct 2026 | `tests/test_requirements_record.py`; fakes only, no real service |
| AC1-H4 | Green | passed | Pass | `d77b736` (local branch, unpushed) | Claude (Cowork), 7 Oct 2026 | `tests/test_requirements_record.py`; fakes only, no real service |
| AC1-P1 | Green | passed | Pass | `d77b736` (local branch, unpushed) | Claude (Cowork), 7 Oct 2026 | `tests/test_requirements_record.py`; fakes only, no real service |
| AC1-P2 | Green | passed | Pass | `d77b736` (local branch, unpushed) | Claude (Cowork), 7 Oct 2026 | `tests/test_requirements_record.py`; fakes only, no real service |
| AC1-P3 | Green | passed | Pass | `d77b736` (local branch, unpushed) | Claude (Cowork), 7 Oct 2026 | `tests/test_requirements_record.py`; fakes only, no real service |
| AC1-P4 | Green | passed | Pass | `d77b736` (local branch, unpushed) | Claude (Cowork), 7 Oct 2026 | `tests/test_requirements_record.py`; fakes only, no real service |
| AC1-P5 to AC1-P10 | Green | passed | Pass | `d77b736` (local branch, unpushed) | Claude (Cowork), 7 Oct 2026 | `tests/test_requirements_record.py`; fakes only, no real service |
| AC1-N6 to AC1-N9 | Green | passed | Pass | `d77b736` (local branch, unpushed) | Claude (Cowork), 7 Oct 2026 | `tests/test_requirements_record.py`; fakes only, no real service |
| AC1-N10 | Green | passed | Pass | `d77b736` (local branch, unpushed) | Claude (Cowork), 7 Oct 2026 | `tests/test_requirements_record.py`; fakes only, no real service |
| AC1-X2 | Green | passed | Pass | `d77b736` (local branch, unpushed) | Claude (Cowork), 7 Oct 2026 | `tests/test_requirements_record.py`; fakes only, no real service |
| AC2-B6 | Green | passed | Pass | `d77b736` (local branch, unpushed) | Claude (Cowork), 7 Oct 2026 | `tests/test_requirements_record.py`; fakes only, no real service |
| AC2-B7 | Green | passed | Pass | `d77b736` (local branch, unpushed) | Claude (Cowork), 7 Oct 2026 | `tests/test_requirements_record.py`; fakes only, no real service |
| AC2-B8 | Green | passed | Pass | `d77b736` (local branch, unpushed) | Claude (Cowork), 7 Oct 2026 | `tests/test_requirements_record.py`; fakes only, no real service |
| AC2-B9 | Green | passed | Pass | `d77b736` (local branch, unpushed) | Claude (Cowork), 7 Oct 2026 | `tests/test_requirements_record.py`; fakes only, no real service |
| AC2-N2 to AC2-N5 | Green | passed | Pass | `d77b736` (local branch, unpushed) | Claude (Cowork), 7 Oct 2026 | `tests/test_requirements_record.py`; fakes only, no real service |
| AC2-N6 to AC2-N8 | Green | passed | Pass | `d77b736` (local branch, unpushed) | Claude (Cowork), 7 Oct 2026 | `tests/test_requirements_record.py`; fakes only, no real service |
| AC2-N9 | Green | passed | Pass | `d77b736` (local branch, unpushed) | Claude (Cowork), 7 Oct 2026 | `tests/test_requirements_record.py`; fakes only, no real service |
| AC2-N10 | Green | passed | Pass | `d77b736` (local branch, unpushed) | Claude (Cowork), 7 Oct 2026 | `tests/test_requirements_record.py`; fakes only, no real service |
| AC2-B10 | Green | passed | Pass | `d77b736` (local branch, unpushed) | Claude (Cowork), 7 Oct 2026 | `tests/test_requirements_record.py`; fakes only, no real service |
| AC2-B11 | Green | passed | Pass | `d77b736` (local branch, unpushed) | Claude (Cowork), 7 Oct 2026 | `tests/test_requirements_record.py`; fakes only, no real service |
| AC2-P1 | Green | passed | Pass | `d77b736` (local branch, unpushed) | Claude (Cowork), 7 Oct 2026 | `tests/test_requirements_record.py`; fakes only, no real service |
| AC2-N11, AC2-N12 | Green | passed | Pass | `d77b736` (local branch, unpushed) | Claude (Cowork), 7 Oct 2026 | `tests/test_requirements_record.py`; fakes only, no real service |
| AC7-N1 to AC7-N3 | Green | passed | Pass | `d77b736` (local branch, unpushed) | Claude (Cowork), 7 Oct 2026 | `tests/test_requirements_record.py`; fakes only, no real service |
| AC6-X8 | Green | passed | Pass | `d77b736` (local branch, unpushed) | Claude (Cowork), 7 Oct 2026 | `tests/test_requirements_record.py`; fakes only, no real service |
| AC6-X9 | Green | passed | Pass | `d77b736` (local branch, unpushed) | Claude (Cowork), 7 Oct 2026 | `tests/test_requirements_record.py`; fakes only, no real service |
| AC6-X10 | Green | passed | Pass | `d77b736` (local branch, unpushed) | Claude (Cowork), 7 Oct 2026 | `tests/test_requirements_record.py`; fakes only, no real service |
| AC6-X11 | Green | passed | Pass | `d77b736` (local branch, unpushed) | Claude (Cowork), 7 Oct 2026 | `tests/test_requirements_record.py`; fakes only, no real service |
| AC6-X12 to AC6-X16 | Green | passed | Pass | `d77b736` (local branch, unpushed) | Claude (Cowork), 7 Oct 2026 | `tests/test_requirements_record.py`; fakes only, no real service |
| AC6-N6 | Green | passed | Pass | `d77b736` (local branch, unpushed) | Claude (Cowork), 7 Oct 2026 | `tests/test_requirements_record.py`; fakes only, no real service |
| AC6-N7 | Green | passed | Pass | `d77b736` (local branch, unpushed) | Claude (Cowork), 7 Oct 2026 | `tests/test_requirements_record.py`; fakes only, no real service |
| AC3-H1 | Green | passed | Pass | `d77b736` (local branch, unpushed) | Claude (Cowork), 7 Oct 2026 | `tests/test_requirements_read.py`; fakes only, no real service |
| AC3-H2 | Green | passed | Pass | `d77b736` (local branch, unpushed) | Claude (Cowork), 7 Oct 2026 | `tests/test_requirements_read.py`; fakes only, no real service |
| AC3-H3 | Green | passed | Pass | `d77b736` (local branch, unpushed) | Claude (Cowork), 7 Oct 2026 | `tests/test_requirements_read.py`; fakes only, no real service |
| AC3-H4 | Green | passed | Pass | `d77b736` (local branch, unpushed) | Claude (Cowork), 7 Oct 2026 | `tests/test_requirements_read.py`; fakes only, no real service |
| AC3-B1 | Green | passed | Pass | `d77b736` (local branch, unpushed) | Claude (Cowork), 7 Oct 2026 | `tests/test_requirements_read.py`; fakes only, no real service |
| AC3-X1 | Green | passed | Pass | `d77b736` (local branch, unpushed) | Claude (Cowork), 7 Oct 2026 | `tests/test_requirements_read.py`; fakes only, no real service |
| AC3-N1 | Green | passed | Pass | `d77b736` (local branch, unpushed) | Claude (Cowork), 7 Oct 2026 | `tests/test_requirements_read.py`; fakes only, no real service |
| AC3-N2 | Green | passed | Pass | `d77b736` (local branch, unpushed) | Claude (Cowork), 7 Oct 2026 | `tests/test_requirements_read.py`; fakes only, no real service |
| AC4-H1 | Green | passed | Pass | `d77b736` (local branch, unpushed) | Claude (Cowork), 7 Oct 2026 | `tests/test_requirements_read.py`; fakes only, no real service |
| AC4-P1, AC4-P2 | Green | passed | Pass | `d77b736` (local branch, unpushed) | Claude (Cowork), 7 Oct 2026 | `tests/test_requirements_read.py`; fakes only, no real service |
| AC4-B1 | Green | passed | Pass | `d77b736` (local branch, unpushed) | Claude (Cowork), 7 Oct 2026 | `tests/test_requirements_read.py`; fakes only, no real service |
| AC4-N1 | Green | passed | Pass | `d77b736` (local branch, unpushed) | Claude (Cowork), 7 Oct 2026 | `tests/test_requirements_read.py`; fakes only, no real service |
| AC6-X17, AC6-X18 | Green | passed | Pass | `d77b736` (local branch, unpushed) | Claude (Cowork), 7 Oct 2026 | `tests/test_requirements_read.py`; fakes only, no real service |
| AC6-X19 | Green | passed | Pass | `d77b736` (local branch, unpushed) | Claude (Cowork), 7 Oct 2026 | `tests/test_requirements_read.py`; fakes only, no real service |
| AC6-X20 | Green | passed | Pass | `d77b736` (local branch, unpushed) | Claude (Cowork), 7 Oct 2026 | `tests/test_requirements_read.py`; fakes only, no real service |
| AC6-X21 | Green | passed | Pass | `d77b736` (local branch, unpushed) | Claude (Cowork), 7 Oct 2026 | `tests/test_requirements_read.py`; fakes only, no real service |
| AC6-X22 | Green | passed | Pass | `d77b736` (local branch, unpushed) | Claude (Cowork), 7 Oct 2026 | `tests/test_requirements_read.py`; fakes only, no real service |
| AC6-N8 | Green | passed | Pass | `d77b736` (local branch, unpushed) | Claude (Cowork), 7 Oct 2026 | `tests/test_requirements_read.py`; fakes only, no real service |
| AC5-H2 | Green | passed | Pass | `d77b736` (local branch, unpushed) | Claude (Cowork), 7 Oct 2026 | `tests/test_requirements_arrangement.py`; fakes only, no real service |
| AC5-P8 | Green | passed | Pass | `d77b736` (local branch, unpushed) | Claude (Cowork), 7 Oct 2026 | `tests/test_requirements_arrangement.py`; fakes only, no real service |
| AC5-X3 | Green | passed | Pass | `d77b736` (local branch, unpushed) | Claude (Cowork), 7 Oct 2026 | `tests/test_requirements_arrangement.py`; fakes only, no real service |
| AC5-N11 | Green | passed | Pass | `d77b736` (local branch, unpushed) | Claude (Cowork), 7 Oct 2026 | `tests/test_requirements_arrangement.py`; fakes only, no real service |
| AC5-N12 | Green | passed | Pass | `d77b736` (local branch, unpushed) | Claude (Cowork), 7 Oct 2026 | `tests/test_requirements_arrangement.py`; fakes only, no real service |
| AC5-N13 | Green | passed | Pass | `d77b736` (local branch, unpushed) | Claude (Cowork), 7 Oct 2026 | `tests/test_requirements_arrangement.py`; fakes only, no real service |
| AC5-N14 | Green | passed | Pass | `d77b736` (local branch, unpushed) | Claude (Cowork), 7 Oct 2026 | `tests/test_requirements_arrangement.py`; fakes only, no real service |
| AC5-N15 | Green | passed | Pass | `d77b736` (local branch, unpushed) | Claude (Cowork), 7 Oct 2026 | `tests/test_requirements_arrangement.py`; fakes only, no real service |
| AC5-N16 | Green | passed | Pass | `d77b736` (local branch, unpushed) | Claude (Cowork), 7 Oct 2026 | `tests/test_requirements_arrangement.py`; fakes only, no real service |
| AC5-N17 to AC5-N19 | Green | passed | Pass | `d77b736` (local branch, unpushed) | Claude (Cowork), 7 Oct 2026 | `tests/test_requirements_arrangement.py`; fakes only, no real service |
| AC6-X23, AC6-X24 | Green | passed | Pass | `d77b736` (local branch, unpushed) | Claude (Cowork), 7 Oct 2026 | `tests/test_requirements_arrangement.py`; fakes only, no real service |
| AC6-X25 | Green | passed | Pass | `d77b736` (local branch, unpushed) | Claude (Cowork), 7 Oct 2026 | `tests/test_requirements_arrangement.py`; fakes only, no real service |
| AC1-X3 | Planned | not run | Not executed | n/a | pending Yang | Docker Compose stack; see docs/postman/README.md |
| AC6-X26 | Planned | not run | Not executed | n/a | pending Yang | Docker Compose stack; see docs/postman/README.md |
| AC4-X2 | Planned | not run | Not executed | n/a | pending Yang | Docker Compose stack; see docs/postman/README.md |
| AC5-X4 | Planned | not run | Not executed | n/a | pending Yang | Docker Compose stack; see docs/postman/README.md |
| AC6-X27 | Planned | not run | Not executed | n/a | pending Yang | Docker Compose stack; see docs/postman/README.md |

## Latest verification

**Leg 1 Red run, 6 October 2026 (automated).** Run by Claude (Cowork) from `backend/equipmentService` in the Linux workspace VM on Yang's Mac, Python 3.13.15 in a scratch virtual environment outside the repo (the repo's `.venv` is a macOS environment), on `6673a21` plus the uncommitted Leg 1 working tree. authService is faked through `httpx.get`; eventRequestService is faked behind `httpx.MockTransport`; Supabase is the in-memory `RequirementsStore`. No real service was involved.

| Check | Command | Result |
| --- | --- | --- |
| Lint | `ruff check .` | All checks passed |
| Whole suite | `python -m pytest -q` | 102 failed, 146 passed, 1 warning. The 146 are the existing tests, unchanged; the 102 are every new SCRUM-33 test item |
| Whole suite, CI style | `PYTHONPATH=. pytest -q` | Same: 102 failed, 146 passed |
| Failure reasons | `pytest --tb=line` on the four new files | Every endpoint test fails on a status assertion because the route returns 404 Not Found; every client test fails with `NotImplementedError` from the stub. No collection, import, fixture or type errors |
| Traceability | Script comparing the matrix with the code | All 132 automated IDs appear in a test or the SQL script; no unknown IDs; every new test has one label comment with one technique |

Two tests were corrected during the Red run because they would have passed vacuously or failed for the wrong reason: AC6-X11 only asserted a 404, which the missing route also returns, so it now also asserts the detail and that the assignment was checked; AC3-X1 indexed the response before checking its status (a `TypeError`), so it now asserts 200 first.

**Database script dry run, 6 October 2026 (not evidence for the matrix).** `database/verify_equipment_requirements.sql` was run on a throwaway local PostgreSQL 16 database with stub `auth.users` and `event_requests` tables. Without the table it stops during compilation with `42P01 relation "public.equipment_requirements" does not exist`, before any case runs (the expected Red). Against a draft of migration `0021` kept outside the repo it reaches the final NOTICE, and seven injected faults (expected-status check removed, `FOR UPDATE` removed, `quantity >= 0`, note-only check removed, a transition removed, `REVOKE` removed, `updated_by` not set) each stopped the script at the expected case. The dry run found that `P0004`, the team's transition code, is PostgreSQL's `assert_failure`, which `WHEN OTHERS` does not catch; the script's helper catches it explicitly. The Supabase SQL Editor run by Yang is still required for the execution record.

**Leg 2 Green run, 7 October 2026 (automated).** Run by Claude (Cowork) from `backend/equipmentService` on Yang's Mac (macOS, the repo `.venv`), on local branch `feat/scrum-33-equipment-requirements` at `d77b736`, after the Leg 2 slices 2.1–2.5. Dependencies are faked exactly as in the Red run (authService via the `httpx.get` stub, eventRequestService behind `httpx.MockTransport`, Supabase via `RequirementsStore`); no real service was involved, so this is local evidence only — shared-database and browser results are the manual cases below.

| Check | Command | Result |
| --- | --- | --- |
| Lint | `.venv/bin/ruff check .` | All checks passed |
| Whole suite | `.venv/bin/python -m pytest -q` | 248 passed, 1 warning (146 existing + 102 SCRUM-33); 0 failed |
| eventRequestService regression | `python -m pytest -q` in `backend/eventRequestService` | 234 passed — unchanged |
| Working tree after mutation checks | `git status` / `git diff` | Clean; every mutant reverted |

**Manual mutation check, 7 October 2026** (`mutmut` is not installed; `testing.md` §7 tooling is a separate team change, so each mutant was applied by hand, its expected catcher run, and the tree restored — every mutant was killed):

| Mutant | Expected catcher | Result |
| --- | --- | --- |
| M1 assignment compared with `==` | AC1-H3, AC6-X8 | killed (25 tests failed, including AC6-X6 and the record suite) |
| M2 request body allows extra fields | AC1-N6 | killed (AC1-N6 to AC1-N9 failed) |
| M3 coordinator role check removed on POST | AC6-X12 | killed (AC6-X12 failed: `technical_support` got 404 instead of 403) |
| M4 Technical Support shortcut applied to coordinators on reads | AC6-X19 | killed |
| M5 `quantity` `ge=0` | AC2-B6 | killed |
| M6 `Rejected` missing from closed statuses | AC7-N3 | killed (AC7-N3 failed) |
| M7 token not forwarded | AC6-X5 | killed |
| M8 queue default `in_progress` | AC4-H1 | killed |
| M9 type compared case-sensitively | AC1-P1 | killed |
| M10 retired rows counted as catalogue types | AC2-N10 | killed |
| M11 `expected_status` check removed in SQL | AC5-N8 | caught by the 6 October SQL dry run's injected fault "expected-status check removed" (script stopped at AC5-N8); Supabase run pending Yang |
| M12 `FOR UPDATE` removed in SQL | AC5-X2 | caught by the 6 October SQL dry run's injected fault "`FOR UPDATE` removed" (script stopped at AC5-X2); Supabase run pending Yang |

## Disclosures

- Test cases, tests, the SQL script and the contract stub were drafted by Claude (Cowork) from the approved ACs, before any implementation. The test design was reviewed and approved by **Yang Xue on 7 October 2026**, including D9 and D10.
- `app/event_requests_client.py` and the `event_request_service_url` setting were added as signature-only stubs so the client tests fail with `NotImplementedError` rather than an import error (`testing.md` §5).
- `tests/conftest.py` gained four SCRUM-33 fixtures (`req_store`, `req_events`, `as_user`, `req_api`); the existing fixtures are unchanged.
- Per `commits.md` §4, the red tests are not pushed; they are committed with the code that makes them pass in Leg 2.
- Leg 2's production code (migration `0021`, the event client, the requirements router) was written by Claude (Cowork) against the already-approved test suite, in the slice order of the plan; the D9 note-keeping rule is implemented in the database function, so every caller gets it.
