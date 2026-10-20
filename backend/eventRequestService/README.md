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
| `GET` | `/event-requests/{id}` | Retrieve one request (owning Organiser or assigned Coordinator) |
| `GET` | `/event-requests/{id}/status-history` | Chronological read-only status evidence, using the same request visibility as SCRUM-39 |
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
| `GET` | `/event-requests/safety-queue` | Safety Officer lists events in `Safety Review`, longest-waiting first (SCRUM-60 AC2) |
| `POST` | `/event-requests/{id}/safety-decision` | Safety Officer approves (→ `Confirmed`) or asks for changes with a reason and affected arrangements (→ `Planning`; the assigned Coordinator is notified) an event in `Safety Review` (SCRUM-60) |
| `GET` | `/event-requests/{id}/safety-reviews` | Safety Officer or the assigned Coordinator reads the safety decisions, newest first |
| `POST` | `/event-requests/{id}/completion` | Assigned Coordinator marks a confirmed event complete (`Confirmed` → `Completed`) |
| `POST` | `/event-requests/{id}/change-requests` | Owning Organiser proposes structured changes to an Approved or Planning event |
| `GET` | `/event-requests/{id}/change-requests` | Owning Organiser or assigned Coordinator reads the amendment history |
| `POST` | `/event-requests/{id}/change-requests/{change_id}/decision` | Deferred: assigned Coordinator receives 409 `CHANGE_DECISIONS_UNAVAILABLE`; no decision is applied |
| `GET` | `/health` | Service health check |

Every event-request operation requires `Authorization: Bearer <access-token>`.
Draft CRUD requires `event_organiser`, coordinator assignment and the
awaiting-assignment queue require `event_operations_manager`, and the
coordinator list and transition commands require `event_coordinator`.
The service asks authService to verify that token with Supabase, then scopes
drafts to the returned user ID. A current assignment may be read by the owning
Event Organiser, an Event Coordinator Lead, or the currently assigned Event
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
| `Safety Review` → `Confirmed` or `Planning` | Safety Officer (role re-checked in the database) | `POST /{id}/safety-decision` |
| `Confirmed` → `Completed` | Assigned Coordinator | `POST /{id}/completion` |

Owned by other stories and **not** implemented here: Planning and Confirmed
(venue/operations stories), downstream venue/equipment/registration conflict
revalidation after an approved change, notification delivery (SCRUM-36), and
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

SCRUM-35 uses migration `0018_event_change_requests.sql`. An owning Organiser
may retain one pending structured amendment while an event is Approved or
Planning. The current increment retains Pending proposals for the owning
Organiser and current assigned Coordinator to view. Approval and rejection
controls are unavailable, and the decision endpoint returns HTTP 409 with
`detail.code = CHANGE_DECISIONS_UNAVAILABLE` after checking the assignment
and request. It does not call the decision RPC or change the event/arrangements,
and no change notifications are sent.

The decision primitive and existing migrations are retained for later integration;
their presence does not enable API decisions. Browser roles cannot read the
change table or execute either workflow function. The original SCRUM-35 criteria
remain outstanding.

## Status history (SCRUM-48)

Apply `database/migrations/0025_event_request_status_history.sql` before deploying
this endpoint in a fresh environment. **Applied to shared Supabase on 10 October
2026 after explicit approval**, migration version `20261010034216`. It installs
triggers, replaces three coordinator RPCs, changes history permissions and adds
baseline rows for existing events. Local and focused shared verification passed;
the full verification script encountered a connector request-state error, so its
assertions were checked in smaller rolled-back blocks. The real repository read
and publishable-key refusal were also verified through shared PostgREST.

`GET /event-requests/{id}/status-history` requires a verified session and reuses
request visibility: the owner, current coordinator and same-client-organisation
Organisers with non-Draft read access can read it. Other relationships receive
404 `HISTORY_NOT_FOUND`; unrelated roles receive 403 `HISTORY_FORBIDDEN`.
There is no history-write endpoint. Browser database roles cannot read the table;
the server role can only select history, while private database triggers insert it.

Creation and each actual status change append one entry in the event transaction.
Refused actions, same-status writes, detail edits and clarification responses add
none. Resume review does add a transition. Entries are ordered by timestamp then
identity, and include previous/new status, actor ID/role, source and timestamp.
Existing events receive an honest system baseline rather than invented earlier
activity. Discarding an unsubmitted Draft removes its history; retained event
history cannot be independently modified or deleted.

The organiser and coordinator detail pages display this timeline separately from
review conversations, change proposals and the progress tracker. Loading, empty
and dependency-error states are explicit. Future status writers must follow the
actor/transaction contract in `database/README.md`; their workflows are not
implemented by this story. See `docs/testcases/scrum_48_testcases.md` for coverage,
evidence and remaining review/deployment checks.

## Arrangement review reads (SCRUM-64, in progress)

Existing `Safety Review` rows are recognised in API status validation and
coordinator in-flight lists, matching PR62 commit
`889764620ba943e1a53d4a1f4a16585c739c2ab4`. The exact upstream migration
`database/migrations/0029_safety_review_status.sql` is a prerequisite; it must not
be reapplied to shared Supabase. This compatibility support does not add a
Planning-to-Safety-Review transition or a Safety Officer decision workflow.

`GET /event-requests/{id}/arrangement-reviews` lists outstanding review records
for the currently assigned `event_coordinator`, ordered by absolute timestamp
and UUID, both descending.
The response retains the arrangement, trigger, changed fields, reason and audit
fields. Owners and domain-only staff receive 403 `ARRANGEMENT_REVIEWS_FORBIDDEN`;
unrelated or former coordinators receive private 404
`ARRANGEMENT_REVIEWS_NOT_FOUND`. Missing authentication retains the existing 401.

Apply `database/migrations/0030_arrangement_review_reads.sql` and
`0031_arrangement_review_event_changes.sql`, then
`0032_arrangement_review_clear.sql` and
`0033_arrangement_review_equipment_unavailability.sql` and
`0035_arrangement_review_shared_reads.sql` and
`0036_arrangement_review_safety_rechecks.sql`,
`0037_arrangement_review_notification_outbox.sql` and
`0038_arrangement_review_notification_delivery.sql`, then
`0040_arrangement_review_safety_recheck_lock_compatibility.sql` for this increment.
All nine are prepared locally and **not applied to shared Supabase**. Apply the
unapplied feature stack in one reviewed transaction or hold writes throughout
rollout; see the database README. Do not reapply prerequisite 0029 or occupy 0034.
Migration 0039 is Tate's independently published handover work and is not copied
into this feature stack.
The server role retains SELECT-only review access and browsers have no access.
An unavailable table or helper returns 502 `Arrangement reviews unavailable`,
never an apparently clear empty queue or a fallback to an older read path.
The coordinator adapter posts only `p_event_request_id` to the server-only
`get_outstanding_arrangement_reviews` RPC. The SQL/STABLE/INVOKER helper returns
full outstanding evidence in descending timestamp/UUID order and can be called
within a server consumer's own transaction, without taking event/resource row
locks or deciding readiness. Coordinator RPC reads and staff table reads share
a descending timestamp/UUID keyset pager. The coordinator POST body remains only
`p_event_request_id`; page ordering and cursor filters are PostgREST query
parameters on its table-valued result. Staff requests retain the authorised domain
and outstanding-row filters on every page. Direct SQL has no helper LIMIT.

A response shorter than the requested 1,000 rows may be a lower server cap, so
only an empty page ends either HTTP read. Clearing previously read rows cannot
shift an offset and hide unread work; failure on any page returns the safe 502
rather than partial evidence. Pages are separate reads, not one database snapshot:
rows cleared after an earlier page can remain in that response and newly raised
rows above its cursor appear on the next refresh. See `database/README.md` for
setup and the separate rolled-back SQL checks.

Migration 0031 records actual significant event updates atomically with reviews
for current/future approved venue bookings and equipment reservations. Dates and
attendance affect both domains; venue/equipment text affects its own domain.
Review reasons retain the relevant before/after values. Equivalent instants,
outer-trimmed text, unrelated edits and Draft/terminal events create no reviews.
This adds no public edit route or SCRUM-35 acceptance workflow. The saved
safety-decision caller and shared readiness consumers remain separately owned
external workflow functions;
lifecycle status is unchanged. Migration 0033 also raises equipment
reviews from the actual status-history cause recorded by the existing equipment
status RPC. It affects only current/future reservations of that catalogue UUID;
restoration does not clear reviews. See `database/README.md` for the shared-lock
limitations and local SQL commands.

Migration 0036 adds a private explicit-target safety-recheck helper only. A privileged decision transaction must supply and validate the actual saved
decision UUID, authorised actor and immutable event/target/reason payload. The
helper validates the complete target set in one unlocked membership snapshot
before any insert and creates one review per distinct pair; exact replay preserves
original reason and clear audit. Migration 0040 replaces 0036's child-row locks so
the trusted caller can hold only its event `FOR UPDATE` without waiting on
booking/reservation rows. The caller must acquire that event lock before invoking
the helper; this is an integration obligation, not a check enforced by the helper. Empty targets create no flags but still require
valid event/decision identities and a nonblank reason. There is no new HTTP route,
Safety Officer decision table or lifecycle action. Browser and service roles
cannot call the writer directly. Current target APIs do not reparent or delete
arrangements, but the database does not enforce membership immutability. Future
membership-change/delete writers must participate in the event lock protocol;
this snapshot is not a lease against arbitrary privileged SQL mutations. See the
database contract for error, caller and concurrency-verification requirements.

For native cross-branch verification, the database README provides an offline
37-file combined fixture pinned at `e7888dcfdb19777722583b471b1d31e49da3f9c4`.
It loads local 0026 Planning support and exact external 0034, 0039 and 0044–0047
from that one reviewed archive. All scopes require the complete stack: current
0046 depends on 0039 and 0047 depends on 0046. Scope selects only the local runner's
`decision`, `handover` or `all` checks. The published caller records the saved
decision and targeted reviews atomically, while approval and handover consume
normal readiness plus outstanding reviews. Caller cross-event target errors are
`22023`; current 0047 also refuses duplicate target pairs before writes, as
covered by upstream AC6-X13. The private helper retains its own `P0002` missing-
target and pair-deduplication contracts. These external
functions are not copied into this feature's migrations or enabled by adding a
new API route here. Current 0046 removes the older local venue SELECT workaround.
The four upstream workflow SQL checks and the local integration runner have
separate commands and evidence; native role checks do not prove JWT/HTTP/browser
access, shared deployment or PR CI. Earlier 4a5bc93 and 0044-only evidence stays labelled historical in the database
README and integration handoff; it is not a current e7888dc verification claim. The independent
30-file SCRUM-64 fixture is unchanged. No runtime code or shared database is
changed by this documentation update.

`GET /arrangement-reviews?arrangement=venue_booking` gives `venue_staff` its
role-wide outstanding venue queue; `arrangement=equipment_reservation` gives
`technical_support` its equipment queue. The domain is required and no event
assignment or previous-editor ownership is required for staff. The same newest
instant/UUID order and full evidence response apply without exposing the event
ticket. Staff remain forbidden from the coordinator-only event-wide endpoint.

`POST /arrangement-reviews/{review_id}/clear` has no request body. The backend
derives actor ID and allowed domains from the verified auth-service caller.
The service-only RPC locks that exact review, rechecks domain and outstanding
state, writes only `cleared_at`/`cleared_by`, and returns the complete review.
It does not clear other flags, including newer flags for the same arrangement.
Responses are 403 `ARRANGEMENT_REVIEW_FORBIDDEN` for an unrelated role/domain,
404 `ARRANGEMENT_REVIEW_NOT_FOUND` for an absent review and 409
`ARRANGEMENT_REVIEW_ALREADY_CLEARED` for a repeat. Queue/clear storage failures
return the same safe 502 message as event reads. Direct table writes remain
unavailable to caller roles; no resources, statuses or notifications are changed.

## Arrangement-review notification delivery (SCRUM-64)

Migration 0037 enqueues one immutable raised snapshot for each new review in the
same source transaction; enqueue failure rolls back the source update and flags.
There is no historical backfill. Migration 0038 stores first accepted timestamps
per recipient and the last attempt time, behind three service-only RPCs. Review
and outbox table writes remain unavailable to browser/server REST callers.

The background relay sends `arrangement_needs_review` with full recorded target,
trigger, reason and changed-field evidence. Its stable `event_id` is UUID5 using
`NAMESPACE_URL` and `needs-review:{trigger_id}:{arrangement_id}`. A
`change_request_id` is added only when the trigger is an actual same-event
Approved change-request record; a generic direct-edit cause never invents one.
Only HTTP 202 records acceptance. A timeout or other status keeps that recipient
pending; retries retain the same event identity. The receiver's unique
`(recipient_id, event_id)` stores one inbox row, not exactly-once HTTP delivery.

Each attempt resolves the latest assigned existing account still holding
`event_coordinator`, and all current existing same-domain `venue_staff` or
`technical_support` accounts. Nonempty authoritative `staff_roles` replaces
metadata; otherwise trusted app metadata uses the auth service's filtered
string-list, singular-role and attendee fallback rules. This native aggregate
avoids REST directory pagination loss. Removed staff/former coordinators receive
no new sends in later attempts; accepted progress remains. Overlapping recipients
are sent once. Both required groups must exist and all their current members
must be accepted before publication, so partial delivery and absent groups leave
durable unresolved work. Recipient selection is an attempt snapshot, not a lock
across the remote HTTP request.

The relay rotates batches of at most 50 by never/least-recently attempted work,
then source time/ID. Directory lookup failure retains its attempt stamp and logs
an unresolved lookup; individual recipient/job failures do not stop later work.
It waits 10 seconds after each pass when Supabase and
`NOTIFICATION_SERVICE_URL` are configured. The app lifespan starts it and waits
for its bounded in-flight work before closing the client on shutdown. With the URL unset, both notification
relays remain off and queued work is retained.

Pending review jobs have no maximum-attempt count, expiry or automatic drop.
Missing current recipients and delivery outages retain the job for later recovery;
accepted recipient progress and stable delivery identities remain available for
retry deduplication. The 50-job batch limits each sweep, and the 10-second pause
separates passes; neither limits lifetime attempts or the total queue. Recovery
latency depends on backlog, new work and dependency availability; no fixed delivery
deadline is promised.

To run delivery locally, start notificationService on port 8005 using its README,
set the event service's **server-only**
`NOTIFICATION_SERVICE_URL=http://127.0.0.1:8005/notifications/events`, then start
`uvicorn app.main:app --reload --port 8003`. Use the same prepared database for
both services. Start authService on 8001 and the frontend on 3000 for the protected
inbox and review UI. This does not apply any migration to shared Supabase.

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
