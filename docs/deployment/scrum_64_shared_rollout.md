# SCRUM-64 shared deployment record

**Status: explicitly approved nine-file bundle applied successfully on 20 October
2026; shared privilege and rolled-back mechanism checks passed.** Root reported
the successful application and checks below. Real-auth application and notification
delivery checks remain outstanding; this is not a full feature-closure claim.

Earlier automatic approval review rejected the full-bundle dry run because
production DDL locks could affect other work. No writes were applied by that
rejected attempt. Root subsequently obtained explicit human approval for this
exact reviewed bundle before applying it. That approval has been fulfilled;
do not rerun the non-idempotent source files.

Target: Supabase project `rrmvhxrxrrnigjdxcbwt`.
Reviewed source: `d3acb095bbd15c8b6d58231309dad13b099aaaf8`.
Application: merged `origin/dev`, with SCRUM-64 and later pagination fixes. The
original dirty SCRUM-35 checkout is outside this rollout and must stay untouched.
Root owns shared execution and runtime orchestration; Vera owns verification.

## Exact bundle and application boundary

These **nine unchanged files were applied in this order in one atomic migration
call**. The actual migration-history record is
`20261020093041 scrum64_arrangement_reviews_atomic_rollout`. Preserve this single
record and the source bytes; do not simulate nine applied records or edit already
applied migrations. The source byte total is 29,759; hashes below bind the review.

| Order | Repository source | SHA256 |
| --- | --- | --- |
| 1 | `database/migrations/0030_arrangement_review_reads.sql` | `aa83213360897b30fc200fbc339a77ed2c6138385c9902c7259020d2692244d2` |
| 2 | `database/migrations/0031_arrangement_review_event_changes.sql` | `f6bff00b0f218a3abb2ce67b3d01d72d12727c4ce3e3dd18647a39032dffd76f` |
| 3 | `database/migrations/0032_arrangement_review_clear.sql` | `8fda18390a0e05e8e272c56830ac04354ac7b69d7018ee019b56adf90851c056` |
| 4 | `database/migrations/0033_arrangement_review_equipment_unavailability.sql` | `72d3705a8b31c88f181f2c2449ef7ea794abd354d0dba0bd30823d66290de56d` |
| 5 | `database/migrations/0035_arrangement_review_shared_reads.sql` | `586a1b54aa92ae2145145f3448a8301696e3780dbcce7587453e45aee954d0a4` |
| 6 | `database/migrations/0036_arrangement_review_safety_rechecks.sql` | `9f6d3a317d6db0641cf29acd5a66548508e203163ec7149d85fc694606f949fb` |
| 7 | `database/migrations/0037_arrangement_review_notification_outbox.sql` | `2c9d23fae27158531b8b4ef63aa802a8837a304fb24966ef084d68f4822be2a9` |
| 8 | `database/migrations/0038_arrangement_review_notification_delivery.sql` | `7d8707cfecb361fb4bf44636b190f662ae0fcd6a88125e2b1eb1b298ac22b6af` |
| 9 | `database/migrations/0040_arrangement_review_safety_recheck_lock_compatibility.sql` | `be3bff0b010d71c56dcf9b961adc3b2e3469b8603e2a6c5439ebef50a117d828` |

The approved execution used transaction-local limits of **lock_timeout
3 seconds** and **statement_timeout 30 seconds**. The migration executor must
supply the single transaction and commit/record boundary; do not insert an early
COMMIT or split the files into individually visible stages. The source files have
no transaction-ending statements. A statement timeout is not a promised total
rollout duration. Observe any timeout/error and stop; do not increase the limits
or retry blindly while other activity is holding locks.

0031/0033 install source flag writers before 0037 installs enqueue. Keeping these
in one transaction prevents any committed interval with flags but no queued job.
0036 is the historical child-lock helper; 0040 replaces it before commit, so no
caller observes that intermediate body. Retain all original migration bytes.

## Read-only prerequisites and baseline

Root's pre-application baseline on 20 October 2026 confirmed:

- No arrangement review table, review outbox or SCRUM-64 functions existed;
  there were no recorded SCRUM-64 feature migrations before this rollout.
- Existing event_requests, venue_booking_requests, equipment_reservations,
  equipment_requirements, safety_reviews and private schema are present.
- Required source columns match, including equipment history old/new status,
  equipment ID/reason and trusted auth.users.raw_app_meta_data.
- Equipment status history has **9 rows, approximately 40 KB**. 0033's volatile
  UUID default and unique constraint can rewrite/index-lock that table despite
  its small baseline size. The post-application count remains nine, with nine
  populated history UUIDs. Recheck size and locks for any future change.
- 0034 and 0044 are already recorded/applied. Do not reapply either. The relevant
  shared Auth directory contains 11 accounts; this plan creates no account/role.

Also retain the existing 0025 actor/history and event-assignment contracts. The
recipient resolver requires staff_roles, event_coordinator_assignments and
0018's event_change_requests. Check final object existence, ownership and grants
against the actual target before applying: a partial/changed target requires a
new review, not a blind rerun of non-idempotent CREATE TABLE/ADD COLUMN statements.

## Data, security and lock effects

The bundle creates arrangement_reviews and arrangement_review_notification_outbox
with RLS enabled, no browser policies, explicit revocations from PUBLIC, anon,
authenticated and service_role, then service-role SELECT only. Browser roles have
no direct table access. Narrow public clear/attempt/accept/complete RPCs have
empty search_path, revoke browser/PUBLIC execution and grant service_role only.
Private trigger functions and the explicit-target helper revoke direct execution,
including service_role. No broad review/outbox table write grants are introduced.

Native audit/enqueue functions are narrow SECURITY DEFINER triggers. The shared
reader is SQL/STABLE/INVOKER; the private explicit-target writer is INVOKER and
must be called from a trusted privileged saved-decision transaction. Its caller
verifies the actual decision/roles/payload and holds the event FOR UPDATE.
0040 validates all target memberships at one snapshot without child-row locks.
It is not a membership lease against privileged reparent/delete; future such
writers must join the event protocol. No general cross-story concurrency claim
is made.

Recipient authority uses nonempty staff_roles first, otherwise trusted
raw_app_meta_data roles/list/singular fallback. Editable user metadata is never
used. Current existing coordinator and domain staff are resolved on each attempt;
no previous-editor ownership is inferred. Missing groups remain pending, with
accepted progress and stable UUID5 delivery identities retained. There is no
attempt cap, expiry or automatic drop.

0033 adds stable review_trigger_id UUIDs to existing equipment history records.
This is **audit identity population only**: no historical flags, reconstruction
or notification backfill. No business event, booking, reservation, lifecycle,
role or account is deleted/rewritten by this bundle. Normal accepted future
source edits raise flags and outbox work atomically; a write failure rolls back
the source action. 0038 replaces only its own pending-outbox index.

## Verification after an approved commit

1. Record the real migration version/name and bundle/source digests. Confirm the
   one intended migration record, both tables and the added history UUID column/
   unique constraint. Confirm no unintended partial or duplicate record.
2. Inspect final function definitions and privileges. Check 0040's final helper
   takes no child-row locks; both source audit triggers and the enqueue trigger
   are attached; public mutation RPCs are service-only and private functions are
   not directly callable by service/browser roles. Check RLS/table grants apart
   from application authentication.
3. Expected trigger names: record_event_arrangement_reviews on event_requests,
   record_equipment_unavailability_reviews on equipment_status_history and
   enqueue_arrangement_review_notification on arrangement_reviews. Preserve
   existing status-history, event submission and other workflow triggers.
4. Verify server PostgREST reads and browser denial after its schema cache sees
   the committed functions/tables. If cache visibility lags, diagnose it before
   claiming a missing migration or reapplying the bundle.
5. Use a separately reviewed bounded shared-safe rolled-back smoke supplied by
   Vera/root, plus authorised normal-auth API/UI and delivery checks. Record
   actual recipient effects if a worker sends a notice. Do not claim all seven
   ACs from metadata or an empty queue alone.

**Do not execute disposable native scripts unchanged on shared infrastructure.**
The delivery script renames auth.users and creates disposable users/role rows.
Several other scripts install fault triggers on business tables or temporarily
grant equipment/history privileges for a vanilla local fixture. Even rolled-back
DDL takes locks and can disrupt concurrent use. Keep the full fault/role/concurrent
suite local; do not transplant those setup operations into the shared smoke.

## Runtime activation and separate owner handoff

Baseline: local port 8003 refused connections and Docker had no running
containers. The fresh rollout checkout has no .env. The existing original root
configuration points at the intended project and has a server key present;
values must never be printed, copied to frontend or committed. Root must provide
that approved configuration explicitly when starting the isolated runtime.

For initial read-only health/API-schema checks before deliberate delivery, disable
notification delivery **in runtime configuration only**: normal Compose supplies
NOTIFICATION_SERVICE_URL and can otherwise start the existing submission relay,
send notices and update outbox rows even during a health check. Do not alter the
original .env. The schema application is now approved and verified; root must
still enable the correct API/Auth/
notification/UI services, confirm their project, normal authentication and worker
lifecycle, then record bounded delivery results. URL unset retains queued work.

A subsequent bounded local HTTP check started the canonical event service from
this rollout checkout with the existing original server configuration read in
memory only. `NOTIFICATION_SERVICE_URL` was absent, settings resolved it to
`None`, and both submission/review relay builders returned `None` before startup.
`GET /health` returned 200; unauthenticated staff-domain and coordinator review
reads both returned 401 `Authentication required`. The owned service processes
were stopped cleanly afterwards. No original dotenv file, Auth account or shared
data was changed and no delivery worker ran. The redacted startup description
and HTTP results are retained as `runtime-readonly-http-results.json`. This
proves health and the missing-auth boundary, not a successful real-user session,
authorised database read or notification delivery.

The Jaren 0045 saved-decision caller was **subsequently applied separately** as
`20261020093706 safety_review_arrangement_reviews`; it was not part of the
nine-file deployment. A read-only catalogue comparison confirmed that its live
`public.decide_safety_review` body exactly matches canonical 0045. The function
holds the event `FOR UPDATE`, saves the actual safety decision before invoking
the private helper and refuses approval while the shared reader reports reviews.
Its owner is `postgres`, matching the helper owner, and its execution grant remains
service-only. No reapplication or modification of that owner's work is needed.
Do not silently apply unmerged/archived 0039, 0046 or 0047, deploy SCRUM-35's 0049
or claim a complete normal-readiness/handover workflow here.

Root sent the successful prerequisite handoff to Jaren/Tate in **Agent Discussions
message #2440**. That message identifies the subsequent owner-controlled sequence:
0045 with its own verifier, then 0039/0046, then 0047. The later 0045 application
is now confirmed independently; the communication alone does not prove the
remaining stages have been deployed.

## Failure and recovery

- Before commit: any lock timeout, statement timeout, syntax/permission failure
  must abort the whole transaction. Inspect rollback and object/migration-record
  state read-only. Do not retry through another tool or assume partially visible
  CREATE objects are safe to rerun.
- After commit: preserve review/audit/outbox data and the applied migration
  record. Prefer a reviewed forward fix. Dropping tables/cascading data or removing
  audit identities is not an automatic rollback and loses evidence.
- If a defect blocks source writes, hold affected writes and pause delivery while
  root investigates. Do not silently disable flag/enqueue triggers while allowing
  new writes to bypass review capture. Any emergency change needs explicit review.
- Preserve accepted-recipient progress. A 202 accepted before acknowledgement
  storage can be retried with the same stable event ID; receiver deduplication
  prevents a second inbox row. No exactly-once HTTP claim is made.
- Resume retained pending work once verified. Do not invent historical backfill
  for changes that happened before installation. Record any interrupted interval
  honestly and obtain a separate recovery decision if required.

## Local rehearsal before shared approval

The canonical independent setup in `database/README.md` was reproduced on a
fresh owned PostgreSQL **16.15** container: the unchanged empty-target guarded
`database/tests/bootstrap_event_status_history.py` followed by the exact **30
supplemental files** succeeded. Each supplemental file committed separately,
including 0041 before 0042. The local Auth metadata column is a disposable test
double prerequisite, not a proposed change to Supabase Auth.

The rehearsal container has no host port and no external network. Its local
adapter accepts only the fixed `scrum48_64_rollout_review` loopback DSN. The source
order/digests and setup log are retained in the rollout evidence directory. This
checks the canonical local schema. The separately reviewed smoke and privilege
checker passed locally after an explicit local-only baseline ACL fixture matching
permissions verified on the shared project. The first local smoke attempt had
stopped at a missing equipment baseline grant; that was a fixture prerequisite,
not a product correction or a proposed shared grant. The ten existing strict SQL
verification scripts then passed sequentially, with their fixtures rolled back.
No external 0039, 0046 or 0047 was loaded, and no independent 0045 caller
deployment is implied.

A second fresh owned, portless PostgreSQL 16.15 container reproduced the guarded
bootstrap and the same 21 non-feature prerequisites, then committed the exact
nine-file bundle above in **one transaction** with transaction-local lock timeout
3s and statement timeout 30s. The unchanged privilege checker passed afterwards.
The concatenated local rehearsal script has SHA-256
`39dd95a6080c16593c5ca510f048c169345178c7fdcc2b1fda10f49a75e86337`.
Its individual embedded migration bytes match the source manifest. This tests
local combinability and bounded execution; it does not create a Supabase migration
record or prove shared deployment, shared lock availability or normal-auth HTTP
delivery. The subsequent shared execution evidence is recorded below separately.

## Execution record

Root reported the following actual shared results on project
`rrmvhxrxrrnigjdxcbwt` after explicit human approval:

- Migration `20261020093041 scrum64_arrangement_reviews_atomic_rollout` succeeded
  with the exact nine-file source bundle pinned above and the reviewed 3s/30s
  transaction-local limits.
- `database/check_arrangement_review_rollout_privileges.sql` passed. Its reviewed
  SHA-256 is `8a5cff3c035dbe3409cf82a0af905d6ccc79dc58ed8c407e114a7c290e76d22c`.
- `database/verify_arrangement_review_shared_rollout.sql` passed and completed
  `ROLLBACK`. Its reviewed SHA-256 is
  `0ed847acb20282fd6d0a2ea7d613d970707f94a9b1f5425455971f5fe1b7b52b`.
- Post-checks found zero scoped smoke-fixture events, zero reviews and zero
  review-outbox rows. Equipment status history retained its nine rows and now
  has nine populated `review_trigger_id` UUIDs, matching 0033's actual column.
- The security advisor added the two expected RLS-without-policy informational
  findings for the server-only review tables. The same three existing mutable
  search-path warnings and existing Auth leaked-password warning remain; this
  rollout does not resolve or newly attribute those pre-existing warnings.

Root retained a concise transcription of the observed Supabase MCP results as
`shared-rollout-observed-results.json` in the rollout evidence directory. It is
labelled as a transcription, not a raw MCP export. Agent Discussions #2440 records
the corresponding owner handoff; Jira evidence comment #10047 records the
deployment evidence.

After the separate 0045 application, root reran both unchanged reviewed shared
scripts: privilege/RLS verification passed and the mechanism smoke passed with
`ROLLBACK`. Scoped event/review/outbox fixtures remained absent. Read-only catalogue
review independently confirmed all three SCRUM-64 triggers enabled alongside the
existing submission, status-history, update-timestamp and organisation-stamping
triggers. The six inspected SCRUM-64 function bodies and the 0045 caller body
exactly match canonical source, including the final 0040 helper without child
locks. Function ownership, empty search paths and private/service-only execution
boundaries also match. Evidence is retained in
`shared-regression-after-0045.json`, `shared-workflow-catalog-review.json` and
`shared-workflow-function-comparison.json`.

This review found no demonstrated SCRUM-64 workflow regression. Two deliberate
boundaries remain: source writes roll back if required review/outbox persistence
fails, and membership validation is a single snapshot rather than a lease against
arbitrary privileged reparent/delete. The current 0045 source explicitly defers
ordinary venue/equipment readiness validation; no public function named for
readiness or handover appeared in the inspected live catalogue. These later
owner-controlled gates must not be presented as enabled by SCRUM-64's deployment.

Still outstanding: real-auth API/UI access, end-to-end notification acceptance
and inbox delivery, the real-user saved-decision workflow and separately owned
0039/0046/0047 readiness stages. Native
SQL/service-role checks do not prove JWT authentication or HTTP worker delivery.
The earlier disposable fault/concurrency evidence remains separate and
attributable to its own environment. Preserve all source SQL and the unrelated
SCRUM-35 working changes.

## Publication check against current dev — 20 October 2026

The isolated evidence branch integrated `origin/dev` at `498543b` without
conflicts. No production source or previously applied migration was changed.
The full eventRequestService suite passed **555 tests, 0 failed/skipped**, with
two existing dependency deprecations (4.77s), using the installed event-service
Python and `SCRUM64_NOTIFICATION_RUNTIME=/tmp/scrum64-notification-runtime/bin/python`:
`python -m pytest -q -p no:cacheprovider` from that service. The first restricted
attempt had 554 passes and a local socket-permission fixture error; rerunning
with loopback permission passed without modifying the tests or product.

The four focused frontend arrangement-review test files recorded in the story
matrix passed **14 tests** (996ms). The first restricted attempt could not write
the reused dependency cache; the permitted rerun passed unchanged. These are
local tests, with the doubles and loopback-notification limitations already
recorded above, not authenticated shared-app evidence.

After the separately owned 0039/0046 and 0050 rollouts, both unchanged approved
shared-safe scripts passed again through Supabase MCP: the privilege/RLS check
and the mechanism smoke with explicit ROLLBACK. This demonstrates continued
mechanism compatibility with those deployed prerequisites; it does not prove
0047 is deployed or the real user/inbox journey.

SCRUM-64's live Jira status was already Done before this publication step. This
record does not alter its ACs or status and does not conceal the outstanding
normal-user and committed-delivery evidence. The publication PR requires human
review and its own CI. No SCRUM-35 working changes are part of this branch.
