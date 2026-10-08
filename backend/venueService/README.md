# venueService

FastAPI microservice for the venue catalogue and venue search / filtering.

## Scope

### SCRUM-15 booking decisions

Venue Staff approve or reject a pending booking request (SCRUM-32) with
`POST /booking-requests/{id}/decision`:

```json
{"decision": "rejected", "reason": "Hall under repair", "suggested_alternative": "Try Orchard Studio"}
```

- Only a `pending` request can be decided; a decided one returns `409`
  ("already been decided") and an unknown one `404`. Non-staff get `403`.
- A rejection needs a non-blank reason; the alternative is optional free text.
  An approval carries neither. Anything else returns `422`.
- An approved request **is** the confirmed booking (agreed in 0018).
- Approval is refused with `409` and
  `{"message", "refusal_codes", "conflicting_block_ids", "conflicting_booking_ids"}`
  when the venue is blocked in the catalogue (`venue_unavailable`), a slot is not
  operated (`outside_operating_slots`), an active block overlaps (`active_block`)
  or another **approved** request for the venue overlaps (`booking_conflict`).
  Dates are inclusive and NIGHT belongs to its starting date. Pending and
  rejected requests never conflict.
- A refused approval leaves the request pending and records who, when and why.
  Venue Staff read the log with `GET /booking-requests/{id}/refusals`.

In database mode the decision runs in `decide_venue_booking_request`
(`database/migrations/0024_venue_booking_decisions.sql`), which locks the venue
row, then the request row, and re-checks everything before writing the decision
or one `venue_booking_refusals` row. Block creation goes through
`create_venue_block`, which takes the same venue lock, so two approvals, or an
approval and a block, cannot both succeed for overlapping periods. Memory mode
applies `assess_booking_decision` (`app/booking_decisions.py`) under an
equivalent process-wide lock (`app/venue_locks.py`). Verify the database
functions with `database/verify_venue_booking_decisions.sql`.

A saved decision notifies the requesting Coordinator (`requested_by`) through
notificationService (`NOTIFICATION_SERVICE_URL`, set in Docker Compose) with
event type `venue_booking_approved` or `venue_booking_rejected`. A refused
approval sends nothing, and a failed notification is logged without undoing
the decision.

Approved requests make their venue, dates and slots unavailable: dated
`GET /venues/search` excludes them like active blocks, and
`POST /venues/{id}/availability` reports them as `booking_conflict` with
`booking_conflicts`. Pending and rejected requests reserve nothing. Setup and
turnaround gaps belong to M5-1.

### Existing endpoints

| Capability | Endpoints |
| --- | --- |
| Maintain the venue catalogue | `POST /venues`, `GET /venues/{id}`, `PATCH /venues/{id}`, `GET /venues` |
| Search and filter venues | `GET /venues/search` |
| Check venue suitability | `POST /venues/{id}/suitability` |
| Create a venue block | `POST /venues/{venue_id}/blocks` |
| List a venue's blocks | `GET /venues/{venue_id}/blocks` |
| Venue booking requests | `POST /booking-requests`, `GET /booking-requests`, `GET /booking-requests/mine`, `GET /booking-requests/{id}` |
| Decide a booking request | `POST /booking-requests/{id}/decision`, `GET /booking-requests/{id}/refusals` |

Venues are stored in the Supabase `public.venues` table
(`database/migrations/0016_venues.sql`) and venue blocks in `public.venue_blocks`
(`database/migrations/0023_venue_blocks.sql`) when `VENUE_STORAGE_BACKEND=supabase`,
which Docker Compose sets. The default, `memory`, keeps both in process memory
and is used by the unit tests and standalone development; that data is lost
when the service stops. All routes verify the bearer token with `authService`;
reads require `event_coordinator` or `venue_staff`, while create and update
operations require `venue_staff`.

`POST /venues/{id}/suitability` compares an event's stated requirements
(expected attendance, layout, operating slot, facilities, accessibility)
against a venue's recorded attributes and lists any attribute that doesn't
match. It is advisory only — a `suitable: false` result never books, holds,
or changes the venue.

`GET /venues/search` checks active venue blocks and approved bookings when a
`date` is supplied. Whole-venue status and the existing catalogue filters still
apply.

## Create a venue block (Day 3)

Create a venue through `POST /venues` first, then use its returned ID in
`POST /venues/{venue_id}/blocks` with a body such as:

```json
{
  "start_date": "2026-09-20",
  "end_date": "2026-09-21",
  "slots": ["AM", "PM"],
  "reason_category": "maintenance",
  "reason_detail": "Air-conditioning repairs"
}
```

The selected slots apply on every date in the inclusive range. The endpoint
returns `201` with the saved block, its generated ID and timestamp, active
status, and creator from the staff dependency. Unknown venues return `404`;
invalid input (including client-supplied creator or status) returns `422`.

In default memory mode, venues and blocks are local to the process and lost on
restart; records stored only in Supabase are not visible. In database mode,
both repositories use the existing `public.venues` and `public.venue_blocks`
tables. The block creator is the verified Venue Staff user. Creating a block
affects dated search but does not change whole-venue status. Booking enforcement
and notifications are not yet integrated.

## Block retrieval and search (Day 4)

`GET /venues/{venue_id}/blocks` returns all blocks for that venue, including
lifted blocks. It is limited to Venue Staff (`403` otherwise) because block
reasons are internal. An existing
venue with no blocks returns `[]`; an unknown venue returns `404`.

Search behaviour:

- `GET /venues/search?date=2026-09-20&slot=AM` excludes venues with an active
  block covering AM on that date.
- With a date but no slot, a venue is returned if at least one of its operating
  slots remains unblocked. Separate blocks can collectively block all slots.
  A result does not mean the venue is available for the entire day.
- Without a date, dated blocks are not evaluated. A slot-only search checks
  normal operating slots, not availability on any specific date.
- Lifted blocks are ignored by search. Block dates include both boundaries;
  NIGHT belongs to its starting date. Only the venue's own blocks apply.

For the example above, September 20 AM search excludes the venue; NIGHT search
can include it if NIGHT is an operating slot and no other filter or block
excludes it. September 22 AM is outside this block and is unaffected by it.

These checks also exclude approved bookings (SCRUM-15).
There is no block-lifting endpoint or calendar UI yet.

## Database integration (local development)

Venues use `app/supabase_repository.py`; blocks use
`app/supabase_block_repository.py`, which follows eventRequestService's
Supabase Data API approach.
It uses `SUPABASE_URL` and a server-side `SUPABASE_SECRET_KEY`, not `DATABASE_URL`.
IDs and creation timestamps are generated by the database. Listing follows all
pages, including when the database caps each response below the requested size.
Connection or configuration failures do not fall back silently to memory.

From `backend/venueService`:

1. Install the updated dependencies: `python -m pip install -e ".[dev]"`.
2. Copy `.env.example` to `.env` and fill in the URL and secret key locally.
3. Set `VENUE_STORAGE_BACKEND=supabase` and make sure authService is running
   (`AUTH_SERVICE_URL`).
4. Start `uvicorn app.main:app --host 127.0.0.1 --port 8002 --env-file .env`
   from this directory.

Database mode changes the shared database when you create/update records.
Restarting this server does not remove them. Docker Compose passes the
Supabase variables to this service from the repository root `.env`.

A creator UUID that does not exist in `auth.users` causes block insertion to
fail with `409`.
Schema constraint violations return `422`; unexpected database failures return
`502`, without exposing credentials or raw database errors.

The existing block model requires `created_by`, although the database currently
allows null. Historical rows with a null creator need a genuine creator assigned
before they can be read through this model; this adapter does not invent one.

Tests always override settings to use isolated memory or HTTP mock transports.
They do not read local credentials or write to the shared database. The database
adapter tests cover endpoint wiring, JSON conversion, pagination, foreign-key
errors, timeouts, and creation-to-search behaviour.

## Integration notes

Venue blocking has no dependency on equipmentService for its acceptance criteria.
Equipment integration is only needed if the team adds an explicit requirement
about equipment affected by a venue closure.

When Venue Staff create a block (SCRUM-23 AC3), venueService finds every
approved booking request for that venue that shares a date and slot with the
block and has not ended (Singapore date), and sends its requesting Coordinator
a `venue_block_affects_booking` notification with the block's dates, slots and
reason. The block is always saved; a failed notification is logged and never
undoes it. As agreed with the SCRUM-32 owner, an approved request is the
booking, so no event-status lookup is needed.

Booking requests (SCRUM-32) are stored in `public.venue_booking_requests`
(`database/migrations/0018_venue_booking_requests.sql`) under the same
`VENUE_STORAGE_BACKEND` switch. An Event Coordinator submits a request for a
venue, an inclusive date range and one or more slots, for an event they are
currently assigned to. venueService confirms that with eventRequestService
(`EVENT_REQUEST_API_URL`, default `http://127.0.0.1:8003`) using the caller's own
token, and copies the event's name, expected attendance and venue-requirements
text into the request. Submitting creates a `pending` request and reserves
nothing: pending requests never block each other, and approving or rejecting
one belongs to a later story. Venue Staff list the queue
(`GET /booking-requests`, pending by default, oldest first) and can open any
request; a Coordinator lists (`/mine`, newest first) and opens only their own,
and another Coordinator's request returns 404. A request for a blocked venue or
for past dates is accepted at submission.

## Run locally

The standard project workflow is to run `docker compose up --build -d` from
the repository root. This exposes venueService on `http://localhost:8004`.
Use the commands below only when developing this service by itself.

To persist venues when running the service by itself, set
`VENUE_STORAGE_BACKEND=supabase`, `SUPABASE_URL` and the server-only
`SUPABASE_SECRET_KEY` (see `.env.example`).

```powershell
python -m venv .venv
./.venv/Scripts/Activate.ps1
python -m pip install -e ".[dev]"
uvicorn app.main:app --reload
```

The service is available at `http://localhost:8000`, its health check at
`http://localhost:8000/health`, and interactive API documentation at
`http://localhost:8000/docs`.

## Test

```powershell
ruff check .
pytest
```

## Venue-block availability check

`POST /venues/{venue_id}/availability` is a read-only check using the existing
venue and block repositories (memory or database). Venue Staff and Event
Coordinators may call it; other roles get `403`. The result contains dates,
slots and reason codes but never a block's free-text reason.

```json
{
  "start_date": "2026-10-01",
  "end_date": "2026-10-03",
  "slots": ["AM", "PM"]
}
```

A successful check returns `200` with `available`, `reasons`, `unsupported_slots`,
and `conflicts` (block ID plus intersecting dates/slots). All requested slots on
all dates must be supported and free of active blocks. Reason codes are
`venue_unavailable`, `outside_operating_slots`, and `active_block`. Lifted blocks
are ignored; dates are inclusive and NIGHT belongs to its starting date. A
missing venue returns `404`; invalid dates/slots or extra fields return `422`.
Backend failures are errors, never an `available: true` fallback.

This endpoint does not create a booking or lock the venue; it reports active
blocks and approved bookings (`booking_conflict`, `booking_conflicts`) as a
snapshot. Approval itself re-checks everything under the venue lock in
`decide_venue_booking_request` (SCRUM-15).
