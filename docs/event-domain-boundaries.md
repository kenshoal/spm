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

- Event Organisers are currently scoped to requests whose `organiser_id` is
  their own user ID. Organisation-wide or same-client access stays denied until
  organisation membership and the same-client rule are defined.
- Attendees receive only the public projection of Confirmed or Completed
  events; requirements and other planning fields are never included.
- Venue Staff receive concrete venue booking requests through `venueService`;
  the booking record contains the event, venue, date and slot relationship
  needed for approval or rejection.
- Technical Support Staff receive concrete equipment reservations through
  `equipmentService`; the reservation record contains the event, equipment and
  quantity relationship needed to support the arrangement.
- The assigned Event Coordinator remains the only coordinator who can read the
  full request. Venue and technical queues are role-wide until those domains
  define individual staff assignment.
