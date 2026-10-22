# SCRUM-35 creator, registration and date shared rollout — 22 October 2026

**Applied after explicit user approval.** Root applied the exact 0056 → 0058 →
0059 bundle to **SPMG9T4**, Supabase project `rrmvhxrxrrnigjdxcbwt` (PostgreSQL
17.6), as `20261022114717` (`scrum35_versioned_bookings_registration_and_atomic_dates`).
The migration timestamp is 22 October 2026, 11:47:17 UTC / 19:47:17 Singapore time.
Do not reapply these sources. [PR #91](https://github.com/jarenlimhaan/spm/pull/91) publishes source `7095a79` into
`dev`; exact-head CI, human review and merge remain pending. This record does
not declare SCRUM-35 Done.
The [earlier shared record](scrum_35_shared_rollout.md) applies only to 0049/0053,
migration `20261022025742`; do not reapply those sources.

## Exact applied sources and order

| Source | SHA256 |
| --- | --- |
| [0056_event_venue_booking_creation.sql](../../database/migrations/0056_event_venue_booking_creation.sql) | `c6d8acdb4dc7a70255cf31bc0b5b5721d2188782f1595a189424c8f84326944f` |
| [0058_event_registration_reviews.sql](../../database/migrations/0058_event_registration_reviews.sql) | `57263049e6e4c13340ce1aedc374896ec16b6d2eb511dae3259f6fe19c327b41` |
| [0059_event_change_date_approval.sql](../../database/migrations/0059_event_change_date_approval.sql) | `bee8d7ea1b15bd845ae320c98a9442da88e4781400883d7da27614a8e143db05` |

0057 is unused. The reviewed bundle applied **0056 → 0058 → 0059 atomically** with
`SET LOCAL lock_timeout = '3s'` and `SET LOCAL statement_timeout = '30s'`.
The bundle included `NOTIFY pgrst, 'reload schema'` in the same transaction
to refresh the RPC cache on commit. Do not run a bundle that overwrites an existing definition
without comparing its exact current source first. The sources contain no inner
COMMIT; original applied migrations remain unchanged.

0056 adds the versioned service-only booking creator and immutable event/venue
links, and revokes direct service INSERT/DELETE. 0058 adds registration review
evidence/acknowledgement, appends shared readiness facts and replaces the non-date
RPC to accept registration text. 0059 adds nullable accepted-plan evidence and the
atomic date RPC, and extends the existing significant-change trigger so date
changes include linked past equipment reservations. No historical review backfill,
resource reallocation, reservation-date movement or auto-clear is performed.
Attendee records, capacity, windows and lifecycle/status history are unchanged.

## Reviewed preconditions and coordinated cutover

The 22 October read-only preflight found the replacement bases unchanged:

| Existing function | Shared `prosrc` MD5 matching canonical source |
| --- | --- |
| `private.record_event_arrangement_reviews()` (0031) | `ce0e24580e4c3c1087e051dd06badecc` |
| `private.event_readiness_issues(uuid)` (0046) | `1fb3cf057dc97f4dc4e612af529ae542` |
| `public.approve_non_date_event_change_request(...)` (0053) | `cd76e2caa5180a262c0b16525880007b` |

Direct service booking INSERT/DELETE were enabled before application and were
revoked by 0056. The checklist below is retained as the reviewed procedure, not
an instruction to reapply the bundle. Future deployments need current checks
rather than relying on these historical preflight values.

1. Obtain approval for these exact sources/bundle and schedule a cooperative
   **venueService booking-write hold**. Old dev venueService versions use REST
   INSERT and will fail after 0056. Stage the matching new venueService, which
   passes the aware event version to the RPC and has no REST fallback. Coordinate
   the matching eventRequestService and frontend publication as one release;
   applying schema before merge/deploy alone is not a safe cutover.
2. Recheck the target identity, migration history, current transactions and all
   prerequisite tables/columns, enums, constraints and function definitions.
   Confirm merged 0055 and its trigger match source; 0054 guard, existing timing,
   cancellation, shared readiness callers and SCRUM-64 writers/enqueue must be
   present. Last read-only preflight found 0055 present and the 0056 creator,
   0058 registration table and 0059 date RPC absent. Repeat at deployment time.
3. Capture definitions, owners, search paths, grants and enabled trigger wiring
   for every replaced function and affected table. Recheck service SELECT/UPDATE
   on venues, booking UPDATE and the existing event/assignment/requirement access.
   Shared venue SELECT/UPDATE were observed true; a vanilla local fixture gap was
   mirrored only in the guarded disposable bootstrap, not by production grants.
4. Capture counts and whole-row fingerprints for events, proposals, bookings,
   reservations/requirements, status history, reviews/jobs and registration data.
   For existing proposals, compare the pre-existing column projection after
   adding `applied_booking_plan`; separately require it null on all pre-existing
   rows. Do not mistake the intended nullable column addition for data mutation.
5. Apply once, atomically, during the hold. Any lock/statement timeout aborts the
   transaction: stop, inspect blockers and migration history, then review before
   retrying. Do not extend timeouts or retry an ambiguous outcome blindly.
6. Verify source bodies/signatures, service-only RPC execution, empty search
   paths, expected RLS and triggers, revoked booking INSERT/DELETE and unchanged
   business fingerprints before releasing the hold onto updated services.
   Review security-advisor differences against the captured baseline. Normal
   authenticated creator/date/mixed/registration/inbox checks are separate release
   gates; local fixtures do not substitute for them.

## Local proof and shared safety

The [database setup](../../database/README.md#atomic-date-and-mixed-approval-0059)
and independent native CI job use Vera's guarded bootstrap, genuine migrations
and labelled Auth doubles. A fresh PostgreSQL 16 rehearsal passed all seven native
rollback scripts, the duplicate-approval race and three date races. Earlier
owned PostgreSQL 14.20 checks also passed the full atomic bundle; neither version proves shared PostgreSQL 17.6
or normal-user delivery. The three races witness real blocking for a new-venue
creator, stale waiting creator and competing booking approval.

The native scripts contain fault injection and the concurrency harnesses commit
labelled fixtures. **Do not run them on shared Supabase.** Shared validation needs
a separately reviewed bounded smoke/read-only plan, authorised labelled fixtures
and postchecks. Actual shared application and the signed-in journey below are
separate from these local fault/race scripts. PR CI and the story-wide completion
assessment remain separate from deployment evidence.

## Observed shared application and postchecks

- One atomic migration completed successfully. All **20** deployment-time
  before/after full-row business fingerprints were identical, using the old
  proposal projection for the new nullable evidence column. All eight affected
  routine bodies matched the PostgreSQL 16 rehearsal; source hashes above stayed
  unchanged.
- The registration table initially contained zero reviews, with RLS enabled,
  service SELECT-only access and browser roles denied. New public RPCs were
  service-executable only. Direct service booking INSERT/DELETE were revoked,
  UPDATE retained and all three expected triggers enabled. No review backfill
  occurred.
- The advisor reported 27 RLS/no-policy INFO items versus the 26-item baseline,
  the expected new server-only registration table. The same three mutable-search-
  path warnings and leaked-password warning remained; they were neither
  introduced nor claimed fixed here.
- Event/venue images were rebuilt, all five backend services healthy and the
  production frontend running locally on port 3000. These are local application
  images using shared Supabase, not a published remote application deployment.
  No committed race fixtures or fault-injection triggers were used on shared.

Operational readbacks are retained under
`/tmp/scrum35-completion-20261022/root/shared-*.json` as local evidence, not setup
dependencies. The exact source hashes above make the reviewed DDL reproducible.

## Real signed-in mixed-date journey

The labelled event `9d885685-3232-418c-85d5-4433866a115f` and proposal
`6ca13a02-52b2-4d0e-993b-92582a74a449` were exercised with actual organiser,
assigned coordinator, venue staff and technical-support sessions. Screenshots
are retained in `output/playwright/scrum35-live-date-20261022/`.

**Setup boundaries:** booking creation, the coordinator equipment requirement
and technical catalogue/reservation setup used actual authenticated API calls.
Venue catalogue creation, the maintenance block and booking approval used UI.
The organiser used UI to propose 21 November at 11:00 Singapore time, attendance
45 and changed venue/equipment/registration requirements. This was not a mocked
API browser journey or a claim that every setup step used a browser form.

The isolated venue was `0cf2651e-cd5a-4335-b0d1-64b478cd5f98`, with approved booking
`e7311af5-9001-4149-bf68-35fb332b223a` and a 21 November 09:00–10:00 maintenance
block. The coordinator's 09:30–11:30 plan was refused with a visible active-block
conflict. Event, proposal, bookings, reservations, arrangement reviews,
registration reviews, outbox and lifecycle history were all byte-identical
before/after refusal; chosen inputs remained available for retry.

The coordinator then approved 10:30–12:30 through UI. Shared readback confirmed
all five proposal fields applied atomically, Planning/lifecycle history unchanged,
booking ID/status/decision audit retained and accepted ranges visible in both
organiser and coordinator history. Equipment reservation
`9c3a2fa4-7daf-45fd-b5a3-bcb3aa2bf915` retained its 19–20 November dates.

One venue and one equipment review shared actual trigger UUID
`0d339a7a-4b4f-46ee-ab01-dea99fd32157`; two durable jobs delivered to the current
coordinator and respective actual staff. Both staff inboxes were seen, with
correct domain-queue links, fixture IDs/reasons and Mark reviewed controls.
The organiser's actual approval notice and event deep link were also verified.

Registration review `c7825fd3-66b6-4d6a-83ad-abed320f0fc1` was acknowledged through
the assigned coordinator UI. The organiser reload showed saved actor/time and
zero acknowledgement buttons. Actual **Send for safety review** refused all
three review items before acknowledgement and only the venue/equipment items
afterwards; Planning and lifecycle history stayed unchanged. Those two flags
remain deliberately outstanding because arrangements have not been rechecked
or reallocated. This proves the SCRUM-35 flag/delivery/gate integration, not later
staff rearrangement or safety approval.

Root retained `shared-live-before.json`, `shared-live-refused.json`,
`shared-live-approved.json`, `shared-live-final.json` and `shared-live-checks.json`
in the evidence directory above; all 17 final checks were true. Labelled business
fixtures remain as evidence. Source `7095a79` is published in [PR #91](https://github.com/jarenlimhaan/spm/pull/91);
exact-head CI, human review and merge remain pending.

## Failure and recovery

An uncommitted bundle rolls back DDL/grants together and changes no business rows.
On uncertain success, inspect actual migration history/catalogue before doing
anything further. Keep the write hold while checking; never reapply sources
because a client timed out.

After commit, prefer a reviewed forward correction. Restore captured prior
definitions/grants only after dependency and caller review plus explicit root
approval. Disable affected application mutations before any reversal. In
particular, do not restore the old direct booking INSERT/DELETE bypass while the
date writer remains active. Never drop retained reviews/accepted plans, use
CASCADE or try to undo committed decisions by deleting history. Removing a
routine does not undo business decisions already committed.
