# venueService

FastAPI microservice for the venue catalogue and venue search / filtering.

## Scope

| Capability | Endpoints |
| --- | --- |
| Maintain the venue catalogue | `POST /venues`, `GET /venues/{id}`, `PATCH /venues/{id}`, `GET /venues` |
| Search and filter venues | `GET /venues/search` |
| Check venue suitability | `POST /venues/{id}/suitability` |
| Venue booking requests | `POST /booking-requests`, `GET /booking-requests`, `GET /booking-requests/mine`, `GET /booking-requests/{id}` |

Venues are stored in the Supabase `public.venues` table
(`database/migrations/0016_venues.sql`) when `VENUE_STORAGE_BACKEND=supabase`,
which Docker Compose sets. The default, `memory`, keeps venues in process
memory and is used by the unit tests and standalone development; that data is
lost when the service stops. All routes verify the bearer token with `authService`; create and update
operations require the `venue_staff` role.

`GET /venues/search` accepts a `date` parameter but does not yet evaluate
per-date availability; a venue is excluded only when its whole-venue `status`
is not `available`. Per-date-slot blocking belongs to the venue availability
calendar / venue-blocking stories.

`POST /venues/{id}/suitability` compares an event's stated requirements
(expected attendance, layout, operating slot, facilities, accessibility)
against a venue's recorded attributes and lists any attribute that doesn't
match. It is advisory only — a `suitable: false` result never books, holds,
or changes the venue.

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
