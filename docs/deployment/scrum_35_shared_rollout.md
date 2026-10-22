# SCRUM-35 shared database rollout — 22 October 2026

**Applied and database-verified.** This record covers rejection and supported
non-date approval only. It supersedes the earlier "prepared/not applied" standing
for these two routines. It does not declare SCRUM-35 Done or deploy the application.

## Target and application record

- Project: **SPM G9T4**, `rrmvhxrxrrnigjdxcbwt`, PostgreSQL 17.6.
- User authorisation: "okay deploy it", after the proposed migration review and
  live non-date workflow were outlined in the originating chat.
- Migration version: **`20261022025742`**.
- Migration name: **`scrum35_rejection_and_non_date_approval`**.
- Executor: root, through Supabase MCP `apply_migration`; successful response and
  a subsequent migration-history read both confirmed the application.
- Source checkout: `9be8b93` plus preserved, uncommitted SCRUM-35 work. Source
  hashes below identify the actual deployed files independently of that checkout.

| Source, applied in this order | SHA-256 |
| --- | --- |
| [0049 rejection](../../database/migrations/0049_event_change_rejection.sql) | `69aeba1c8217525bfa6c92f27c7defaa583f49b8c8f050b42fbbc1c78796a26b` |
| [0053 non-date approval](../../database/migrations/0053_event_change_non_date_approval.sql) | `b038214ef551d296b8eb413356231f2ef11f877742ae13218192776433b9727f` |

Devon prepared the bundle; root reviewed the live prerequisites and executed it.
The one-transaction payload contained a fail-closed absence guard for either new
routine name, both files verbatim, `SET LOCAL lock_timeout = '3s'`,
`SET LOCAL statement_timeout = '30s'` and `NOTIFY pgrst, 'reload schema'`.
The executor supplied the transaction boundary. Bundle SHA-256:
`1eaceb5d3619281a21b2c47ed1fa894e08b7d261317eab103f64c4a0340587fd`.

Installation added only these two functions and their EXECUTE grants. It did not
backfill/update business rows, replace existing functions or triggers, change
table grants/RLS, create accounts or alter credentials. Do not replay the sources
against this shared project or bypass the absence guard.

## Preflight and readback

Root checked the healthy project, absence of both routines, 45 required columns
(none missing), enabled review/enqueue triggers and required service-role access.
No other active transaction was observed at preflight time. After application:

| New routine | MD5 of exact stored `prosrc` | Security/access result |
| --- | --- | --- |
| `public.reject_event_change_request(uuid,uuid,varchar,text)` | `3072d43b82c4dd2389f451e97fafc41c` | INVOKER, empty search path; service EXECUTE true, anon/authenticated false |
| `public.approve_non_date_event_change_request(uuid,uuid,varchar,text)` | `cd76e2caa5180a262c0b16525880007b` | INVOKER, empty search path; service EXECUTE true, anon/authenticated false |

Five existing `pg_get_functiondef` hashes remained identical:

| Existing routine | Preserved MD5 |
| --- | --- |
| `private.check_booking_candidate` | `ccad16d8aeff87ffff7dda393675fdb8` |
| `public.decide_event_change_request` | `24a5e1ed95d8824db51418406a331f56` |
| `private.record_event_arrangement_reviews` | `3a993f51813dbc4339e61753d89e2105` |
| `private.enqueue_arrangement_review_notification` | `7fd5c2a73425dcbb40b051c476784e4d` |
| `public.set_event_request_updated_at` | `029946c380aad340b45a256629313c0e` |

## Executed verification

Vera authored the [shared rollback verifier](../../database/verify_event_change_shared_smoke.sql).
Root reviewed and executed those exact frozen bytes, SHA-256
`59e16eb70a81ffa6e385900a45e1eef80c0c4d7aedad3c03835d8f9ec431a5ad`.
It uses one BEGIN/ROLLBACK with 15-second statement, two-second lock and
20-second idle-in-transaction timeouts. It creates isolated random-UUID fixtures,
reads existing account identities without modifying them and performs no shared
fault-trigger/schema/privilege changes. Its assertions **passed**:

- Real service-role rejection saves its audit and preserves the event plan,
  arrangements, lifecycle history and queued work.
- Real service-role non-date approval applies the exact three supported fields
  and saves its audit with two affected domain reviews and pending outbox rows.
- Replay, stale/mixed proposals and unrelated coordinators are refused with their
  specific SQLSTATEs and unchanged protected fixture state.
- Actual anon/authenticated calls to both routines are denied with `42501`.

The transaction rolled back. Before/after counts and whole-row hashes matched
across all **12** checked tables: events, proposals, status history, assignments,
venue bookings, equipment, equipment requirements/reservations, arrangement
reviews, review jobs, submission jobs and notifications. No test rows remain in
those tables. Native audit sequences may advance during rolled-back fixture
creation; harmless gaps are possible and sequences were not reset.

Root also exercised both routes through the **real application repository and
shared PostgREST**, using the configured server key and fresh nonexistent event
IDs. Both returned the expected `P0002` through the new RPCs. No successful
decision, notification or fixture write was attempted through HTTP. This proves
RPC availability/service access, not a normal-user authenticated workflow.

The security-advisor comparison introduced no findings. Existing findings remain:
25 informational RLS-without-policy notices for server-managed tables,
three equipment-function [mutable-search-path warnings](https://supabase.com/docs/guides/database/database-linter?lint=0011_function_search_path_mutable)
and disabled [leaked-password protection](https://supabase.com/docs/guides/auth/password-security#password-strength-and-leaked-password-protection).
They were not changed or presented as resolved by this rollout.

## Evidence, recovery and remaining work

Raw reviewed source, preflight, migration response/history, catalogue readbacks,
advisor snapshots, rollback result and fingerprint comparison are retained under
`/tmp/scrum35-shared-rollout-20261022/`. The source-native fault and concurrency
checks retain their earlier disposable-database evidence; no shared injected
failure or overlapping-concurrency proof is claimed here.

On a failed/ambiguous future rollout, inspect migration history and actual
definitions before retrying. A committed reversal would require a separately
reviewed dependency/caller check and removal of only the two new exact signatures,
without CASCADE. Never delete business history or rewind shared sequences to
hide an outcome; removing a function would not undo decisions already made.

The subsequent real Playwright journey on 22 October verified normal organiser,
Coordinator Lead and coordinator login, creation/assignment, supported non-date
approval, reasoned rejection and both recipient-visible organiser outcome links.
Event `9d885685-3232-418c-85d5-4433866a115f` is retained as labelled evidence;
rejection preserved the complete approved event row and lifecycle history.
See the [dated browser record](../testcases/scrum_35_testcases.md#real-signed-in-approval-and-rejection-journey--22-october-2026).
No booking or equipment reservation was created in that journey, so it does not
prove recipient-visible affected-arrangement review delivery.

Application publication/review/CI and the remaining original acceptance scope
are still pending. This original 0049/0053 rollout did not install date or
registration approval. The separately authorised 0056/0058/0059 bundle was later
applied on 22 October as `20261022114717`; its
[deployment and signed-in journey record](scrum_35_date_rollout.md) documents
the current date/membership protocol without attributing it to this first rollout. No application code, original
migration, acceptance criterion or protected DoD file was edited during
deployment. The shared verifier is retained unchanged from Vera's handover.
