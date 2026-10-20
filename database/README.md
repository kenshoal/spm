# Database

All backend services share one Supabase (Postgres) database, so the schema lives here — above any single service — as plain SQL migrations applied in filename order.

## Applying a migration

Migrations are applied manually through the Supabase dashboard (there is no CLI/`psql` access from CI):

1. Supabase dashboard → **SQL Editor** → **New query**.
2. Paste the full contents of the next unapplied file from `migrations/` (filename order: `0001`, `0002`, …).
3. **Run**, and repeat until every file is applied.

Apply each file exactly once and never edit a file that has already been applied — new changes go in a new file.

## Migrations

| File | Purpose |
| --- | --- |
| `migrations/0001_baseline.sql` | `equipment` and `equipment_status_history` tables, status CHECK constraints, indexes. **Reference snapshot / fresh environments only** — this state already exists in the live DB; do not re-run it there |
| `migrations/0002_transition_equipment_status.sql` | `transition_equipment_status` RPC: atomic status change + history row; ERRCODE `P0002` for unknown ids |
| `migrations/0003_create_equipment_fn.sql` | `create_equipment` RPC: atomic insert of the equipment row + first history entry |
| `migrations/0004_quantity_history.sql` | `equipment_quantity_history` audit table + `update_equipment_quantity` RPC (row lock, ERRCODE `P0002`) |
| `migrations/0005_rls_and_function_access.sql` | RLS enabled on the three equipment tables (default-deny for anon/authenticated). Its function revokes were a no-op — see 0006 |
| `migrations/0006_rpc_execute_grants.sql` | RPC `EXECUTE` revoked from `PUBLIC` (which anon/authenticated inherit through) and granted explicitly to `service_role` |
| `migrations/0007_event_requests.sql` | Event-request table, validation constraints, update timestamp trigger and organiser-only RLS policies. The shared development project already matched this schema on 20 September 2026 |
| `migrations/0008_event_request_submission_outbox.sql` | Private transactional outbox and triggers that record one `event_request.submitted` event for a direct submission or Draft-to-Submitted transition |
| `migrations/0009_event_request_outbox_organiser_index.sql` | Covering index for the outbox organiser foreign key and future notification-recipient lookups |
| `migrations/0010_staff_roles.sql` | `staff_roles` role-assignment table keyed by `(user_id, role)`, RLS enabled, service-role access only |
| `migrations/0011_event_coordinator_assignments.sql` | `event_coordinator_assignments` append-only table backing Coordinator assignment and the awaiting-assignment queue. **Reference snapshot / fresh environments only** — this table was created by hand in the dashboard and already exists live; do not re-run it there |
| `migrations/0011_event_request_review_status.sql` | Full event-request status constraint and server-only access to coordinator assignment history; API services enforce actor and transition rules |
| `migrations/0012_coordinator_status_transitions.sql` | `advance_event_request_by_coordinator` RPC (SCRUM-28): locks the request row, re-checks the latest coordinator assignment and applies one coordinator transition atomically. ERRCODE `P0002` not found, `P0003` not the assigned coordinator, `P0004` transition not allowed. Revokes `EXECUTE` from `PUBLIC` only — see 0013 |
| `migrations/0013_coordinator_transition_execute_grants.sql` | Revokes the direct `EXECUTE` grants Supabase's default privileges give `anon` and `authenticated` on the 0012 function, leaving `service_role` only (same fix as 0005 + 0006 for the equipment RPCs) |
| `migrations/0014_atomic_coordinator_assignment.sql` | `assign_event_request_coordinator` RPC: locks the event request, validates its state and the target coordinator role, then inserts assignment history atomically. Server role only |
| `migrations/0015_harden_coordinator_transition_search_path.sql` | Pins the SCRUM-28 transition RPC to an empty search path, clearing the Supabase mutable-search-path warning without changing behavior |
| `migrations/0016_event_request_review_decisions.sql` | SCRUM-17 review history plus server-only atomic RPCs for decisions, organiser clarification responses and resuming review |
| `migrations/0017_notifications.sql` | `notifications` table for SCRUM-37: one row per recipient per event, unique `(recipient_id, event_id)` so a retried event is stored once, newest-first inbox index, RLS on with service-role access only |
| `migrations/0018_event_change_requests.sql` | SCRUM-35 change-request history and creation RPC; decision RPC retained for later work, currently blocked by the public API |
| `migrations/0018_venue_booking_requests.sql` | `venue_booking_requests` table for SCRUM-32: dates, slots and status with CHECK constraints (slot rules as in `venue_blocks`, decision fields always consistent with the status), a restrictive foreign key to `venues`, four lookup indexes, RLS on with service-role access only. Applied to shared development on 4 October 2026 |
| `migrations/0019_event_change_requests_organiser_index.sql` | Covering index for the SCRUM-35 organiser foreign key |
| `migrations/0019_client_organisations.sql` | SCRUM-39: `client_organisations`, `organisation_members` (one organisation per Organiser) and `event_requests.organisation_id`, stamped from the Organiser's membership on insert and never changed afterwards. RLS on, service-role access only. Verify with `verify_client_organisations.sql`. Applied to the shared development project on 5 October 2026 |
| `migrations/0020_equipment_reservations.sql` | `equipment_reservations` table for SCRUM-10: units of an equipment row committed to an event, `quantity > 0` and `return_date >= collection_date` CHECKs, FKs to `equipment` and `event_requests`, hold-window index, RLS on with service-role access only. Starts empty; SCRUM-13 writes rows. Applied to the shared development project on 6 October 2026, replacing the placeholder table from `feat/scoped-resource-access` (SCRUM-39), which was dropped the same day once the two stories deconflicted — SCRUM-10's hold-ledger schema (`collection_date`/`return_date`) is the canonical one |
| `migrations/0020_event_change_request_updated_at.sql` | Advances the event version timestamp when an amendment is approved |
| `migrations/0021_event_change_request_monotonic_updated_at.sql` | Makes the approval-side timestamp assignment strictly monotonic |
| `migrations/0021_equipment_requirements.sql` | `equipment_requirements` table for SCRUM-33: what equipment an event needs (`quantity >= 1`, 2,000-character limits on the free-text columns, blank type refused), the event snapshot, and `requested`/`in_progress`/`arranged` with audit fields that must move together; `transition_equipment_requirement` RPC applies one arrangement transition under `FOR UPDATE` (ERRCODE `P0002` unknown id, `P0004` disallowed, stale or note-less update), two oldest-first lookup indexes, RLS on with service-role access only. Applied to shared development on 7 October 2026 |
| `migrations/0022_monotonic_event_request_updated_at_trigger.sql` | Makes the shared event-request update trigger monotonic, including multiple writes in one transaction |
| `migrations/0023_venue_blocks.sql` | `venue_blocks` table for SCRUM-23 with its `block_reason` and `block_status` enums, a foreign key to `venues` and a per-venue index. **Reference snapshot** of the table created by hand in the dashboard (safe to re-run: it skips existing objects), plus RLS on and `REVOKE ALL` from `anon` and `authenticated`, so only venueService's secret key can read block reasons. Applied to shared development on 6 October 2026 through the SQL Editor; afterwards `has_table_privilege` returns false for `anon` and `authenticated`, and the publishable key gets `401` (`42501`) while venueService still reads both existing blocks |
| `migrations/0024_venue_booking_decisions.sql` | SCRUM-15: `venue_booking_refusals` append-only log of refused approvals (who, when, reason codes, conflicting block and booking ids), plus server-only `decide_venue_booking_request` (locks the venue row, then the request row; approves, rejects with a required reason, or records a refusal for `venue_unavailable` / `outside_operating_slots` / `active_block` / `booking_conflict`) and `create_venue_block` (same venue lock). Errors: `P0002` not found, `55000` already decided, `22023` invalid decision. RLS on and no browser-role access. Verify with `verify_venue_booking_decisions.sql`. Applied to shared development on 8 October 2026 through the SQL Editor; afterwards the secret key reads `venue_booking_refusals`, the publishable key gets `401` on the table and on `decide_venue_booking_request`, and an unknown request id returns `P0002` without writing |
| `migrations/0025_event_request_status_history.sql` | SCRUM-48: immutable event status history, atomic insert/update triggers, honest legacy baselines and actor context in three existing coordinator RPCs. Browser access revoked; service role reads only. **Applied to shared development via MCP on 10 October 2026, version `20261010034216`; local and focused shared checks passed** |
| `migrations/0026_event_request_planning.sql` | SCRUM-58: replaces `advance_event_request_by_coordinator` from `0025` with one added move, Approved → Planning, recorded in status history as `coordinator.planning`. Lock, latest-assignment check and grants unchanged. Verify with `verify_event_request_planning.sql`. **Applied to shared development via MCP on 13 October 2026, version `20261013134214`**, after checking the live function still matched `0025`. Full verification ran on a disposable local cluster; on shared, only read-only checks (definition, grants) were run |
| `migrations/0027_equipment_reservation_requirements.sql` | SCRUM-13: `equipment_reservations.requirement_id uuid NOT NULL` referencing `equipment_requirements` (numbered past 0025 and 0026, taken by SCRUM-48 and SCRUM-58). Two indexes (outstanding quantity per requirement, per-event listing) and the server-only `reserve_equipment` RPC: locks the requirement then the equipment row, re-checks the row's status, the requirement's outstanding quantity and the units held on the busiest day of the hold window, then inserts with `event_request_id` copied from the requirement. `P0002` not found, `P0004` refused. Verify with `verify_equipment_reservation_writes.sql`. **Applied to shared development on 14 October 2026 through the SQL Editor, after confirming the table was empty** |
| `migrations/0028_reserve_equipment_type_check.sql` | SCRUM-13 D12: replaces `reserve_equipment` from `0027` with one added check under the lock: the catalogue row's type must match the requirement's (trimmed, whitespace collapsed, case ignored), else SQLSTATE `22023`, which equipmentService maps to 422. `0027` is not edited because it is applied to shared development. Grants restated (service role only). Verify with `verify_equipment_reservation_writes.sql`. **Applied to shared development on 15 October 2026 through the SQL Editor**: before it, the verify script stopped at AC1-N10 (expected Red); after it, both verify scripts passed and the grants were `service_role` and the owner only. Also verified on a disposable local PostgreSQL 16 cluster the same day |
| `migrations/0029_safety_review_status.sql` | SCRUM-60 increment 1: adds the `Safety Review` event status (between Planning and Confirmed) and the `safety_officer` staff role, and replaces `advance_event_request_by_coordinator` from `0026` with one change: a coordinator may cancel during `Safety Review`. No coordinator path reaches `Confirmed`. Verify with `verify_safety_review.sql`. Exact prerequisite adopted unchanged from PR62 commit `889764620ba943e1a53d4a1f4a16585c739c2ab4`; existing shared migration, do not reapply there. |
| `migrations/0030_arrangement_review_reads.sql` | SCRUM-64 first read slice: arrangement review identity/audit constraints and event/time index. RLS enabled; browser access revoked and service role SELECT only. **Prepared, not applied to shared Supabase**. No flag writers, clearing or notification workflow. |
| `migrations/0031_arrangement_review_event_changes.sql` | SCRUM-64 native event-detail audit trigger raises per-target review work atomically for significant actual edits. Private, non-callable writer; review table remains service-role SELECT only. **Prepared, not applied to shared Supabase**. No clearing or notification workflow. |
| `migrations/0032_arrangement_review_clear.sql` | SCRUM-64 service-only exact-review clear RPC: row lock, trusted backend domain scope, stale refusal and audit-pair-only update. Review table grants remain SELECT only. **Prepared, not applied to shared Supabase**. |
| `migrations/0033_arrangement_review_equipment_unavailability.sql` | SCRUM-64 native equipment-history trigger flags exact-equipment current/future reservations for actual unavailable transitions, using a stored history UUID. Existing status RPC/API and SELECT-only review grants unchanged. **Prepared, not applied to shared Supabase**. |
| `migrations/0034_safety_review_decisions.sql` | SCRUM-60 increment 2: insert-only `safety_reviews` (decision, reason, targets as made; RLS on, `service_role` SELECT only) and the server-only `decide_safety_review` RPC: locks the event row first, `P0002` not found, `P0003` caller not currently a `safety_officer`, `P0004` not in `Safety Review`, `22023` invalid decision, reason or targets; then records the review and history actor and moves to `Confirmed` or `Planning`. No booking/reservation row locks (SCRUM-58 gate protocol). Raising SCRUM-64 arrangement reviews and the approval re-checks follow in a later migration. Verify with `verify_safety_review_decisions.sql`. **Applied to shared development via MCP on 18 October 2026, version `20261018031650`**; read-only grant checks passed afterwards |
| `migrations/0035_arrangement_review_shared_reads.sql` | SCRUM-64 server-only shared outstanding-evidence function: STABLE INVOKER, full rows/reasons ordered by timestamp and UUID. No locks, readiness verdict or mutation grants. Coordinator adapter uses this RPC; staff domain queues unchanged. **Prepared, not applied to shared Supabase**. |
| `migrations/0036_arrangement_review_safety_rechecks.sql` | Original SCRUM-64 private explicit-target writer; its child-row locking is replaced by 0040. Preserved unchanged for migration history. **Prepared, not applied to shared Supabase**. |
| `migrations/0037_arrangement_review_notification_outbox.sql` | SCRUM-64 atomic per-new-review notification snapshot; private enqueue trigger, service SELECT only and no historical backfill. **Prepared, not applied to shared Supabase**. |
| `migrations/0038_arrangement_review_notification_delivery.sql` | SCRUM-64 current-recipient aggregate and narrow service-only attempt/acceptance/completion RPCs, durable per-recipient progress and fair pending index. **Prepared, not applied to shared Supabase**. |
| `migrations/0039_send_for_safety_review.sql` | SCRUM-58: server-only `send_event_request_for_safety_review` moves Planning → Safety Review for the latest assigned coordinator when the event has an approved venue booking, no pending one, and every equipment requirement fully reserved. Otherwise `P0005` with the outstanding items as JSON in `DETAIL`; also `P0002` / `P0003` / `P0004`. Recorded in status history as `coordinator.safety_review`. Needs `0029`. Locks only the event row (`FOR UPDATE`); writers reach the event last through FK inserts, so they serialise without deadlock. Verify with `verify_safety_review_readiness.sql`; two-connection checks in `tests/test_safety_review_concurrency.py` on a disposable cluster built by `tests/bootstrap_safety_review.py`. **Not yet applied to shared development** (disposable local cluster only, 16 October 2026) |
| `migrations/0040_arrangement_review_safety_recheck_lock_compatibility.sql` | Replaces only the private safety-target helper: whole-batch membership snapshot with no child row locks, preserving errors, replay, private privileges and atomic reviews/outbox. Trusted caller owns the event lock. **Prepared, not applied to shared Supabase**. |
| `migrations/0041_booking_request_cancelled_status.sql` | SCRUM-61: adds the `cancelled` value to `booking_request_status`. Its own file because Postgres cannot use a new enum value in the transaction that adds it. **Not yet applied to shared development** |
| `migrations/0042_cancel_venue_booking_request.sql` | SCRUM-61: `cancelled_by` and `cancelled_at` on `venue_booking_requests`, the decision-consistency constraint extended for `cancelled`, a new `cancelled_consistent` constraint, and the server-only `cancel_venue_booking_request` function (ERRCODE `P0002` not found, `55000` not pending or approved, `22023` no user). Run after 0041. **Not yet applied to shared development** |
| `migrations/0043_venue_setup_turnaround.sql` | SCRUM-59: `venues.setup_minutes` and `venues.turnaround_minutes`, `integer NOT NULL DEFAULT 0`, each checked to be a multiple of 15 from 0 to 1020 (`venues_setup_minutes_valid`, `venues_turnaround_minutes_valid`). Existing venues read 0 / 0. Safe to re-run. Access unchanged (0016). Verify with `verify_venue_setup_turnaround.sql`. **Not yet applied to shared development** |
| `migrations/0044_safety_review_null_inputs.sql` | SCRUM-60: replaces `decide_safety_review` from `0034` (not edited, as it is applied) with NULL-safe input checks: a NULL decision, NULL targets or a target without `arrangement` now gets `22023` before any write. In `0034` a target without `arrangement` was saved, because `NULL NOT IN (...)` is NULL. Grants restated. Verify with `verify_safety_review_decisions.sql` (AC6-X5). **Applied to shared development via MCP on 18 October 2026, version `20261018045424`**: the verify script failed at AC6-X5 before it (`23502`) and passed fully after it |
| `migrations/0045_safety_review_arrangement_reviews.sql` | SCRUM-60 increment 2b: replaces `decide_safety_review` from `0044`. Requires SCRUM-64's `0030`–`0040`. `changes_requested` calls `private.raise_safety_arrangement_reviews` with the saved `safety_reviews.id`, targets and reason in the same transaction (a target outside the event is `22023`; any flag or enqueue failure aborts the decision); `approved` is refused with `P0005` and a JSON list of `arrangement_needs_review` items while `get_outstanding_arrangement_reviews` returns any row. Event row `FOR UPDATE` first; child rows only read. SCRUM-58's ordinary readiness check is not included yet. Verify with `verify_safety_review_arrangement_reviews.sql`. **Not yet applied anywhere shared** |
| `migrations/0046_shared_event_readiness.sql` | SCRUM-58 AC3b: `private.event_readiness_issues(p_event_request_id uuid) RETURNS jsonb`, the handover's ordinary readiness moved out of `0039` unchanged so SCRUM-60's approval can share it (approved booking and none pending, rejected/cancelled ignored; every requirement fully reserved). `[]` when ready; items `no_venue_booking`, `venue_booking_pending`, `equipment_not_reserved`. STABLE, SECURITY DEFINER, no row locks, EXECUTE for `service_role` only. Replaces `send_event_request_for_safety_review` to also refuse (`P0005`) on every outstanding SCRUM-64 review, cancelled bookings included, as `arrangement_needs_review` items after the readiness items. Needs `0035` and `0039`. Verify with `verify_shared_event_readiness.sql`; disposable schema from `tests/bootstrap_safety_review.py`. **Not yet applied to shared development** |

Verify `0020` after applying it: run
[`verify_equipment_reservations.sql`](verify_equipment_reservations.sql) in the
SQL Editor — it exercises the CHECK constraints and both foreign keys
(including the refusal paths) and prints
`ALL EQUIPMENT RESERVATION VERIFICATIONS PASSED` on success, rolling back so
no data is left behind. From SCRUM-13's `0027` on, the script also needs `0027`
applied: every reservation it inserts names a requirement.

`0027` was applied to shared development on 14 October 2026 through the SQL
Editor (the reservations table was confirmed empty first). Do not apply it
again there; retain the file for fresh environments — it must be applied
before the SCRUM-13 endpoints work, since `POST /equipment-reservations`
returns `500` until `reserve_equipment` exists. Its behavioural checks are
in [`verify_equipment_reservation_writes.sql`](verify_equipment_reservation_writes.sql),
run after `0027` and `0028`; the AC3-N2 two-session race needs two SQL
sessions as that script's footer describes and, because it commits fixture
rows, runs on a disposable migrated database rather than shared development.

`0028` (SCRUM-13 D12) must be applied after `0027`. It was applied to shared
development on 15 October 2026 through the SQL Editor; do not apply it again
there, and retain the file for fresh environments. Before it is applied,
`verify_equipment_reservation_writes.sql` stops at the AC1-N10 line, which is
the expected Red. After applying it, run both verify scripts and confirm the
grants with
`SELECT grantee, privilege_type FROM information_schema.routine_privileges WHERE routine_name = 'reserve_equipment';`
(`service_role` and the owner only).

`0011` was applied to the shared Supabase development project via MCP on 22
September 2026. Do not apply it again there; retain the file for fresh
environments and schema review.

`0012` was applied to the shared Supabase development project on 23 September
2026 (the corrected version, with the fixed P0004 `RAISE`). Do not apply it
again there. Fresh environments must apply it before running the SCRUM-28
eventRequestService, otherwise `/review`, `/cancellation` and `/completion`
return 502.

`0013` was applied to the shared development project on 23 September 2026,
after which `verify_event_request_status_transitions.sql` passed there. Do not
apply either file again there.

`0014` was applied to the shared development project on 24 September 2026 and
`verify_atomic_coordinator_assignment.sql` completed there without error. Do
not apply it again there; retain it for fresh environments.

`0015` was applied to shared development on 24 September 2026. The full status
transition verification passed afterward, and the Supabase security advisor no
longer reports `advance_event_request_by_coordinator` as having a mutable search
path.

`0017` was applied to shared development via the Supabase MCP on 29 September
2026. Do not apply it again there (it is safe to re-run, but there is no need).
Read-only checks afterwards confirmed RLS on, all five constraints and both
indexes present, no `anon`/`authenticated` access, and `service_role` insert and
update. `verify_notifications.sql` was run against a local Postgres, not shared
development, because it writes rows (they are rolled back).

`0018` was applied to shared development on 4 October 2026 through the SQL Editor,
and `verify_venue_booking_requests.sql` then ran there without error (it rolls
back every row it writes). Read-only Data API checks afterwards found the table
readable by the service role and refused to the browser role. Do not apply it
again there (it is safe to re-run, but there is no need).

The SCRUM-35 `0018_event_change_requests.sql` and `0019` migrations were applied
to shared development on 4 October 2026. Migrations `0020` through `0022` were
applied on 5 October 2026 after the rollback verification found that PostgreSQL
transaction timestamps could leave the optimistic-concurrency marker unchanged.
`verify_event_change_requests.sql` then completed without error and retained no
fixture rows.

New RPCs should revoke `EXECUTE` from `PUBLIC, anon, authenticated` in the same
migration that creates them. Supabase grants all three by default.

`0001_baseline.sql` was derived from what `equipmentService` implies, then reconciled against the live database (columns, types, nullability, defaults, constraints, indexes) using the export queries below. One thing is deliberately absent:

- **No `operational_status` enum type** — the live DB stores status as `varchar` with CHECK constraints; the API mirrors the allowed values in `app/models.py`.

Note: `transition_equipment_status` did **not** exist in the live database (verified 2026-09-19) even though `PATCH /equipment/{id}/status` calls it — `0002` creates it from the router's RPC contract.

## Verifying the SQL functions

The service's pytest suite fakes the database, so the functions' real behaviour (atomicity, `P0002` contract, audit logging, the quantity CHECK) is verified by [verify_equipment_functions.sql](verify_equipment_functions.sql). Run it in the SQL Editor after applying the migrations: it exercises every function including failure paths, prints `ALL EQUIPMENT FUNCTION VERIFICATIONS PASSED` on success, and `ROLLBACK`s — leaving no data behind. RLS behaviour is verified separately with the publishable key over the REST API (see `docs/`).

The event-request submission outbox is verified by
[`verify_event_request_submission_outbox.sql`](verify_event_request_submission_outbox.sql).
It proves that a Draft creates no event, each supported submission path creates
exactly one event, and a repeated status write does not create a duplicate. The
script rolls back all test rows.

The notifications table is verified by
[`verify_notifications.sql`](verify_notifications.sql). Run it after `0017`:
it proves a retried event is stored once, one event can notify several
recipients, a non-object payload is refused and browser roles cannot read the
table. The script rolls back all test rows.

The booking-request table is verified by
[`verify_venue_booking_requests.sql`](verify_venue_booking_requests.sql).
Run it once before `0018`, when it should stop with a missing-table error (the
Red result), and again after (and after `0041` and `0042`, which add the
`AC4-D1` to `AC4-D8` cases for SCRUM-61), when it should print
`ALL VENUE BOOKING REQUEST VERIFICATIONS PASSED`. It covers dates, slots,
required columns, status and decision consistency, the venue foreign key and
server-only access. The script rolls back all rows and needs no Supabase Auth
user.

The venue setup and turnaround columns are verified by
[`verify_venue_setup_turnaround.sql`](verify_venue_setup_turnaround.sql).
Run it once before `0043`, when it should stop at the missing column (the Red
result), and again after, when it should print
`SCRUM-59 verify: all venue setup and turnaround cases passed`. It covers the
0 / 0 default, both limits and the refused values 20, -15 and 1035. The script
rolls back all rows.

The coordinator transition function is verified by
[`verify_event_request_status_transitions.sql`](verify_event_request_status_transitions.sql).
Run it after `0012` and `0013`: it exercises Submitted → Under Review, non-terminal →
Cancelled and Confirmed → Completed, every `P0002`/`P0003`/`P0004` failure
path (including reassignment away and repeated actions), confirms refused calls
leave the status unchanged, and checks the `EXECUTE` grants. It prints
`ALL EVENT-REQUEST STATUS TRANSITION VERIFICATIONS PASSED` and rolls back.
Requires at least one Supabase Auth user (used as the organiser).

The equipment-requirements table and its transition function are verified by
[`verify_equipment_requirements.sql`](verify_equipment_requirements.sql).
Run it once before `0021`, when it should stop with a missing-table error (the
Red result), and again after, when it should print
`SCRUM-33 verify: all equipment_requirements cases passed`. It covers the
defaults, every CHECK and foreign key (including the refusal paths), the
allowed transitions and their audit fields, the row lock, the lookup indexes
and server-only access. It rolls back all rows and needs at least one Supabase
Auth user (run `seed_test_accounts.sql` first).

Atomic assignment is verified by
[`verify_atomic_coordinator_assignment.sql`](verify_atomic_coordinator_assignment.sql).
After `0014`, it exercises missing, Draft, terminal and wrong-role failures,
successful assignment and reassignment history, the shared row-lock contract
and server-only execution grants. It rolls back all verification data.

SCRUM-17 review decisions are verified by
[`verify_event_request_review_decisions.sql`](verify_event_request_review_decisions.sql).
After `0016`, it exercises every review outcome, reason and response retention, refused
side effects and server-only permissions. It rolls back all verification data.

SCRUM-35 event amendments are verified by
[`verify_event_change_requests.sql`](verify_event_change_requests.sql). After
`0018_event_change_requests.sql` through `0022`, it checks unchanged and duplicate
requests, atomic approval, rejection without event mutation, stale approval,
reassignment and server-only table/function access. It requires one Supabase
Auth user and rolls back all verification data.

## Arrangement review read contract (SCRUM-64, in progress)

Number allocation update, 16 October: Jaren reserved **0034** for his SCRUM-60
safety decision migration in Telegram discussion #2111 (04:13:21 UTC). Our
unapplied shared-read migration is now **0035**, with identical SQL and SHA256
`586a1b54aa92ae2145145f3448a8301696e3780dbcce7587453e45aee954d0a4`.
PR62's 0034 and 0044 are now present through the merge of `dev`; both remain
owned by SCRUM-60 and retain their recorded shared application history. They must
not be replaced or renumbered as SCRUM-64 files. The independent 30-file fixture
below deliberately omits them. The separate 37-file compatibility fixture uses
the exact reviewed archive versions, including later work not merged here,
without changing local migration ownership or claiming shared deployment.
Historical execution records retain their old numbers.

### Safety decision integration boundary

Jaren's published `decide_safety_review(event UUID, officer UUID, decision text,
reason text, targets jsonb)` at PR62 commit
`e7888dcfdb19777722583b471b1d31e49da3f9c4` owns the saved `safety_reviews`
decision and lifecycle mutation through external 0034 and its 0044/0045/0047
replacements. Targets are objects with `arrangement` (`venue_booking` or
`equipment_reservation`) and `id` (the booking/reservation UUID). The published
caller maps a saved changes-requested decision ID to existing
`trigger_type='safety_recheck'`, `trigger_id=<safety_reviews.id>` and the saved
reason, without duplicate `source`/`source_id` columns. Explicit targets
must belong to the same event. Empty targets mean zero arrangement flags; they
do not discard the decision or its reason. Approval creates no safety-recheck
flags. The SCRUM-64 helper contract remains separate from the saved decision
and lifecycle responsibilities of SCRUM-60.

Migration 0036 provides only the private transaction-internal writer
`private.raise_safety_arrangement_reviews(event UUID, decision UUID, targets JSONB,
reason TEXT) -> integer`. It returns the actual number of inserted rows. Event
and decision UUIDs, an array of targets and a nonblank reason are always required,
even for `[]`; a valid empty array returns zero. Each target requires a supported
`arrangement` and UUID `id`; additional metadata is ignored. Duplicate domain/UUID
pairs are collapsed. Malformed required inputs fail with `22023`; missing events,
missing targets and targets belonging to another event fail privately with
`P0002`. All target shapes and memberships are validated before any flag insert.

Explicit targets have no implicit date, approval-state or event-status filter.
Migration 0040 replaces 0036's `FOR SHARE` child locks with one ordinary statement
that validates the whole distinct target set at one snapshot before any insert.
The helper takes no booking, reservation, requirement or equipment row lock. It
then inserts `safety_recheck` rows with the supplied decision UUID and complete reason,
empty changed fields and no clear audit. Exact per-target replay does nothing:
it neither rewrites evidence nor reopens cleared work. A distinct decision can
raise new work for the same arrangement. Insert failure rolls back all new rows.
The helper changes no event/resource status, history or decision and makes no
remote notification call. New reviews also enqueue durable work through 0037.

The trusted caller must lock its event `FOR UPDATE` before invoking the helper
and retain it through the saved-decision/review transaction. A child-first writer
can need an event FK lock; waiting on its child while holding the event introduces
a reverse edge. Removing that wait follows Tate's published event-only protocol
at `bf31002c4928c6d953be89bb7f34e3f257fd883e`, without copying his 0039 gate or
implementing Jaren's saved-decision caller. Published allocation was checked on
17 October: 0034 remains Jaren's reservation, 0039 is Tate's published migration
and 0040 is our next compatibility migration. The original 0036 SQL is unchanged.

Membership is validated at a snapshot, not protected by a child-row lease.
Current supported booking/reservation APIs do not expose reparent/delete actions,
but database UPDATE grants do not make those identities immutable, and venue
bookings still have no event FK. Future membership-changing or deleting writers
must join the event protocol; arbitrary privileged changes are not serialised by
this helper. No cross-story immutability trigger, deletion guard or FK is added.

This function is `SECURITY INVOKER`, in `private`, with an empty search path and
EXECUTE revoked from PUBLIC, anon, authenticated and service_role. A trusted
decision function must call it in a privileged owner/definer transaction;
an ordinary service-role invoker wrapper cannot bypass that boundary. No direct
HTTP endpoint or app-role review-write grant is added. The caller must verify
the Safety Officer's authority, the actual saved decision and its event, and bind
the immutable complete target/reason payload to that decision. There is no saved
decision foreign key or separate replay ledger here: a caller passing additional
targets on a repeated UUID is not detected by the per-target conflict key.

**Published integration boundary:** the optional pinned fixture below uses PR62
commit `e7888dcfdb19777722583b471b1d31e49da3f9c4`, containing the decision
foundation, NULL validation and 0045–0047 connections. Its saved changes-requested
decision calls this private writer with the actual saved UUID in the same
transaction; invalid or cross-event targets are mapped to caller error `22023`.
The helper's own private missing-target contract remains `P0002`. The published
0047 caller refuses duplicate domain/UUID target pairs with `22023` before writes
(UUID text case does not distinguish targets); the private helper still deduplicates
its trusted input. These are separate caller/helper contracts. Approval and
handover both check normal readiness followed by outstanding review evidence,
including retained flags on cancelled bookings. Those caller/lifecycle/gate
functions remain SCRUM-60/SCRUM-58 ownership. The merged base contains 0034/0044
and the initial API/UI; later 0039 and 0045–0047 remain archive-only here.
A new equipment requirement can commit after handover without a review flag, so
normal readiness must also be checked at approval; flags alone are insufficient.
The current published 0047 approval performs that check. Native evidence does not
establish a shared deployment or replace the future membership-writer protocol.

### Current shared read


`0029_safety_review_status.sql` is the explicit upstream prerequisite, copied
byte-for-byte from PR62 commit `889764620ba943e1a53d4a1f4a16585c739c2ab4`.
SHA256: `bd3b35f8eeee1e931c9386b641ea9d44a749e65bdbf4eaff4d120ef91d13fb33`.
It represents the already applied shared Safety Review status/role/cancellation
schema; this adoption does not merge PR62 or implement its safety decisions,
authentication changes or seed accounts. Apply it only to a fresh local target
where it is absent; do not alter or reapply the shared migration. The backend
status model, coordinator in-flight grouping and frontend status/tracker support
match that same upstream commit so existing Safety Review rows can be read.
Our four unapplied feature migrations were renumbered 0030–0033 with their
contents unchanged; earlier evidence retains its original migration names.

`0030_arrangement_review_reads.sql` creates `public.arrangement_reviews` for the
coordinator-only `GET /event-requests/{id}/arrangement-reviews` API. Its adapter
calls `POST /rpc/get_outstanding_arrangement_reviews` with only
`{"p_event_request_id": "<event UUID>"}`. Migration 0035 centralises the event
predicate, `cleared_at IS NULL` and absolute timestamp/UUID descending order in
that full-row helper; the service retains defensive validation/order. Review state is separate
from event, booking and reservation status. A composite per-target trigger key
retains distinct affected arrangements while rejecting duplicate review identity;
clearing actor/time must be present together. Generic arrangement UUIDs are not
foreign keys to the still-independent booking/reservation workflows.

The prepared migrations 0030–0033, 0035–0038 and 0040 are **not applied to shared Supabase**.
RLS is enabled, all browser grants are revoked and the server role retains SELECT
only.

Migration 0035 exposes the shared read only to `service_role`, as SQL/STABLE
`SECURITY INVOKER` with an empty search path; it uses the existing table SELECT
grant and adds no write access. Its exact signature is
`public.get_outstanding_arrangement_reviews(p_event_request_id uuid) RETURNS SETOF public.arrangement_reviews`.
Rows retain `id`, `event_request_id`, `arrangement`, `arrangement_id`, `trigger_id`,
`trigger_type`, `changed_fields`, `reason`, `raised_at`, `cleared_at` and
`cleared_by`; only outstanding rows are returned. The service role has function
EXECUTE and the underlying table SELECT, while PUBLIC/anon/authenticated have no
function EXECUTE. Server callers may query these facts within their own transaction. It returns full review identities and reasons, not a
readiness verdict, and takes no explicit event/resource row locks. This does not
solve future gates' snapshot/lock protocol or widen either protected HTTP
endpoint. Staff domain queues retain their existing domain-scoped table reads.
A missing/unavailable helper produces safe 502 `Arrangement reviews unavailable`;
there is no raw-table fallback or false empty success.

The SQL helper has no LIMIT, but HTTP function results remain subject to the
deployment's PostgREST `db-max-rows` setting. Supabase documents a default maximum
of 1,000 rows; this increment does not verify the target cap or implement paging.
Do not infer unbounded HTTP completeness from direct SQL checks. See
[Supabase row limits](https://supabase.com/docs/reference/python/select) and
[PostgREST db-max-rows](https://docs.postgrest.org/en/stable/references/configuration.html#db-max-rows).

Migration 0031 attaches a private `SECURITY DEFINER` audit trigger with an
empty search path and no direct EXECUTE permission, including for `service_role`.
It runs only after an event UPDATE already authorised by the existing database
and API boundary, so callers cannot forge review rows through a table INSERT.

The trigger derives changed fields and useful before/after reasons from OLD/NEW:
`proposed_date_times` and `expected_attendance` affect both domains,
`venue_requirements` affects venues and `equipment_requirements` affects
reservations. Timestamp arrays compare actual instants without reordering;
optional text compares after outer trimming, treating blank as absent. Unrelated
or equivalent edits and events whose resulting status is Draft, Completed,
Cancelled or Rejected create no work. Approved venue bookings with
`end_date >= today` and reservations with `return_date >= today` are included for
the same event, using the Singapore transaction date, including the final day.
Each affected target gets its own row under one generated direct-update UUID;
this UUID is not represented as a change-request identity. Earlier reviews remain
unchanged, and any failed review insert rolls back the event update and all its
new reviews.

The event UPDATE already locks the event row. This trigger reads arrangements
without acquiring requirement or equipment row locks. Concurrent arrangement
creation and future equipment-status/readiness writers still need their own
consistent locking design. The trigger observes arrangements visible to its
statements; it does not serialise concurrent reservation/booking creation with
event changes. The saved safety caller and shared readiness consumers are not
implemented here. No SCRUM-35 acceptance route is enabled.

Migration 0032 adds `public.clear_arrangement_review(uuid, uuid, text[])` as a
narrow `SECURITY DEFINER` RPC with an empty search path and EXECUTE granted only
to `service_role`. The backend supplies the actor and allowed domains solely from
verified auth-service roles, including that service's authoritative fallback
rules; browser input never supplies these values. The RPC locks only the named
review row and rejects absent (`P0002`), wrong-domain/invalid actor (`P0003`) or
already-cleared (`P0004`) work before writing its audit pair. Every other field
and other review row remains unchanged. Direct INSERT/UPDATE/DELETE review
grants remain revoked, so callers cannot bypass the RPC's checks. A clear does
not acquire event, requirement or equipment locks and does not complete later
review flags for the same arrangement.

Migration 0033 adds a unique `review_trigger_id` UUID to each equipment status
history row and a private, non-callable audit trigger after new history inserts.
Existing history receives stable identifiers under the normal append workflow;
no write-protection or historical review reconstruction is claimed. The trigger
is attached after adding the column, so retained history is not replayed. The
existing `transition_equipment_status` RPC records status, history and reviews in
one transaction: any review failure rolls back them all. API response fields are
unchanged. Creation history, equal-status writes and restoration to AVAILABLE
neither create nor clear reviews. Actual transitions to DAMAGED, UNDER_REPAIR,
UNDER_MAINTENANCE or RETIRED flag reservations for the exact catalogue equipment
UUID, through their inclusive Singapore return date, excluding Draft/terminal
events. The shared cause UUID, old/new status and recorded reason remain
attributable to that history row; no reservation or lifecycle state is rewritten.

Although no explicit event lock is added, review inserts acquire an implicit
foreign-key KEY SHARE lock on the event. The existing reservation RPC likewise
inserts an event foreign key after locking requirement then equipment. A future
readiness gate that locks event then equipment can introduce a reverse edge or
miss concurrent flags; this increment does not resolve that shared lock protocol.
It observes existing arrangements visible to its statements and does not claim
safety against concurrent arrangement creation or future SCRUM-58 gates.

For this increment, apply the migration to a disposable database with the event
schema, standard roles and an existing disposable auth identity, then run
[`verify_arrangement_review_reads.sql`](verify_arrangement_review_reads.sql) using
`psql -X -v ON_ERROR_STOP=1 -f database/verify_arrangement_review_reads.sql` with
that database's connection. The script checks stored identity/constraints,
outstanding order, RLS/grants and actual browser/server-role reads; its fixtures
are rolled back. After applying 0031 locally, also run
`psql -X -v ON_ERROR_STOP=1 -f database/verify_arrangement_review_flags.sql`.
That rolled-back script exercises real event updates, domain/date eligibility,
semantic no-ops, private writer access and atomic rollback on an inserted failure.
After applying 0032, run
`psql -X -v ON_ERROR_STOP=1 -f database/verify_arrangement_review_clears.sql` for
stored clear permissions, exact-target/stale behaviour and audit invariants.
After applying 0033, run
`psql -X -v ON_ERROR_STOP=1 -f database/verify_arrangement_review_unavailability.sql`
for real status-RPC targeting, history attribution, status partitions and atomic
rollback on an injected flag failure. The script supplies missing vanilla-PG
service-role fixture grants transactionally and rolls them back.
`verify_arrangement_review_safety_compatibility.sql` checks actual Safety Review
storage eligibility after the exact upstream prerequisite. After applying 0035,
run `psql -X -v ON_ERROR_STOP=1 -f database/verify_arrangement_review_shared_reads.sql`
for service/browser access, full ordered evidence and the same helper's remaining
facts after legitimate clears (3→2→1→0), with unchanged read snapshots.
After applying 0036 and its 0040 replacement, run
`psql -X -v ON_ERROR_STOP=1 -f database/verify_arrangement_review_safety_rechecks.sql`
for explicit targeting, whole-batch refusal, replay/clear preservation, injected
failure rollback and denied direct app/browser calls. This owner-run check does
not supply or verify the saved-decision caller or actual Safety Officer
HTTP authorisation.
The sequential clear script proves stale T1/T2 behaviour, not simultaneous
session lock waiting. These checks do not prove remote HTTP delivery or
SCRUM-58 readiness integration.

### Durable arrangement-review notifications

Migration 0037 records exactly one outbox snapshot for each newly inserted review
of any supported cause, atomically with its source transaction. Payload fields are
the raised review row with `id` named `review_id`; later clears do not rewrite
that evidence. Enqueue failure rolls back the source change, reviews and work.
There is no historical backfill and no HTTP delivery inside a database trigger.

Migration 0038 adds `accepted_recipients` (recipient UUID to first accepted time)
and `last_attempted_at`. Its three empty-search-path `SECURITY DEFINER` RPCs are
callable only by `service_role`: `begin_arrangement_review_notification_attempt`,
`record_arrangement_review_notification_accepted` and
`complete_arrangement_review_notification`. Direct outbox UPDATE remains revoked.
The internal role resolver is private/non-callable and aggregates existing Auth
accounts using authoritative nonempty `staff_roles`, otherwise the auth service's
trusted metadata fallback. Latest assignment uses ID descending and compares its
legacy text identity to UUID text; an absent/invalid/revoked coordinator leaves
that group unresolved. Venue/equipment staff are current role-wide groups, not
prior editors. No new Auth schema, user or role is introduced.

An attempt locks its work row and stamps the action clock before looking up
recipients. A directory failure returns `recipients_available=false` while keeping
the stamp, allowing fair rotation through never/least-recently attempted jobs.
Acceptance is an atomic append-once JSON union, preserving first timestamps under
concurrent updates. The trusted relay records it only after HTTP 202. Completion
re-resolves both current groups and publishes only when both exist and their
current union is accepted. Already accepted recipients remain recorded through
reassignment. This is durable at-least-once delivery, not exactly-once HTTP or a
cross-service role/assignment lock. The native resolver adds `change_request_id`
only for a matching same-event Approved `event_change_requests` cause.

The Python relay sends `arrangement_needs_review` using
`uuid5(NAMESPACE_URL, "needs-review:{trigger_id}:{arrangement_id}")`. Downstream
`UNIQUE(recipient_id,event_id)` prevents duplicate inbox rows. See the event
service README for startup, disabled-delivery behaviour and retry/shutdown details.

After 0037/0038, run the rolled-back checks
`verify_arrangement_review_notification_enqueue.sql` and
`verify_arrangement_review_notification_delivery.sql`. The first proves atomic
pending work, replay and enqueue failure rollback; the second proves real SQL
recipient precedence, acceptance preservation, fair attempt stamps and server-only
boundaries, including a disposable directory outage. They do not perform HTTP or
real-user authentication. `verify_notifications.sql` separately checks the
receiver's stored unique identity.

After merged 0041 has committed and 0042/0043 are installed, run the separate
`psql -X -v ON_ERROR_STOP=1 -f database/verify_arrangement_review_cancelled_venues.sql`
check. It calls the actual cancellation RPC, verifies that later significant
changes exclude the cancelled booking but still flag an approved sibling and
eligible equipment, and preserves the earlier review/job and lifecycle/resource
snapshots. Cancellation is not a review acknowledgement: existing outstanding
reviews remain visible in the shared reader until authorised staff clear the
named review. Consumers must not hide that work based on current booking status.
The check rolls back; it extends the nine existing review SQL checks to ten without changing their
historical results or proving HTTP authentication.

**Rollout boundary:** apply the still-unapplied feature files 0030–0033 and
0035–0038 plus 0040 in **one reviewed database transaction**, or hold all affected writes
until the entire stack is installed. Otherwise a flag writer could create reviews
before its enqueue trigger exists. Do not add a backfill to hide that gap. For an
approved target where prerequisite 0029 already exists, leave it unchanged; 0034
belongs to the independent safety-decision owner. These files contain no COMMIT.
A transaction can be supplied with `psql -X -v ON_ERROR_STOP=1 --single-transaction`
and repeated `-f database/migrations/<feature-file>` arguments. This is rollout
guidance, not authorisation or evidence of shared deployment.

### Disposable SCRUM-64 SQL setup

From the repository root, use an owned, empty PostgreSQL 16 cluster with `psql`
and Python 3 available. Set `SCRUM64_TEST_DSN` to its loopback connection URL
with a database name starting `scrum48_`. The existing bootstrap refuses shared,
non-loopback, nonempty or reused targets. It creates local Auth test doubles and
one disposable identity, not real Supabase authentication. The extra Auth metadata
column below extends only that disposable test double; genuine Supabase already
has it. Do not use this setup
against shared Supabase or a database with existing roles/data.

```sh
python3 database/tests/bootstrap_event_status_history.py \
  --dsn "$SCRUM64_TEST_DSN" --disposable || exit 1

# Local Auth test-double column only; never run this ALTER on Supabase Auth.
psql -X -v ON_ERROR_STOP=1 -d "$SCRUM64_TEST_DSN" \
  -c "ALTER TABLE auth.users ADD COLUMN raw_app_meta_data jsonb NOT NULL DEFAULT '{}'::jsonb" || exit 1

for migration in \
  0001_baseline.sql \
  0002_transition_equipment_status.sql \
  0003_create_equipment_fn.sql \
  0004_quantity_history.sql \
  0005_rls_and_function_access.sql \
  0006_rpc_execute_grants.sql \
  0016_venues.sql \
  0017_notifications.sql \
  0018_venue_booking_requests.sql \
  0018_event_change_requests.sql \
  0019_event_change_requests_organiser_index.sql \
  0020_event_change_request_updated_at.sql \
  0021_event_change_request_monotonic_updated_at.sql \
  0020_equipment_reservations.sql \
  0021_equipment_requirements.sql \
  0027_equipment_reservation_requirements.sql \
  0028_reserve_equipment_type_check.sql \
  0029_safety_review_status.sql \
  0030_arrangement_review_reads.sql \
  0031_arrangement_review_event_changes.sql \
  0032_arrangement_review_clear.sql \
  0033_arrangement_review_equipment_unavailability.sql \
  0035_arrangement_review_shared_reads.sql \
  0036_arrangement_review_safety_rechecks.sql \
  0037_arrangement_review_notification_outbox.sql \
  0038_arrangement_review_notification_delivery.sql \
  0040_arrangement_review_safety_recheck_lock_compatibility.sql \
  0041_booking_request_cancelled_status.sql \
  0042_cancel_venue_booking_request.sql \
  0043_venue_setup_turnaround.sql
do
  psql -X -v ON_ERROR_STOP=1 -d "$SCRUM64_TEST_DSN" \
    -f "database/migrations/$migration" || exit 1
done

for check in reads flags clears unavailability safety_compatibility shared_reads safety_rechecks notification_enqueue notification_delivery
do
  psql -X -v ON_ERROR_STOP=1 -d "$SCRUM64_TEST_DSN" \
    -f "database/verify_arrangement_review_$check.sql" || exit 1
done

# Additional post-merge cancellation compatibility check; fixtures roll back.
psql -X -v ON_ERROR_STOP=1 -d "$SCRUM64_TEST_DSN" \
  -f database/verify_arrangement_review_cancelled_venues.sql || exit 1

# Commits labelled fixtures: owned disposable cluster only, discard afterwards.
python3 database/tests/test_arrangement_review_lock_compatibility.py \
  --dsn "$SCRUM64_TEST_DSN" --disposable || exit 1
```

The loop applies 30 supplemental files after the guarded bootstrap, including the
genuine change-request schema/timestamp prerequisites needed for cause lookup and
the merged booking-cancellation/setup migrations 0041–0043. Each file uses its
own `psql` invocation: 0041 must commit its new enum value before 0042 uses it.
Do not combine those two migrations in one transaction. This is separate from
the atomic SCRUM-64 feature rollout described above.
This is the bounded SCRUM-64 verification fixture, not a complete deployment of
all project migrations. Each verification script rolls back its own fixtures.
The database schema, bootstrap identity and concurrency fixtures remain until
the owned cluster is removed. The nine existing SQL checks and the separate cancellation check roll back their own fixtures;
the Python concurrency harness above commits labelled fixtures and must never
run on shared Supabase. Use `--psql /path/to/psql-wrapper` if needed.

The three native concurrency cases exercise both held-child domains, an earlier
flag transaction followed by an event-locked shared reader, and the reverse order
with the actual equipment-status RPC and review/outbox writer. The child-first
review INSERT is an explicit protocol fixture, not a claimed current normal HTTP
deadlock. These schedules verify no incompatible helper child wait, correct
committed evidence and preserved resources/lifecycle. They do not test Tate's
readiness verdict, Jaren's actual caller, arbitrary reparent/delete operations or
all concurrent arrangement-creation races. The unchanged sequential clears script
still does not prove simultaneous clears.

### Pinned external safety-workflow compatibility fixture

Use a **different owned empty PostgreSQL 16 cluster** from the independent
30-file SCRUM-64 fixture above. Run these commands from the repository root.
The combined fixture loads **37 supplemental migrations**, including local 0026
Planning support and all six external files below. Every test scope uses this
same complete schema: 0046 depends on 0039 and 0047 depends on 0046. Selecting
`decision` does not remove Tate's dependency from the current stack.

Set `SCRUM64_TEST_DSN` to an owned disposable loopback database named
`scrum48_*`. Set `SCRUM64_EXTERNAL_SQL_DIR` to the **database directory of an
extracted, reviewed offline source archive** at commit
`e7888dcfdb19777722583b471b1d31e49da3f9c4`: it must contain `migrations/`
and the four verifier files. This is one published combined source snapshot,
including Tate's handover/readiness work; it is not an implicit branch merge.
Keep its commit, source paths and SHA256 values in the archive manifest. Local
0034/0044 now come from merged PR62, but this reproducibility recipe deliberately
uses the pinned archive for all six listed files. Do not overwrite those applied
base files, copy later external migrations into this checkout or fetch new source
as a hidden setup step. Once the archive is supplied, setup needs no
external network. A future head requires reviewed hashes and fresh evidence.

All entries in this table are from that same pinned commit:

| External source relative to the archive's database directory | SHA256 |
| --- | --- |
| `migrations/0034_safety_review_decisions.sql` | `4099f1f7a0c60df682d076c0080e7911da05008495313126de0c9e3f79e817aa` |
| `migrations/0039_send_for_safety_review.sql` | `15c9bcc42cce8c8a948428f9be70ad0ab122501ea72b66dbcc0215ceb7b909a5` |
| `migrations/0044_safety_review_null_inputs.sql` | `aa2cb9b05e978358b4b634a715ca95fd27284dcf9f7c821132af3993c6301792` |
| `migrations/0045_safety_review_arrangement_reviews.sql` | `333774e7c9e7fe5831bdf44d308230d15b39e1ff80b2bff4ba4cf536df7b3ff4` |
| `migrations/0046_shared_event_readiness.sql` | `a6c0f19a3900ae4576a9d6edb5fa11cc3c437f5de086b1e628dd9492e3dc2a3c` |
| `migrations/0047_safety_review_approval_readiness.sql` | `647d8e67e13b7307144438473bc298167f49c67b40c0d8c20b82dde435ff0507` |
| `verify_safety_review_decisions.sql` | `401938449777cc45827062cf14f08434cbd0eddd82c80b40caee814b3d6f1070` |
| `verify_safety_review_arrangement_reviews.sql` | `8c7602f5366229bbc0ae38c02a5f818cc32484a4c82d58ace1bbea8e91e5000c` |
| `verify_shared_event_readiness.sql` | `55803187c95990062be3bda03bb45aaa665d05c61bd0293908984bcf85f6059d` |
| `verify_safety_review_approval_readiness.sql` | `44455ab8f6848f6abbc9c3877225568614a446c3c1a0234a7cff8eb00a63aadc` |

0034 requires the event schema, `staff_roles`, exact 0029 safety status/role
foundation and 0025 actor/history support. The guarded SCRUM-48 bootstrap supplies
the older event/history migrations. Persisted `staff_roles` is the Safety Officer
role source for the decision RPC; metadata alone does not satisfy it. The two
Auth rows and metadata column below extend only the disposable Auth test double,
not shared Auth or real accounts.

The load order retains 0036 followed by its 0040 lock-compatible replacement.
0045 connects actual saved decisions to the private review writer and outstanding
reader; 0046 adds shared normal readiness and the handover review gate; 0047 uses
both normal readiness and outstanding reviews before approval. 0046's narrowly
privileged readiness function removes the older fixture's need for a separate
venue SELECT grant. **Do not apply the historical local ACL workaround here.**

```sh
: "${SCRUM64_TEST_DSN:?Supply the owned disposable loopback scrum48_* database URL}"
: "${SCRUM64_EXTERNAL_SQL_DIR:?Supply the pinned archive database directory}"
python3 - "$SCRUM64_EXTERNAL_SQL_DIR" <<'PY_CHECK' || exit 1
from pathlib import Path
import hashlib
import sys
archive = Path(sys.argv[1])
expected = {
    "migrations/0034_safety_review_decisions.sql": "4099f1f7a0c60df682d076c0080e7911da05008495313126de0c9e3f79e817aa",
    "migrations/0039_send_for_safety_review.sql": "15c9bcc42cce8c8a948428f9be70ad0ab122501ea72b66dbcc0215ceb7b909a5",
    "migrations/0044_safety_review_null_inputs.sql": "aa2cb9b05e978358b4b634a715ca95fd27284dcf9f7c821132af3993c6301792",
    "migrations/0045_safety_review_arrangement_reviews.sql": "333774e7c9e7fe5831bdf44d308230d15b39e1ff80b2bff4ba4cf536df7b3ff4",
    "migrations/0046_shared_event_readiness.sql": "a6c0f19a3900ae4576a9d6edb5fa11cc3c437f5de086b1e628dd9492e3dc2a3c",
    "migrations/0047_safety_review_approval_readiness.sql": "647d8e67e13b7307144438473bc298167f49c67b40c0d8c20b82dde435ff0507",
    "verify_safety_review_decisions.sql": "401938449777cc45827062cf14f08434cbd0eddd82c80b40caee814b3d6f1070",
    "verify_safety_review_arrangement_reviews.sql": "8c7602f5366229bbc0ae38c02a5f818cc32484a4c82d58ace1bbea8e91e5000c",
    "verify_shared_event_readiness.sql": "55803187c95990062be3bda03bb45aaa665d05c61bd0293908984bcf85f6059d",
    "verify_safety_review_approval_readiness.sql": "44455ab8f6848f6abbc9c3877225568614a446c3c1a0234a7cff8eb00a63aadc",
}
for name, digest in expected.items():
    if hashlib.sha256((archive / name).read_bytes()).hexdigest() != digest:
        raise SystemExit(f"Pinned external source mismatch: {name}")
PY_CHECK

python3 database/tests/bootstrap_event_status_history.py \
  --dsn "$SCRUM64_TEST_DSN" --disposable || exit 1
psql -X -v ON_ERROR_STOP=1 -d "$SCRUM64_TEST_DSN" \
  -c "ALTER TABLE auth.users ADD COLUMN raw_app_meta_data jsonb NOT NULL DEFAULT '{}'::jsonb; INSERT INTO auth.users DEFAULT VALUES" || exit 1

for migration in \
  0001_baseline.sql \
  0002_transition_equipment_status.sql \
  0003_create_equipment_fn.sql \
  0004_quantity_history.sql \
  0005_rls_and_function_access.sql \
  0006_rpc_execute_grants.sql \
  0016_venues.sql \
  0017_notifications.sql \
  0018_venue_booking_requests.sql \
  0018_event_change_requests.sql \
  0019_event_change_requests_organiser_index.sql \
  0020_event_change_request_updated_at.sql \
  0021_event_change_request_monotonic_updated_at.sql \
  0020_equipment_reservations.sql \
  0021_equipment_requirements.sql \
  0027_equipment_reservation_requirements.sql \
  0028_reserve_equipment_type_check.sql \
  0026_event_request_planning.sql \
  0029_safety_review_status.sql \
  0030_arrangement_review_reads.sql \
  0031_arrangement_review_event_changes.sql \
  0032_arrangement_review_clear.sql \
  0033_arrangement_review_equipment_unavailability.sql \
  0034_safety_review_decisions.sql \
  0035_arrangement_review_shared_reads.sql \
  0036_arrangement_review_safety_rechecks.sql \
  0037_arrangement_review_notification_outbox.sql \
  0038_arrangement_review_notification_delivery.sql \
  0039_send_for_safety_review.sql \
  0040_arrangement_review_safety_recheck_lock_compatibility.sql \
  0041_booking_request_cancelled_status.sql \
  0042_cancel_venue_booking_request.sql \
  0043_venue_setup_turnaround.sql \
  0044_safety_review_null_inputs.sql \
  0045_safety_review_arrangement_reviews.sql \
  0046_shared_event_readiness.sql \
  0047_safety_review_approval_readiness.sql
do
  case "$migration" in
    0034_safety_review_decisions.sql|0039_send_for_safety_review.sql|0044_safety_review_null_inputs.sql|0045_safety_review_arrangement_reviews.sql|0046_shared_event_readiness.sql|0047_safety_review_approval_readiness.sql)
      source_file="$SCRUM64_EXTERNAL_SQL_DIR/migrations/$migration" ;;
    *) source_file="database/migrations/$migration" ;;
  esac
  psql -X -v ON_ERROR_STOP=1 -d "$SCRUM64_TEST_DSN" \
    -f "$source_file" || exit 1
done
```

Each migration uses its own `psql` invocation: 0041 must commit its enum value
before 0042 consumes it. This is an isolated fixture recipe, **not** a shared
rollout command. Retain the reviewed production rollout/write-hold boundary
above; no shared migration is applied by these instructions. If local PostgreSQL
is accessed through a wrapper, put its `psql` executable on `PATH` for both the
bootstrap and direct commands.

#### Published workflow SQL and local integration checks

After all 37 files, optionally run all four exact upstream workflow checks. The
current decision verifier uses a real target and a ready approval fixture, so it
is compatible with 0045/0047. The latest approval verifier also includes AC6-X13
for duplicate-target `22023` refusal before writes. Every script rolls its fixtures
back:

```sh
for verification in \
  verify_safety_review_decisions.sql \
  verify_safety_review_arrangement_reviews.sql \
  verify_shared_event_readiness.sql \
  verify_safety_review_approval_readiness.sql
do
  psql -X -v ON_ERROR_STOP=1 -d "$SCRUM64_TEST_DSN" \
    -f "$SCRUM64_EXTERNAL_SQL_DIR/$verification" || exit 1
done
```

The ten independent SCRUM-64 SQL checks and three disposable lock-compatibility
cases above can also run unchanged against this combined fixture. Run the local
saved-caller/gate contract checks separately:

```sh
SCRUM64_INTEGRATION_SCOPE="${SCRUM64_INTEGRATION_SCOPE:-all}"
case "$SCRUM64_INTEGRATION_SCOPE" in
  decision|handover|all) ;;
  *) echo "Scope must be decision, handover or all" >&2; exit 1 ;;
esac
python3 database/tests/test_safety_arrangement_integration.py \
  --dsn "$SCRUM64_TEST_DSN" --disposable --scope "$SCRUM64_INTEGRATION_SCOPE"
# Add --psql /path/to/psql-wrapper if required.
```

Scope selects test methods only: `decision` checks the saved caller and approval,
`handover` checks the handover consumer and `all` checks both. It does not alter
schema dependencies or assertions. These native checks exercise persisted roles,
real workflow functions, reviews, history and transactional outbox behaviour;
they do not prove JWT/HTTP/browser authorisation, shared deployment or PR CI.
See [`scrum_64_integration_handoff.md`](../docs/testcases/scrum_64_integration_handoff.md)
for current runner hashes, exact counts and execution status. A passing local
snapshot is not a claim that the workflow is deployed to shared Supabase.

#### Earlier source/evidence pins (historical only)

The preceding full-stack source pin was
`4a5bc9349ecb91d260454b6a9db77beea15e5793`, with 0047 SHA256
`c0ab8732be85a2c8226e7ae5ab2156f89efb1430e4c479d319773c2817435993`
and approval verifier SHA256
`6f7912f04bc1656b2573a29dada5eb34479d3cf399ce75e1ffbe71a81748abb0`.
Its recorded results remain tied to that source; they are not current evidence
for e7888dc's duplicate-target change. Current execution status belongs in the
integration handoff, separately from these reproducible source inputs.

Earlier PR62 commit `289a814917dc8a9e4f874b43595285cf7dc68ef9` used the same
0034 digest `4099f1f7a0c60df682d076c0080e7911da05008495313126de0c9e3f79e817aa`
and verifier `9627a4da26058dd4fe3f8bfbd18abcf8763b4124f2157185176bbc786179c916`.
The later `135536cd1e0713052476ef0b17ce78c9c7542a0e` added 0044 NULL validation
with verifier `879a3644a66540e28565bc0abc51659cc61d3e9645e8c774ad423b3c665ddf65`;
its decision-only 32-file and full 33-file fixtures predated the 0045–0047
connections. Tate's earlier 0039 was pinned at
`bf31002c4928c6d953be89bb7f34e3f257fd883e` (digest unchanged above).
The original frozen runner was
`78ad48f8926f703fd86724d3086f9837f0ab43e6ab92e8c8f96210744f33a76e`.
Those missing-connection failures and initial venue 42501 remain historical
results; they do not describe the current published connections. The separately live-verified
local venue ACL snippet had SHA256
`4eafc51e7a40f66bdf96b2e637c68e621bd09f3fd02cf896c1952d39c1146724`.
It was a local platform-precondition workaround, never a repository migration,
and is unnecessary with the current 0046 stack.

This optional fixture does not import the later workflow migrations or prevent
independent SCRUM-64 review. PR62's initial decision API/UI and 0034/0044 are now
merged through `dev`; the saved decision/lifecycle and shared readiness gates
remain owned by SCRUM-60/SCRUM-58. SCRUM-64 supplies their review helpers.
No production replacement, privileged shim or shared deployment is added here.

## Event status history contract (SCRUM-48)
Migration `0025` was **applied to shared development on 10 October 2026** after
explicit requester approval, as MCP migration `20261010034216`
(`event_request_status_history`). Do not reapply it there. It created 12 labelled
baselines for the 12 existing events; verification fixtures were rolled back.
It depends on the event-request, assignment and review-decision migrations through
`0016` and the existing `private` schema. It does not change authentication or add
new transition rules. Before deployment, compare the three replaced RPC definitions
with the target database to avoid overwriting another team's newer changes.
For a fresh environment, deploy the database change before the new service/UI
and run the rolled-back verification afterwards. If verification fails, stop the release and inspect the
failure; do not drop history to make the checks pass. Removing this migration is
not a data-preserving rollback and would need a separately reviewed recovery plan.

All actual status writes are recorded by private triggers in the same transaction.
A trusted status-changing RPC must first verify the caller, lock the event row and
validate its current state/assignment, then supply its actor immediately before the
status update:

```sql
PERFORM private.set_event_status_actor(
    p_event_request_id, p_verified_actor_id, 'event_coordinator', 'coordinator.action'
);
UPDATE public.event_requests SET status = p_new_status WHERE id = p_event_request_id;
```

Call the helper and update within **one database RPC/transaction**, never separate
REST requests. Context is scoped to the event, transaction-local and consumed once.
System workflows use a null actor ID, role `system` and a named source. The helper
rejects invalid context with `22023`. Creation and Draft submission identify the
owning Organiser through their existing authenticated workflow. A privileged
status update without context is recorded honestly as `system` /
`database.status_update`; it never guesses the actor from an assignment.

The service role has SELECT only on history; browsers have no table access or
helper execution. The immutable-history triggers reject independent update,
delete and truncate with `P0003`. The existing Draft-discard cascade is preserved;
retained events cannot be deleted to erase their status evidence.

Run [`verify_event_request_status_history.sql`](verify_event_request_status_history.sql)
after `0025`. It requires an existing auth user, creates only transactional fixtures
and rolls back. It covers creation/submission, all current coordinator writers,
resume, named system work, actor boundaries/context isolation, failure rollback,
refused side effects, chronology, immutability, grants and actual server-role RPC
execution. It prints `ALL EVENT STATUS HISTORY VERIFICATIONS PASSED`.

Shared PostgreSQL 17.6 verification passed for creation/direct submission,
review/clarification/resume/approval, cancellation/completion/rejection, refusal,
write-failure rollback, actor boundaries/isolation, Draft discard, retained-event
protection, immutable update/delete/truncate and actual service-role execution.
The MCP returned `Invalid or expired requestState` for the combined script;
its assertions were checked through shorter rolled-back blocks instead. The
single-call script run remains unverified on the connector. The real repository
also read a valid baseline through shared PostgREST, while the publishable-key
read was refused with HTTP 401 / `42501`. See the SCRUM-48 test document for
remaining authenticated UI/CI/human-review checks and advisor findings.

The two-connection race test is **local only** because it commits fixture rows:
use a disposable migrated database with an existing fixture auth user, then discard
the entire database after the test. It refuses non-loopback database URLs and needs
only Python's standard library plus `psql`:

```bash
python3 database/tests/test_event_status_history_concurrency.py \
  --dsn postgresql://scrum48_test@127.0.0.1:55484/postgres \
  --psql /opt/homebrew/opt/postgresql@14/bin/psql
```

The example identifies the disposable cluster used for the recorded local run;
create/migrate your own disposable cluster before rerunning it. No shared Supabase
credentials should be supplied. A duplicate transition must yield one success,
one `P0004` conflict and exactly one additional matching history row.

Supplemental live API checks are opt-in through
[`tests/verify_live_event_status_history.py`](tests/verify_live_event_status_history.py),
which is not part of normal pytest runs. Start the real auth, event and frontend
services and use the existing development test accounts shown on `/auth`.
The `prepare` and `race` modes require explicit approval for shared test writes and
`--allow-shared-test-write`; they retain their labelled fixtures rather than delete
them. Keep application notification delivery disabled for this bounded check.

See [`docs/testcases/scrum_48_testcases.md`](../docs/testcases/scrum_48_testcases.md)
for the `access`, `prepare` and `race` commands and execution evidence. Overlapping
HTTP calls are supplemental integration evidence, not deterministic proof that
shared database row locks overlapped; storage side effects need separate checks.

The timeline does not replace clarification or amendment records. Future
SCRUM-35/40/58/60 status producers must adopt this contract when their stories are
implemented. This migration does not enable those stories or their notifications.

## Test accounts

[`seed_test_accounts.sql`](seed_test_accounts.sql) confirms the shared dev test
accounts (one per role, two coordinators, password `12345678`) and assigns
their roles. Register the accounts first; see "Test accounts" in
`docs/authentication.txt`. Dev only; never run it on production.

## Verification queries

Re-run these in the SQL Editor if you suspect the migration file has drifted from the live schema:

```sql
-- Columns: types, nullability, defaults
SELECT table_name, column_name, data_type, udt_name, is_nullable, column_default
FROM information_schema.columns
WHERE table_schema = 'public'
ORDER BY table_name, ordinal_position;

-- Varchar lengths and identity columns
SELECT table_name, column_name, character_maximum_length, is_identity, identity_generation
FROM information_schema.columns
WHERE table_schema = 'public'
  AND (data_type = 'character varying' OR is_identity = 'YES');

-- Constraints: PK / FK / CHECK
SELECT conrelid::regclass AS table_name, conname, pg_get_constraintdef(oid)
FROM pg_constraint
WHERE connamespace = 'public'::regnamespace;

-- Indexes on the equipment tables
SELECT tablename, indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'public'
  AND tablename IN ('equipment', 'equipment_status_history');

-- Functions defined for the equipment domain
SELECT proname, pg_get_functiondef(oid) FROM pg_proc
WHERE proname ILIKE '%transition%' OR proname ILIKE '%equipment%';
```

Still to export from the live database (open TODO in `0001_baseline.sql`): RLS policies (`SELECT * FROM pg_policies WHERE schemaname = 'public';`) and triggers (`SELECT * FROM information_schema.triggers WHERE trigger_schema = 'public';`).
