# Event request and coordination boundaries

The organiser-facing `eventRequestService` owns the request form and its data
until it is handed to event coordination.

| Stage | Owning service | Responsibilities |
| --- | --- | --- |
| `Draft` | `eventRequestService` | Create, read, update and delete the authenticated organiser's incomplete request. |
| `Submitted` | `eventRequestService` | Validate the complete form, preserve the organiser and request ID, and make the request read-only. |
| Coordination workflow | `eventService` | Coordinator assignment, assessment, authorisation, scheduling, completion and their audit history. |

SCRUM-11 ends when one authenticated organiser's complete request is persisted
as `Submitted`. It does not assign a coordinator or implement later workflow
transitions.

## Integration still required

The coordination service is not present on this branch, so there is no
implemented hand-off from a submitted request to an operational event yet.
Before those branches are integrated, agree on an idempotent contract that:

- references the immutable submitted `event_request_id` rather than copying the
  request CRUD operations;
- stores that reference with a unique constraint so retries cannot create two
  operational events;
- preserves `organiser_id` as the authenticated owner;
- leaves coordinator-only fields and status history in `eventService`.

## Interim status tracking (SCRUM-28)

Until `eventService` exists, `eventRequestService` stores the request status
and coordinator assignment history, and the frontend displays all ten statuses.
It writes only four transitions: `Draft` → `Submitted` (organiser),
`Submitted` → `Under Review`, non-terminal → `Cancelled` and `Confirmed` →
`Completed` (assigned coordinator, through the `0012` database function).
Approval, rejection, changes requested, planning, confirmation and automatic
completion must be written by their own stories, not invented in
`eventRequestService`. When the coordination service is integrated, move these
commands behind the hand-off contract above.

## Interim access relationships

- Event Organisers can view and change requests whose `organiser_id` is their
  own user ID. Organisers in the same client organisation can view each other's
  non-Draft requests but cannot change them (`403`); unrelated organisations get
  `404` (clarification #81, migration `0019`). Organisation membership is seeded
  data until E3-4 adds maintenance.
- Attendees receive only the public projection of Confirmed or Completed
  events; requirements and other planning fields are never included.
- Venue Staff receive venue booking requests through `venueService`. The
  record is SCRUM-32's `venue_booking_requests` row: venue, event reference,
  date range, slots, and the event snapshot (name, attendance, requirements
  note) taken at submission, so Venue Staff never read the event request.
- Technical Support Staff receive concrete equipment reservations through
  `equipmentService`; the reservation record contains the event, equipment and
  quantity relationship needed to support the arrangement.
- The assigned Event Coordinator remains the only coordinator who can read the
  full request. Venue and technical queues are role-wide until those domains
  define individual staff assignment.
