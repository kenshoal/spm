# eventRequestService

FastAPI service for event-request submission, coordinator assignment, review
decisions and lifecycle transitions. Records are persisted in Supabase.

## Current API

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/event-requests` | Create a Draft |
| `POST` | `/event-requests/submissions` | Submit a complete new request |
| `GET` | `/event-requests` | List the current organiser's requests |
| `GET` | `/event-requests/assigned-to-me` | List requests whose latest assignment is the calling Coordinator |
| `GET` | `/event-requests/public-events` | Attendee-facing Confirmed and Completed events |
| `GET` | `/event-requests/venue-requirements` | Venue fields for active arrangements (`venue_staff` only) |
| `GET` | `/event-requests/equipment-requirements` | Equipment fields for active arrangements (`technical_support` only) |
| `GET` | `/event-requests/{id}` | Retrieve one request (owning Organiser or assigned Coordinator) |
| `PATCH` | `/event-requests/{id}` | Update a Draft |
| `POST` | `/event-requests/{id}/submit` | Submit a completed Draft |
| `DELETE` | `/event-requests/{id}` | Delete a Draft |
| `GET` | `/event-requests/awaiting-assignment` | List Submitted requests with no Coordinator |
| `POST` | `/event-requests/{id}/coordinator` | Assign or reassign a Coordinator |
| `GET` | `/event-requests/{id}/coordinator` | Get the current Coordinator |
| `POST` | `/event-requests/{id}/review` | Assigned Coordinator starts review (`Submitted` → `Under Review`) |
| `POST` | `/event-requests/{id}/decision` | Assigned Coordinator approves, requests clarification, or rejects an `Under Review` request |
| `GET` | `/event-requests/{id}/decisions` | List retained review decisions for the owning Organiser or assigned Coordinator |
| `POST` | `/event-requests/{id}/clarification-response` | Owning Organiser answers the current clarification without editing submitted fields |
| `POST` | `/event-requests/{id}/resume-review` | Assigned Coordinator continues review after the Organiser responds |
| `POST` | `/event-requests/{id}/cancellation` | Assigned Coordinator cancels a non-terminal request (→ `Cancelled`) |
| `POST` | `/event-requests/{id}/completion` | Assigned Coordinator marks a confirmed event complete (`Confirmed` → `Completed`) |
| `GET` | `/health` | Service health check |

Every event-request operation requires `Authorization: Bearer <access-token>`.
Draft CRUD requires `event_organiser`, coordinator assignment and the
awaiting-assignment queue require `event_operations_manager`, and the
coordinator list and transition commands require `event_coordinator`.
The service asks authService to verify that token with Supabase, then scopes
drafts to the returned user ID. A current assignment may be read by the owning
Event Organiser, an Event Operations Manager, or the currently assigned Event
Coordinator. Multi-role users are authorised when any assigned role and the
required request relationship match. The browser cannot choose the organiser or
coordinator ID; both come from the verified session.

Assignment uses the server-only `assign_event_request_coordinator` database
function. It locks the request row shared with status transitions, rechecks the
request state and verifies that the selected user has `event_coordinator` in
`staff_roles` before inserting the assignment. Error codes `P0002`, `P0004`
and `P0005` map to 404 or 409 responses without creating an assignment. Apply
migration `0014_atomic_coordinator_assignment.sql` before deploying this
service version.

`GET /event-requests/{id}` returns the request to its owning Organiser or to the
Coordinator on its latest assignment. An unrelated Organiser or Coordinator gets
404 (so request IDs cannot be probed); any other role gets 403.
`GET /event-requests/assigned-to-me` returns `[]` when nothing is assigned and
excludes requests that have since been reassigned to someone else.
The three role-specific list endpoints return deliberately narrow response
models: they never include `organiser_id`, purpose, review decisions or the
other role's requirements. Attendee data is limited to Confirmed and Completed
events; venue and equipment work begins only after approval.
The non-null `organiser_id` column stores that verified UUID. This service no
longer reads or writes `temporary_organiser_id`; the deployed Supabase table
must match that contract before authenticated requests are tested.

Draft fields may remain incomplete. Submission requires every currently defined
event-request field, changes the status to `Submitted`, and makes the request
read-only. Requirements that do not apply must still contain explicit text such
as `None`.

## Status transitions

The database migration `0011_event_request_review_status.sql` permits the full
agreed status vocabulary. This service writes only the following transitions:

| Transition | Actor | Endpoint |
| --- | --- | --- |
| `Draft` → `Submitted` | Owning Organiser | `POST /{id}/submit` (or direct `POST /submissions`) |
| `Submitted` → `Under Review` | Assigned Coordinator | `POST /{id}/review` |
| `Under Review` → `Changes Requested`, `Approved`, or `Rejected` | Assigned Coordinator | `POST /{id}/decision` |
| `Changes Requested` → `Under Review` | Assigned Coordinator, after Organiser response | `POST /{id}/resume-review` |
| Any non-terminal status → `Cancelled` | Assigned Coordinator | `POST /{id}/cancellation` |
| `Confirmed` → `Completed` | Assigned Coordinator | `POST /{id}/completion` |

Owned by other stories and **not** implemented here: post-submission change
requests raised by an Organiser after a decision (SCRUM-35), Planning and
Confirmed (venue/operations stories), notification delivery (SCRUM-36), and
automatic completion of Confirmed events more than seven days overdue
(SCRUM-40). `Completed`, `Cancelled` and `Rejected` are terminal.

The three coordinator commands run through the database function
`advance_event_request_by_coordinator` (migration
`0012_coordinator_status_transitions.sql`). It locks the request row, re-checks
the latest assignment and updates the status in one transaction, so a refused
call never changes the status. The service maps its error codes, not message
text: `P0002` → 404, `P0003` → 403, `P0004` → 409. Apply `0012` to the target
Supabase project before deploying this service; see `database/README.md`.
Notification delivery for these transitions belongs to SCRUM-36.

SCRUM-17 uses the three server-only functions in migration
`0016_event_request_review_decisions.sql`. They atomically record a decision,
attach the owning Organiser's clarification response and return the request to
`Under Review` only for the assigned Coordinator. Submitted request fields stay
read-only throughout. Direct client roles cannot read the history table or
execute these functions; authorised access goes through this API.

## Submission confirmations

When an event request becomes `Submitted`, the database records one
`event_request.submitted` row in `event_request_outbox` (migration `0008`).
While the service runs, a background relay checks that table every 10 seconds
and sends each unpublished row to notificationService as an
`event_request_submitted` notification for the Organiser (SCRUM-37 AC1), then
sets `published_at`.

- A row is marked published only after notificationService accepts it, so an
  unreachable notification service delays confirmations instead of losing
  them.
- The outbox row id is sent as `event_id`, and notificationService stores a
  repeated `event_id` once, so a re-sent row never notifies the Organiser
  twice.
- The relay runs only when `NOTIFICATION_SERVICE_URL` and Supabase are both
  configured. Without them, rows stay unpublished until a relay can deliver
  them.

## Clarification notices

When the assigned Coordinator records a `Changes Requested` decision through
`POST /event-requests/{id}/decision`, the service sends the owning Organiser a
`clarification_requested` notification carrying the Coordinator's reason
(SCRUM-37 AC3), after the decision has been written.

- The notice is sent once and is not retried. If notificationService is
  unreachable, the failure is logged and the decision still succeeds; the
  Organiser can read the clarification on the request itself. Unlike the
  submission confirmation, it does not go through the outbox.
- Approved and Rejected decisions send nothing here; their notices belong to
  SCRUM-36.
- A refused decision (wrong Coordinator, wrong status, missing reason) sends
  nothing.

## Run locally on macOS/Linux

The standard project workflow is to run `docker compose up --build -d` from
the repository root. This exposes eventRequestService on
`http://localhost:8003`. Use the commands below only when developing this
service by itself.

Python 3.11 or newer is required.

```bash
python3.14 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
cp .env.example .env
# Replace SUPABASE_SECRET_KEY with the server-only key from Supabase.
# Run authService on port 8001, or set AUTH_SERVICE_URL to its internal URL.
uvicorn app.main:app --reload --port 8003
```

The API is available at `http://localhost:8003`, with interactive documentation
at `http://localhost:8003/docs`.

`SUPABASE_SECRET_KEY` must remain in the backend environment. Do not put it in
frontend variables or commit it to source control. New `sb_secret_...` keys are
preferred; the legacy service-role key is also supported during migration.

## Test

```bash
ruff check .
pytest
```
