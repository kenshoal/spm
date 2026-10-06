# venueService

FastAPI microservice for the venue catalogue and venue search / filtering.

## Scope

### SCRUM-15 decision rules (integration pending)

`app/booking_decisions.py` contains the pure `assess_booking_decision` function.
This work is on `feat/venue-booking-decision`, based on `feat/venue-blocking` to
reuse SCRUM-23's availability checks. The internal input projections are not a
database schema or an agreed booking/event API.

- Only a request whose normalized status is `pending` can receive a decision.
- Explicit rejection preserves an optional reason and suggested alternative.
  It does not require availability lookups to succeed. Blank details are absent;
  nonempty rejection details on an approval are rejected as invalid input.
- Approval checks current whole-venue status, operating slots and active blocks
  using SCRUM-23's existing logic, plus overlapping confirmed venue bookings.
- Dates are inclusive and a shared slot is required for overlap. Other venues,
  disjoint periods/slots and lifted blocks do not conflict.
- `None` for either lookup means it has not succeeded and prevents approval;
  an empty list means a successful lookup found no rows.
- Refused approval returns machine-readable reasons and block/booking conflict
  evidence, with no target status. The request remains pending until a separate
  explicit decision is saved. The future handler must record refusal evidence.

`ConfirmedVenueBooking` represents an actual reserved venue period, not proposed
event timing. The future adapter must supply all relevant current confirmed
reservations and omit cancelled/unconfirmed ones. A venue reservation must count
even if the overall event has not yet reached `Confirmed`; do not reuse the
affected-event notification filter for booking conflict checks.

The evaluator performs no authorization, writes, allocation creation, event
changes or notifications. No endpoint has been added. Integration still needs
the shared booking schema and allocation ownership/API. The handler must verify
Venue Staff permission, read current data, and coordinate its final check and
save with both competing approvals and venue-block writes. A successful rule
assessment alone does not lock or reserve a slot. Notify the requesting
Coordinator only after a decision is committed, leaving any event changes to
the Coordinator. Notification delivery is not implemented by these rules.

Tests: `pytest tests/test_booking_decisions.py`. These cover decision eligibility,
rejection details, availability/conflict refusals, inclusive boundaries, failed
lookups, invalid inputs and absence of mutation. They do not claim end-to-end
coverage of booking persistence, concurrency or notification acceptance criteria.

### Existing endpoints

| Capability | Endpoints |
| --- | --- |
| Maintain the venue catalogue | `POST /venues`, `GET /venues/{id}`, `PATCH /venues/{id}`, `GET /venues` |
| Search and filter venues | `GET /venues/search` |
| Check venue suitability | `POST /venues/{id}/suitability` |
| Create a venue block | `POST /venues/{venue_id}/blocks` |
| List a venue's blocks | `GET /venues/{venue_id}/blocks` |
| Venue booking requests | `POST /booking-requests`, `GET /booking-requests`, `GET /booking-requests/mine`, `GET /booking-requests/{id}` |

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

`GET /venues/search` checks active venue blocks when a `date` is supplied.
Whole-venue status and the existing catalogue filters still apply.

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

These checks consider venue blocks only, not existing reservations.
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

Coordinator alerts for confirmed events affected by a new block (SCRUM-23 AC3)
are not implemented yet. As agreed with the SCRUM-32 owner, an approved request
in `venue_booking_requests` is the booking, so affected events will come from
approved rows for the venue plus the event's status and current Coordinator
from eventRequestService, once SCRUM-15 can approve requests.

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

This endpoint does not create a booking, lock the venue, or check existing
bookings. Its answer is a snapshot. The booking owner must call the check,
reject `available: false`, and coordinate check-and-save with block writes to
avoid a block being created between checking and saving. Merely calling this
endpoint separately is not an atomic booking guarantee.
