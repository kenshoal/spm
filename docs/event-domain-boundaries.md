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

Until that contract is implemented, the organiser UI can accurately show
`Draft` and `Submitted`. Later coordination and completion states must not be
invented in `eventRequestService`.
