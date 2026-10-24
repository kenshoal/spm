# SCRUM-40 automatic-completion rollout plan — 24 October 2026

**Prepared only; no shared rollout is authorised or claimed here.** Target for a
later reviewed rollout is SPMG9T4 (`rrmvhxrxrrnigjdxcbwt`). Source/CI publication,
human review and actual shared Auth/API/worker verification remain separate gates.

| Exact source | SHA256 |
| --- | --- |
| [0063_event_auto_completion.sql](../../database/migrations/0063_event_auto_completion.sql) | `22d80816844c576637778a6bbad9a43f97c954a8fbba1ba3aa0b7ef10ca13330` |

## Review and preflight

A read-only shared catalogue check on 24 October found `final_event_end_at`,
`complete_overdue_event_request` and `set_event_request_final_end` absent. Existing
status-actor/history and date-approval routines were present. This is a dated
preflight, not evidence of installation; repeat the comparison immediately
before any separately authorised rollout. The nullable column has no default
or data backfill, and the finite constraint is installed with it.

- Confirm the project, current migration history and published allocation before
  using 0063. Do not overwrite existing functions/columns/triggers without an
  exact-definition comparison. Original applied migrations are not edited.
- Confirm canonical event/assignment tables, the existing updated-at trigger,
  immutable history trigger and `private.set_event_status_actor` helper. Recheck
  service event SELECT/UPDATE, assignment SELECT, private-schema usage/helper
  execution and browser denial. Capture current definitions/grants, enabled
  trigger wiring and advisor baseline.
- Capture business counts/fingerprints, including resources, registrations,
  reviews, outboxes and inbox. Adding the nullable final-end column changes row
  JSON shape: compare the old event-column projection and separately require
  every pre-existing end to remain NULL immediately after installation.
- Inventory old service versions and privileged date-edit scripts. The new
  guard deliberately refuses end changes after Confirmed/terminal and actual
  proposed-date changes there when an end is recorded; unsupported admin writes
  must not silently bypass it. Normal Approved/Planning reschedules clear the
  end, and existing manual completion/confirmation contracts stay unchanged.
- Keep `AUTO_COMPLETION_ENABLED=false` during schema/application rollout. The
  nullable column has no inferred backfill; existing Confirmed rows without an
  end must remain skipped, not receive a guessed deadline. Their existing manual
  completion remains available. No new confirmation gate is installed.

## Reviewed execution sequence for a later authorised rollout

1. Obtain approval for this exact source and current deployment plan. Apply 0063
   once in one atomic migration with transaction-local `lock_timeout='3s'` and
   `statement_timeout='30s'`; include `NOTIFY pgrst, 'reload schema'` for commit.
   Timeouts/errors roll back: stop, inspect blockers/history and review before
   retrying. Do not silently extend timeouts or reapply an ambiguous result.
2. Check both public INVOKER/empty-search-path signatures, service-only EXECUTE,
   private guard with no direct EXECUTE, finite nullable column/constraint and
   enabled update guard. Compare unchanged business projections/grants/advisors.
   No resource, registration, notification or delivery rows should be written
   merely by installing the migration.
3. Deploy the matching API/UI with the worker still disabled. Verify current
   assigned-coordinator recording while Approved/Planning, explicit Singapore
   input/readback, same-instant no-op, reschedule clearing and owner read-only
   display. Recheck existing manual completion/confirmation without adding an
   end requirement. Legacy missing-end events remain visibly skipped.
4. Only after an approved bounded real-target check, opt into the worker and
   restart/recreate eventRequestService. Confirm interval/config, one real-clock
   pass, strict elapsed boundary, one system history row and no related-domain
   writes/notices. Do not supply a synthetic future clock on shared data. A
   trusted manual `--once` performs the same writes even when the daemon flag is
   false; it is not a dry run or unprotected HTTP trigger.

## Local evidence and boundaries

The [fresh recipe](../../database/README.md#automatic-completion-scrum-40) and CI
job use PostgreSQL 16 and genuine migrations. Local native oracles prove strict
168-hour/DST boundaries, all other states protected, missing-end skips, actual
system history time, rollback and browser denial. Both manual/automatic race
orders use real blocking and exactly one retained transition. The browser uses
real Next/Chromium with prepared API outcomes; that read/projection journey does
not claim to run the real scheduler or prove normal shared authentication.

Fault-trigger SQL and committed race fixtures are disposable-only: **never run
those native scripts on shared infrastructure**. A shared smoke must be separately
reviewed and use authorised labelled data, not copied fixture DDL. Existing
notification relays and Tate's separate SCRUM-38 handler remain outside this
domain change. The timer callback registry supports independent registration;
disabling auto completion does not imply disabling a future SCRUM-38 handler.

## Stop and recovery

Set `AUTO_COMPLETION_ENABLED=false` and restart/recreate the service to stop new
background passes. Cancellation waits for the active bounded-HTTP handler to
finish; cancelling a thread cannot undo an in-flight database write. Inspect
actual state/history before any retry. Disabling the worker does not undo a
Completed event or remove its system audit.

Prefer a reviewed forward fix. Before a schema reversal, stop affected callers,
capture current state and obtain root approval after dependency review. Never
use CASCADE, drop retained end/history evidence, bulk-revert completed statuses
or remove a record to hide a decision. This plan does not authorise shared DDL,
deployment, backfill or business-data mutation.
