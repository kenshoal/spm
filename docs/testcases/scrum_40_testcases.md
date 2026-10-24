# SCRUM-40 — Automatically Complete Overdue Confirmed Events

## Approved contract — 23 October 2026

**Status: Partially verified locally; Not Done for delivery.** Native completion/end-recording, atomicity, concurrency and focused API/worker tests pass. Final local gates pass. Shared rollout, a real authenticated workflow, deployed timer operation, publication CI and human review remain separate evidence gates. The requester explicitly approved a coordinator-recorded authoritative final event-end **timestamp** and automatic completion only **strictly after** that timestamp plus **168 elapsed hours**. Equality at seven days is ineligible. Every non-Confirmed state remains unchanged. Completion writes immutable, system-attributed status history with its actual transition time and no booking, equipment, registration or notification changes. No Jira criteria are edited by this record.

Source: the original seven Jira criteria freshly verified by root and the requester-approved clarifications recorded on 23 October; the earlier readiness review is `scrum-40-starting-plan-2026-10-23.md` in the Codex working folder. Its unresolved date/source questions are superseded by this approval. This specification is derived before inspecting production implementation.

User story: as an Event Coordinator, I want confirmed events to be completed automatically after they are overdue, so stale event records do not remain open indefinitely.

| Original AC | Approved observable interpretation | Review / scope |
| --- | --- | --- |
| AC1 | Given Confirmed with a recorded final end, a pass strictly later than end + seven days persists Completed. Just below/equal never completes. | Clarified timestamp source and strict boundary explicitly approved. No proposed-start/resource-return-date surrogate. |
| AC2 | Given any non-Confirmed lifecycle state, automatic completion leaves the complete event unchanged. | Clarified to include every state, including Changes Requested, Approved, Planning and Safety Review omitted from the original examples. |
| AC3 | Completion history identifies a system automatic action without fabricating a human actor. | Keep; use existing immutable history boundary, not a new audit subsystem. |
| AC4 | Completion history records actual completion time, distinct from scheduled end or eligibility threshold. | Keep; status and history atomic. |
| AC5 | Existing authorised organiser/coordinator views and timeline show Completed after refresh. | Keep existing relationships and no access widening. |
| AC6 | Completion changes event status/version and required lifecycle history only. | Keep; no resource release/rebooking, attendee registration mutation or notification. Tate owns separate SCRUM-38 handling. |
| AC7 | Repeated or competing completion attempts cannot rewrite a Completed event or create a second history entry. | Keep; authoritative state/eligibility under native row lock. |

### Included boundaries and dependencies

- Only the currently assigned coordinator may record the authoritative end in Approved or Planning, rechecked under the event lock. A same-instant save preserves the event version. An actual proposed-date change clears the end in editable states; a protected Confirmed/terminal record with an end refuses such a write. Equal dates retain the end. No confirmation-required gate is added. Organiser cannot forge the authoritative value through draft/change fields. Existing Confirmed rows without an end are skipped, never guessed or backfilled.
- The thin shared timer offers an aware clock, configurable interval, manual single pass and isolated callback failures. Each story retains its own persistence/idempotency; no generic job platform, provider setup, public run-jobs endpoint or SCRUM-38 domain logic is included.
- The initial rule/native slice proves completion, its actual history and forbidden side effects. New routine/import absence is setup only. A production-owned callable no-op scaffold may establish meaningful status/history assertion Red before its body.
- Parent owns Git, shared deployment and combined execution; Vera owns tests/fixtures/verifiers and this document; Devon owns production. No shared database writes are authorised to the test owner.
- Protected pre-existing user files remain byte-identical: `docs/standards/definition-of-done.md` SHA `2727346251a767d8d8d325059cf133e269fcc47bf460857a81d020e2fef5f586`; `docs/testcases/scrum_20_testcases.md` SHA `7c84b6fc2a59d4c90fa7a39c722bd246b7e245dcc7d1bdbee8b72300cf3d7fce`.

## Minimal initial test matrix — before production inspection

The frozen clock below is **2026-10-23 04:00:00 UTC** (12:00 Singapore). Native fixtures include nonempty bookings, reservations, registration data, existing histories and notification/outbox controls so unchanged-state assertions cannot pass vacuously. These are grouped by distinct risk, not copied at every layer.

| ID | AC / technique | Preconditions and concrete input | Action / observable expected result | Forbidden effects / layer | Execution |
| --- | --- | --- | --- | --- | --- |
| AC1-H1 | AC1/3/4/6; happy | Confirmed, final end `2026-10-16T03:59:59.999999Z`; nonempty protected related state | Run one actual system completion; event becomes Completed, one immutable automatic system history entry at actual transition time | Only target status/version and required history change; unrelated events/resources/registrations/notices unchanged. Native primary proof | Green — local |
| AC1-B1/B2/B3 | AC1; boundary | Confirmed, end respectively `2026-10-16T04:00:00.000001Z`, `2026-10-16T04:00:00Z`, `2026-10-16T03:59:59.999999Z` | Fixed-clock pass: first two unchanged, third completes; equivalent offset representation compares by instant | No premature completion from date truncation, `>=` or raw ISO comparison. Native; reuse H1 for above-boundary evidence | Green — local |
| AC2-P1 | AC2; partition | Every actual non-Confirmed enum state, each with an overdue end and existing history | Run completion; all rows/history remain exactly unchanged | A missing status predicate fails. Native grouped enum partition | Green — local |
| AC1-N1 | AC1/6; negative | Existing Confirmed row with no final end | Pass reports/skips it safely; exact event/history/related snapshot unchanged | No guessed proposed date, booking end or reservation return date. Native/handler | Green — local |
| AC7-N1 | AC7; negative | H1 event already Completed, first automatic history retained | Run again; zero second transition and full state unchanged | No changed audit time, duplicate history or unrelated side effect. Native | Green — local |
| AC3-X1 | AC3/4/6; cross-cutting | Due Confirmed row; distinctive local required-history write failure | Run actual completion; exact injected failure; entire before/after snapshot equal | No Completed state without required history; disposable-only fault setup, never shared | Green — local |
| AC7-X1 | AC7; cross-cutting | Competing real manual/automatic attempts for one due Confirmed row | Witness actual row-lock wait; exactly one transition/history and losing call no effects | No timing-only concurrency claim. Native two-session harness, one group with two winner orderings | Green — local PG16 |
| AC3-X2 | AC3/security; cross-cutting | Browser/app callers versus trusted system worker boundary | Direct forbidden calls refuse with specific access error; native history actor remains system | Human completion route cannot impersonate automatic actor. Native/API as applicable | Green — local |
| AC5-X1 | AC5; cross-cutting | Existing authorised organiser/current coordinator and a prepared Completed outcome | Normal read/timeline refresh shows saved completion/time/system source; unrelated actor cannot gain access | Reuse existing visibility regressions; one critical UI journey, not duplicated role matrices | Green — local |

### Frozen implementation boundaries — 23 October

The first native boundary is `public.complete_overdue_event_request(p_event_request_id uuid, p_as_of timestamptz) RETURNS boolean`, callable only by the service role. It locks and rechecks the event. The eligibility clock is distinct from the actual native history timestamp. History uses NULL actor ID, role `system` and source `event_request.auto_completed`; no duplicate completion-time column is required.

End recording uses `POST /event-requests/{id}/final-end` with required aware `final_event_end_at`, backed by `public.set_event_request_final_end(uuid,varchar,timestamptz)` returning the saved event. This is outside organiser draft/amendment input. Detailed API refusal assertions follow the frozen error contract, not guessed messages.

`AutoCompletionService.run_once(as_of=None)` captures one aware UTC clock per sweep. The shared `PeriodicTaskRunner(handlers, interval_seconds=60)` runs named zero-argument callbacks independently. Its asynchronous loop offloads synchronous work and awaits cancellation. Automatic startup is opt-in (`AUTO_COMPLETION_ENABLED=false`); `PERIODIC_TASK_INTERVAL_SECONDS` is positive with default 60. The manual `python -m app.services.auto_completion --once` uses real UTC and exposes no HTTP clock override. These seams do not implement SCRUM-38.

The coordinator end-write API/security and thin-runner matrices add only distinct interface cases. No new criteria are inferred from an interface suggestion.

## Five-question design review

1. **Does each case follow an approved requirement?** Strict elapsed timestamp boundary, only Confirmed, system audit, visibility, no other effects and repeat safety each map above to the original ACs and explicit requester clarification.
2. **Is the minimum happy path observable?** Native status plus exact immutable history and nonempty protected-state snapshots, not merely a return count or fake repository mutation.
3. **Would a plausible one-line bug fail?** `>=`, date truncation, removed Confirmed filter, invented human actor, omitted history, duplicate write or resource/notice update each violates a concrete assertion.
4. **Is the layer proportional?** Native transaction owns business state; Python tests cover distinct handler/clock/runner seams; one browser path covers visible end recording and status reload. Existing authorisation/visibility checks are reused where sufficient.
5. **What is not established by Green?** Local/double-backed tests do not prove shared application, real signed-in actor access, a running timer, exact-commit CI, merge or human review. These remain explicit delivery gates.

## Latest execution record

Initial source base is fresh dev `9276da2`, branch `feat/scrum-40-auto-completion`. Current local evidence is consolidated below; the original freezes remain historical provenance. Only the two pre-existing protected user-document changes existed at start. The test owner has not edited either protected file or production.

### First native oracle freeze

`/tmp/scrum40-start-20261023/vera/verify_event_auto_completion.sql`, SHA256 `943c689b9cfc5fcb6979a680977fac45e49700a86cc30d428fc7defd756b0190`, was frozen before the production scaffold. It starts with actual persisted status, then checks exact system history, actual execution time and full protected snapshots with nonempty bookings, reservations, registrations, review jobs and notifications. Later assertions cover strict boundaries, an intended DST check (strengthened below), all ten other lifecycle states, NULL end, repeat, required-history rollback and direct browser denial. Root reviewed the oracle. The production-owned column plus no-op callable scaffold is a setup prerequisite; no missing-function result is claimed as Red.

### Timer mechanism matrix — frozen before its scaffold

| ID | AC / technique | Concrete operation | Expected result and forbidden effects | Layer / status |
| --- | --- | --- | --- | --- |
| AC1-X2 | AC1; cross-cutting | Two named prepared callbacks; first raises, second records a call; run twice | Each sweep reaches the second callback, including after the first callback failed. No SCRUM-38 business rules are simulated | Runner unit; Green — local |
| AC1-X3 | AC1; cross-cutting | A handler blocks on a test-owned event; cancel the async runner after witnessing entry, then release it in `finally` | Handler executes outside the event-loop thread; loop remains responsive; cancellation awaits active completion and never starts the next callback | Runner async/thread boundary; Green — local |
| AC1-B4 | AC1; boundary | Nondefault interval 7 seconds, prepared sleep records its argument and cancels | Exactly one pass precedes the sleep; next interval is 7 rather than hard-coded 60. No real long wait | Runner scheduling; Green — local |

These mechanics use empty production-owned callables for initial behavioural Red, not missing-module failures. The completion handler clock/pagination and opt-in app/configuration were frozen separately below.

### Completion handler matrix — frozen before its scaffold

| ID | AC / technique | Preconditions / action | Expected result / forbidden effects | Layer / status |
| --- | --- | --- | --- | --- |
| AC1-X1 | AC1/2/7; cross-cutting | Prepared raw pages contain 2, 2, 1 and 0 rows despite requested limit 1000; one NULL end, true/false outcomes and one native-call outage; clock provider changes if read twice | One UTC clock for the whole sweep, five examined, two completed, one unchanged, one missing-end skip and one failed; continue to the empty page and to the last event; no fake eligibility or persistence algorithm | Handler unit; Green — local |
| AC1-H2 | AC1; happy | Explicit aware `as_of`, empty page, clock provider forbidden | Report five zero counters; one read, no completion call and no clock-provider invocation | Handler unit; Green — local |
| AC1-N2 | AC1; negative | Naive explicit clock or naive clock-provider result | ValueError before all repository access; no mutations | Handler unit; Green — local |

Prepared repository methods are `list_confirmed_for_auto_completion(after_id, limit)` and `complete_overdue_event_request(event_id, as_of)`. Native SQL remains authoritative for status/eligibility. `AutoCompletionService(repository, clock=None, page_size=1000)` reports examined/completed/unchanged/skipped_missing_end/failed counts. These infrastructure counters do not claim actual committed completion without native evidence.

### Authoritative end-recording API matrix — frozen before route implementation

| ID | AC / technique | Input / action | Expected result / forbidden effects | Layer / status |
| --- | --- | --- | --- | --- |
| AC1-H3 / AC1-P1 | AC1; partition | Current coordinator posts `2026-11-25T18:30:00+08:00` in Approved or Planning | 200 full saved event, same instant `10:30Z`, lifecycle retained; exact event/actor/aware timestamp forwarded. Prepared storage outcome, not a second fake native state machine | API; Green — local |
| AC1-N3 | AC1/security; negative | Assignment now belongs to another coordinator | 403 before setter call; complete prepared state unchanged | API; Green — local |
| AC1-N4 | AC1; negative | Missing timestamp or naive `2026-11-25T18:30:00` | 422 missing/timezone-aware validation; no setter call or state change | API; Green — local |
| AC1-N5 | AC1/security; negative | Prepared native P0002/P0003/P0004 or storage outage | 404/403/409 `final_end_unavailable`/502 safe `Final event end unavailable`; no raw SQL leakage or simulated mutation | API; Green — local |
| AC1-N7 | AC1/security; negative | Missing bearer reaches actual Auth dependency | Exact401 Authentication required, no Auth HTTP, no setter call or prepared-state change | API; Green — local |
| AC1-N8 | AC1/security; negative | Auth HTTP double verifies an organiser who owns the event | Exact403 Insufficient permissions, no setter call or prepared-state change | API; Green — local |

API tests exercise the real FastAPI route with explicit identity/storage doubles. Native checks own same-instant persistence, locked reassignment, exact editable states and schedule invalidation. Existing Auth dependency regressions are retained; these tests do not claim signed-in Auth verification.

### End-recording native matrix — frozen before setter body

| ID | Technique / concrete input | Expected result and forbidden effects | Status |
| --- | --- | --- | --- |
| AC1-H3 / AC1-P1 | Partition: current assignment, Approved / Planning, aware final end | Save only end/version; returned full row equals persisted row; no lifecycle history or related mutation | Green — local |
| AC1-B5 | Boundary: same instant as +08:00 and Z | Saved row/version and complete state unchanged | Green — local |
| AC1-N3 | Negative: former / NULL assignee | P0003 and complete snapshot unchanged | Green — local |
| AC1-X4 | Cross-cutting: equivalent proposed instants, then actual next-day proposal | Equal values retain end; actual change clears it atomically. Existing registration-review trigger remains intact; no unrelated mutation | Green — local |
| AC1-P2 | Partition: all nine states outside Approved / Planning | P0004, complete snapshot unchanged | Green — local |
| AC1-X5 | Cross-cutting: direct privileged date or end change on Confirmed / Completed / Cancelled / Rejected with a recorded end | P0004 and complete snapshot unchanged, never silently clears the protected end | Green — local |
| AC1-N6 | Negative: nonexistent event | P0002 and complete snapshot unchanged | Green — local |
| AC3-X2 | Cross-cutting: setter's service-only function grants | Browser EXECUTE denied, service EXECUTE available; reuse system-boundary case, not an extra story criterion | Green — local |

Initial historical verifier freeze: SHA256 `3fcd472da7b3e05f465ed72fb2e599f481db4c40d81205ca88f7e2dd2543ef58`, archived as `/tmp/scrum40-start-20261023/vera/verify_event_final_end.initial3fcd.sql`. The native setter callable scaffold must exist before execution. Its no-op persisted-end assertion established genuine missing behaviour; missing function did not. The initial `3fcd` version had a PL/pgSQL RAISE-format fixture parse error, corrected without changing assertions; final durable source is `e4b1aa0049d900827fca5e10f9f4444bd3b373d1d1cded510bbb0af5848fb831`.

### Operations/transport matrix — frozen before wiring

| ID | AC / technique | Concrete operation and expected result | Forbidden effects / status |
| --- | --- | --- | --- |
| AC1-X6 | AC1/7; cross-cutting | Actual adapter with controlled HTTP transport: Confirmed equality, ID-ascending keyset and end-only projection; short page still followed by empty page; exact completion RPC aware UTC body and scalar true/false; exact setter RPC three arguments/object response | No resource/history writes over REST, no object-array truthiness or omitted scope; Green — local integration probe |
| AC1-X7 | AC1; cross-cutting | Standalone worker settings default disabled/60, enabled/7 without notification URL; zero/negative/nonfinite intervals refused. Enabled factory calls named completion handler, default factory returns None. Injected app lifespan starts and cancels its runner; ordinary injected apps construct no worker | No notifier dependency, implicit background work or SCRUM-38 implementation; Green — local integration probe |
| AC1-X8 | AC1; cross-cutting | CLI `--once` invokes one service pass without clock override, emits its JSON counts and returns 0/1 for success/failed-event report/exception; closes owned service each time | No repeated timer or web run-jobs endpoint; Green — local integration probe |

Frozen source `tests/test_auto_completion_infrastructure.py` SHA256 `3aef4925e6fca73ba9223372bbe4dc36fe5274fcb8fa736a8188a90fd9c2656e`. These three boundary probes complement the already observed native/API/handler Red; missing new configuration/factory symbols would be setup-only, never a fabricated extra behavioural Red.

### UI projection freeze

`frontend/__tests__/auto-completion-history.test.tsx` SHA `fc0053270561bfb57063f17f0a3a6c999049da19ea3d39dfe237a47b5d347afe` requires the exact source-specific label `Completed automatically`, retaining System, transition, semantic time and explicit refresh. Manual completion must not acquire the automatic label.

One browser journey, `frontend/e2e/auto-completion.spec.ts` SHA `83c1bdf8cf710c5c04bc621c74705abc1d821579f4f645a661bd703102f64295`, records `2026-11-25 18:30` Singapore as `10:30Z`, reloads it, checks organiser cannot edit, then displays an explicitly prepared Completed projection in both normal readers. Its fixture source SHA is `9fd62d0786e5ef79e8daf78dbc140fab1cfe4683a6590238ffa7d12045b77d28`. The prepared endpoint does not calculate eligibility or simulate the worker transaction. Native proof owns that behaviour.

## Current execution evidence — 23–24 October 2026

The specification tables above now show their latest local execution status. The frozen-source and initial Red history below preserve the earlier sequence. Counts below distinguish grouped native checks, focused tests and whole-service regressions; they are not additive story-case totals.

| Boundary / cases | Observed result | Command / environment / evidence |
| --- | --- | --- |
| Native completion AC1-H1/B1/B2/B3, AC2-P1, AC1-N1, AC7-N1, AC3-X1/X2 | Initial scaffold left due event Confirmed: genuine H1 Red. Exact original `943c` then passed all seven NOTICE groups and ROLLBACK | Root, owned PostgreSQL16 `scrum48_auto_completion`, `psql -X -v ON_ERROR_STOP=1 -f database/verify_event_auto_completion.sql`; `native-red.log`, `native-green-attempt1.log` under `/tmp/scrum40-start-20261023` |
| Native end recording H3/P1/B5/N3/X4/P2/X5/N6 and setter grants | Initial fixture parse error was setup-only. Corrected `e4b1` failed actual persisted-end H3 against callable scaffold, then all four NOTICE groups passed with ROLLBACK | Root: `setter-native-red.log` (setup), `setter-native-red-corrected.log`, `setter-native-green-attempt1.log`; same owned PG16 and psql command targeting `database/verify_event_final_end.sql` |
| Final DST boundary, same AC1-B1 | Post-Green review found original March8 anchor was already after the DST transition. Only two fixture instants changed: March7 17:30Z =12:30-05:00 and March14 17:00Z =13:00-04:00; actual elapsed167.5h. Final `b165` passes all original groups | Independent Python `zoneinfo` conversion plus root actual PG16 `native-dst-strengthened-green.log`. Original `943c` Red/Green archive retained; this is oracle strengthening, no new feature Red/case |
| Required history failure and full no-side-effect snapshots | Actual injected23514 reached; event/history/related rows rolled back. Nonempty booking/reservation/registration/inbox/outbox controls remained unchanged on completion | Included in the native completion file; fault trigger is disposable-only, never a shared rollout script |
| Concurrent AC7-X1 | One unittest group, both automatic/manual winner orders passed; actual blocking PIDs 258→259 and260→261, exactly one Completed history, exact winning actor/source and no losing effects | Root, `python3 database/tests/test_event_auto_completion_concurrency.py --dsn <owned loopback DSN> --psql /opt/homebrew/bin/psql --disposable`; source `fe2fa265b4b656ebd48d7fdd38da75585f68952ce9f743b683d03cbc1faaf260`. Fixtures commit only in this disposable database |
| Equality mutation, same AC1-B2 | Deliberate refusal `<=`→`<` was killed at premature boundary. Connection rollback restored original function MD5 `3aec426423c7ad63d35ac9346839fffa` | Root, `boundary-mutant.log`; test-only guarded script `vera/check_strict_boundary_mutant.sql`, no new testcase |
| Final-end HTTP AC1-H3/P1/N3/N4/N5/N7/N8 | Initial actual route404 vs200 was genuine Red. Final 11 executions include missing bearer401 and verified-organiser403; native/storage doubles are explicit | Initial `49b036` Red log `vera/final-end-api-red.log`; original frozen source archived. Final source includes only two requested endpoint Auth cases and import-order maintenance |
| Handler AC1-X1/H2/N2 | Zero-count callable scaffold was genuine assertion Red; final 4 executions pass | `vera/handler-red.log`; prepared raw pages/outcomes only, not a fake eligibility engine |
| Runner AC1-X2/X3/B4 | Initial empty callback result was genuine Red; final 3 executions pass, including actual thread barrier and awaited cancellation | Root/Devon runner logs; frozen `6e270c27` retained |
| Infrastructure AC1-X6/X7/X8 | Missing PeriodicTaskSettings import was setup-only; all 3 final boundary probes pass | `vera/infra-first.log`; no extra Red claim. HTTP MockTransport, settings/factory, injected lifespan and CLI are distinct integration probes |
| Independent final focused backend | **21 passed, 0 failed/skipped, 2 existing dependency warnings, 0.52s**; targeted Ruff passes | Vera, from `backend/eventRequestService`: `.venv/bin/python -m pytest tests/test_auto_completion_infrastructure.py tests/test_auto_completion_service.py tests/test_event_final_end.py tests/test_periodic_task_runner.py -q -p no:cacheprovider`; `vera/focused-after-lint.log`. Warnings: Starlette httpx compatibility and AnyIO BlockingPortal deprecation |
| Calendar-day mutation, same AC1-B1 | Deliberate168hours→7days was killed at the genuine DST-crossing assertion. Original function MD5 restored to `3aec426423c7ad63d35ac9346839fffa` by connection rollback | Root `calendar-day-mutant.log`; guarded local-only script `vera/check_calendar_day_mutant.sql`; no new case/count |
| Native fresh setup/regression | Full atomic0063 installed on a second empty owned PG16 through genuine0059 baseline; both40 verifiers plus existing date approval, registration review, arrangement flag and venue-timing verifiers pass | Root `fresh-*.log`. Exact production migration SHA `22d80816844c576637778a6bbad9a43f97c954a8fbba1ba3aa0b7ef10ca13330`; no shared mutation or runtime enablement implied |
| Source-specific history AC5-X1 | Missing `Completed automatically` label was genuine observable Red. Developer reports1 new + 14 existing history executions Green | `vera/history-red.log`; frozen new test `fc005327`. This is a component/source-presentation check, not real Auth |
| One browser journey AC5-X1 | Original83c1 first actual page lacked Final event end region: genuine UI Red, configured production build succeeded. **Final strengthened journey Green** as part of 51 browser tests, including actual-page cleared-end refresh and re-recording | Root-owned copied frontend `/tmp/scrum40-ui-check-20261023/frontend`; prepared Auth/APIs, no native worker emulation |

### Review corrections and final source provenance

- The final browser source is `0fa6a71e1fbe7f078c3d58c001c688f16d19c14ffdbbdab51c478ab83dbc0448`; prepared fixture is `247a6e6026cf3d13ca9a75cbdcafc1bbcb1963bba3ebf029387ae4d79c27be5c`. It additionally refreshes the actual page after a prepared cleared end and re-records it. Initial83c1/9fd62 sources remain archived.
- **Retired AC5-N1 draft:** direct unkeyed form rerender `b0b5` failed, but the actual coordinator page already keys the form by the recorded end (`page.tsx:99`). That draft tested an unsupported component context. It was removed from the repo, archived with its log and is **not** a product defect, feature Red or extra passing case. The actual-page browser assertion checks the requirement at its real boundary; no production fix was made to fit the invalid draft.
- After the first 21 Green run, test-only import ordering and the CLI fixture's captured loop variables were cleaned up. All expectations remain intact; final backend test hashes are infrastructure `3d937f598484d63e5486479c9d100b96ed29999745557f01decccec379a17def`, handler `bc3f9d5c3841ec78fb618cb28526a49ee9dfb39f6d7035afe349a018ad109fd1`, API `8b7bb0020b53093ae8f65f10aca6543d794a4d93c609bcc90f8906aa187180d4` and runner `6e270c27fcb56e6db7cc9c6f30168756879f9037ee23befd9147bfa31b386fc9`. Original pre-lint versions are archived under `vera/*.pre-lint`.
- Current durable native completion SHA is `78d7eb4136809867fbac87f10030f9c2908f3f5e6ec8a1b32de71dc05f30e00f`; setter SHA is `e4b1aa0049d900827fca5e10f9f4444bd3b373d1d1cded510bbb0af5848fb831`. No assertions were derived from sampled production output.

### Delivery limits

Shared0063 application, real coordinator/organiser sessions, a deployed running worker, actual manual CLI against deployed storage, publication CI and human review are not established by this local record. The optional notification receiver integration is separate from completion: completion must send no notification. Missing-end legacy Confirmed events deliberately remain unchanged and are reported as skipped. SCRUM-38 registration handling remains Tate's separate callback/domain. No confirmation-required gate, guessed end, resource release or terminal-state rewrite is introduced. Protected user documents retain their recorded hashes.

## Final local quality gates — 24 October 2026

These are whole-project/service regression totals on dev `9276da2` plus this local SCRUM-40 diff. They are not story-specific case counts, real Auth checks or shared rollout evidence.

| Gate | Actual result | Command / boundary |
| --- | --- | --- |
| Event service full backend | **793 passed, 1 skipped, 2 known deprecation warnings, 12.71s** | Root, from `backend/eventRequestService`, `.venv/bin/python -m pytest -p no:cacheprovider -q -rs`. Existing `test_arrangement_review_notification_http.py:73` skipped because `SCRUM64_NOTIFICATION_RUNTIME` was unset; this opt-in notification integration is unrelated to completion and is not claimed Green here |
| Full backend Ruff | Passed | `.venv/bin/ruff check --no-cache .` |
| Frontend full unit suite | **498 passed across 62 files, 7.71s** | Root-owned copied frontend, `npm test -- --run`; actual React rendering with prepared dependencies |
| Frontend lint / typecheck | Both passed | `npm run lint`; `npm run typecheck` |
| Full Chromium browser suite | **51 passed, 41.5s, one worker** | Root-owned copied frontend, `npx playwright test --reporter=list --workers=1`; configured production Webpack build succeeded before tests. Auth/APIs are controlled browser fixtures; native producer is verified separately |
| Story-focused backend / labels | **21 passed, 0 failed/skipped, 2 existing warnings, 0.52s**; all owned Python tests/harness Ruff pass | Vera command above; all new/changed automated test functions have directly adjacent stable AC-purpose comments and one technique; frontend unit and browser declarations have matching purpose comments |
| Protected user files | Both hashes unchanged | DoD `2727346251a767d8d8d325059cf133e269fcc47bf460857a81d020e2fef5f586`; SCRUM20 testcase `7c84b6fc2a59d4c90fa7a39c722bd246b7e245dcc7d1bdbee8b72300cf3d7fce` |

No extra standalone component test remains for retired AC5-N1. The final real-page refresh assertion passed first against the already-correct keyed integration; it is regression strengthening, not an additional product Red or production fix. End recording and automatic projection remain one browser journey. The initial whole-backend790/one-skip run was intermediate before the three infrastructure probes;793 is the current full total.

Root's completed-tool-response summary is preserved at `/tmp/scrum40-start-20261023/final-local-results-20261024.json`. It records exact commands, working directories, counts and tool-output references; it is **not a complete raw-log export**. The full broad outputs remain in root's execution transcript. Exact commands are `.venv/bin/ruff check --no-cache . && .venv/bin/python -m pytest -p no:cacheprovider -q -rs` in the event service, `npm test -- --run && npm run lint && npm run typecheck` in `/tmp/scrum40-ui-check-20261023/frontend` and `npx playwright test --reporter=list --workers=1` in that same owned copy. No later CI result is inferred from them.

### Independent audit strengthening — 24 October 2026

The final 11-file manifest and persistent recovery archive were independently checked: no missing files or byte drift. AC1–7 traceability and the direct-purpose-comment audit passed without rerunning unchanged suites. Source review also confirms organiser draft/update/submission/amendment inputs do not declare the authoritative end; the existing endpoint organiser403 check is retained. Additional organiser-input permutations were not added.

The same **AC1-H1** native fixture now includes an explicitly retained Rejected proposal with its original actor/reason/time and an acknowledged registration review with its original cause/version/actor/time. Event-scoped preconditions assert both controls exist before completion. The existing full before/after snapshot assertion is unchanged, so deletion, clearing or re-auditing of this prior evidence cannot pass vacuously. These rows are prepared storage controls, not proof that the fixture executed historical proposal/acknowledgement workflows.

Frozen candidate SHA `78d7eb4136809867fbac87f10030f9c2908f3f5e6ec8a1b32de71dc05f30e00f` passed **all seven existing NOTICE groups plus ROLLBACK** on root's fresh owned PostgreSQL16 with the genuine through0059 baseline and unchanged0063. Evidence: `/tmp/scrum40-start-20261023/audit-nonempty-controls-green.log`. The exact Green candidate was promoted to `database/verify_event_auto_completion.sql`. This is post-implementation oracle strengthening within the original forbidden-side-effect contract, with **no new case, production change or feature Red claim**. Earlier native `943c` and DST-strengthened `b165` Red/Green provenance remains archived; the previous durable `b165` is `/tmp/scrum40-start-20261023/vera/verify_event_auto_completion.pre-controls-b165.sql`.

The historical freeze description now accurately calls its old DST fixture an intended check; the later genuine-crossing correction and killed calendar-day mutant remain distinct evidence. The broad 793 backend / 498 frontend / 51 browser results above are unchanged-source historical executions for their respective code/tests, not newly rerun results from this two-control native strengthening. The affected native CI recipe passed on owned PostgreSQL16: all six SQL verifiers and one race group covering both real wait orderings (138→139 and 140→141), with the race taking 0.186s. Full raw evidence is `/tmp/scrum40-start-20261023/audit-native-ci-recipe.log`. This is a local CI-recipe rehearsal, not remote publication CI. Shared rollout remains unauthorised and unverified.
