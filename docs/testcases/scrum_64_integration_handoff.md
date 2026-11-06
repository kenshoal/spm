# SCRUM-64 combined safety integration handoff — updated 19 October 2026

**The bounded native integration checks pass on the latest pinned source.** On 19 October 2026, root reran unchanged runner 6861 against isolated published snapshot `e7888dcfdb19777722583b471b1d31e49da3f9c4`: seven methods/nine transaction executions passed, zero failures,0.835s. Four published workflow SQL verifiers also passed with ROLLBACK. A separate temporary Jaren AC6-X13 compatibility supplement proves exact and mixed-case duplicate UUID refusals with 22023, exact duplicate message and full protected-state equality. This adds no repository case or production TDD claim. The dated 79-case baseline stays 77 Green/two Planned; actual API/JWT, real authenticated browser and whole-story Done remain unproven. Earlier 4a5bc934 and 18 October results remain historical evidence, not current source pins.

Vera owns this test design, opt-in runner and catalogue. Devon owns SCRUM-64 production changes. Root owns isolated database preparation, execution records and external workflow/PR actions. No production function is replaced by a test implementation, no external story is implemented here and no shared database is changed.

## Historical 18 October sources, approval and pins

The user authorised preparing and executing the combined integration checks. Root freshly reviewed issue tracker SCRUM-64, SCRUM-60 and SCRUM-58 and supplied the human-agreed session contract (discussion2168/2194/2195) before implementation inspection. The requirements below are normalised approved outcomes, not quotations from a passing implementation.

- Current feature checkout: `a7ea77df6f1facd994ef335a9f3b90dfe7284c0b` on `feat/scrum-64-arrangement-review`; no new product code is introduced by these tests.
- Initial Jaren PR62 pin, retained as historical evidence: `289a814917dc8a9e4f874b43595285cf7dc68ef9`. Exact `0034_safety_review_decisions.sql` SHA256 `4099f1f7a0c60df682d076c0080e7911da05008495313126de0c9e3f79e817aa`; exact own verification SHA256 `9627a4da26058dd4fe3f8bfbd18abcf8763b4124f2157185176bbc786179c916`.
- Tate branch head: `bf31002c4928c6d953be89bb7f34e3f257fd883e`. Exact `0039_send_for_safety_review.sql` SHA256 `15c9bcc42cce8c8a948428f9be70ad0ab122501ea72b66dbcc0215ceb7b909a5`.
- 18 October Jaren PR62 pin: `135536cd1e0713052476ef0b17ce78c9c7542a0e`. Its 0034 is byte-identical to the initial pin. Exact `0044_safety_review_null_inputs.sql` SHA256 `aa2cb9b05e978358b4b634a715ca95fd27284dcf9f7c821132af3993c6301792`; updated `verify_safety_review_decisions.sql` SHA256 `879a3644a66540e28565bc0abc51659cc61d3e9645e8c774ad423b3c665ddf65`.
- 18 October pinned archive and manifest: `/tmp/scrum64-safety-integration-0044/pinned/`; initial archive: `/tmp/scrum64-safety-integration/pinned/`. These are exact external inputs, not adopted replacement migrations in this branch.
- Independent requirements oracle SHA256 `d70cfaaecf8ff0665974f53a389edd5690c41a9a1c0d4272c5f09fc0835c6c3c`, `/tmp/scrum64-combined-integration/requirements-oracle.md`, was frozen before reading callable wiring.

## Approved requirements

1. Only the current persisted `staff_roles.safety_officer` actor may decide. Wrong or removed capability refuses with P0003 and no protected writes. The actual API must separately derive the actor from verified identity; native checks do not prove that HTTP/JWT boundary.
2. Source state is Safety Review. Approve moves to Confirmed; changes_requested moves to Planning. A repeat from a stale/source state refuses P0004 without rewriting saved evidence.
3. A saved changes_requested decision retains its immutable full reason and explicit `{arrangement,id}` target payload. Exactly the named same-event targets receive safety_recheck flags using that actual saved decision UUID and reason. Empty targets with a nonblank reason produce zero flags.
4. Decision, permitted caller lifecycle/history, review flags and our required durable enqueue share one transaction. A malformed/foreign target or downstream required-write fault must leave no partial decision, status/history, flag or job. At the approved public saved-decision caller, malformed/foreign targets use 22023. The private helper retains P0002 for absent/cross-event target membership; its tests are unchanged. These are distinct boundary contracts, not interchangeable error expectations. Sequence advancement is not transactional state.
5. Outstanding review evidence, including retained work on a cancelled booking, must block consuming approval/handover. Ordinary incomplete readiness also blocks with P0005 and useful nonempty JSON-array issues. No unapproved issue item shape is guessed. Clearing is explicit; cancellation is not an automatic acknowledgement.
6. Separate coordinator-notice HTTP is post-commit best effort; this test does not falsely include it in the database transaction. SCRUM-58/60 own their actual gates, saved-caller workflows and lifecycle decisions.

## Bounded native integration matrix

Five core groups plus two public-gate diagnostics are run independently. The IDs map to the approved ACs; they are this separate integration layer, not seven extra baseline passes.

| ID | Requirement and purpose | Setup / input | Numbered action and expected result | Forbidden effects / plausible fault |
| --- | --- | --- | --- | --- |
| AC7-X5 | Connect the actual saved cause to complete exact review work. | Actual Safety Review event, current officer, linked booking/reservation and full reason. | 1. Call actual decide_safety_review changes_requested. 2. Read real saved row. 3. Require exactly two flags/jobs with its UUID/reason. 4. Require Planning and actual officer history. | No synthetic cause, unrelated target or source-state rewrite; a primitive that saves but never invokes our helper fails. |
| AC7-N1 | Native current-role refusal with a positive control; API authorisation stays pending. | Wrong venue-only actor, officer removed from staff_roles then restored. | 1. Require wrong/removed P0003 with full state equality. 2. Restore role. 3. Require successful empty-target decision and zero new flags/jobs. | No stale role grant or unauthorised decision. No JWT/route/forged-actor claim. |
| AC7-N3 | Wrong-event target must roll back the actual saved caller. | Valid first booking plus reservation belonging to another event. | 1. Call actual changes_requested. 2. Require caller 22023. 3. Compare decision/event/history/reviews/jobs/resources. | No accepted foreign target or partially saved caller; primitive shape-only validation fails. |
| AC7-X6 | Required enqueue failure must roll back actual decision and lifecycle. | Two valid targets; transaction-local test trigger faults the second real job INSERT. | 1. Call actual decision. 2. Require the specific23514 and second attempt. 3. Compare full protected state. | No decision/status/history/first flag/job left behind; not reaching the enqueue seam fails. |
| AC7-X7 | Actual caller stale replay differs from helper idempotency. | Successful empty-target changes_requested has moved event to Planning. | 1. Snapshot saved decision/history. 2. Attempt another decision. 3. Require P0004 and exact equality. | No duplicate or overwritten decision; no claim later revisions are implemented. |
| AC5-X12 | Actual approval must consume ordinary readiness and outstanding facts. | Separate ordinary-incomplete event and otherwise-ready event with retained review on cancelled booking. | 1. Call actual approve in each independent subcase. 2. Require P0005/useful nonempty JSON array. 3. Require unchanged state. | No Confirmed result while incomplete/review work remains. No invented readiness helper schema. |
| AC5-X13 | Actual coordinator handover must retain its ordinary refusal and consume review facts. | Planning event without a venue; separately otherwise-ready Planning event with retained cancelled-booking review. | 1. Call actual public handover as service_role. 2. Require P0005/useful nonempty JSON array and unchanged state. | No Safety Review result with outstanding facts. An earlier privilege failure does not establish this predicate. |

The actual public interfaces are `decide_safety_review(uuid,uuid,text,text,jsonb)` and `send_event_request_for_safety_review(uuid,varchar)`. The proposed `private.event_readiness_issues(uuid)` is not published as an agreed capability or issue-shape contract; it is not implemented or bootstrapped by this test. The public diagnostics remain executable without inventing that private function.

## Historical 18 October runner and preparation

**Historical failing-runner record:** the 18 October local-only artifact was `database/tests/test_safety_arrangement_integration.py`, SHA256 `5de75f8ac994e5ba210bfc003ace27d0d3b400c02984ab7e09a49c69d49c8b59`. Its only refactor adds `--scope decision|handover|all` (default all) and limits the Tate capability prerequisite to the handover method. All seven test method bodies and the four shared business assertion/fixture helpers are AST-identical to frozen `78ad48f8926f703fd86724d3086f9837f0ab43e6ab92e8c8f96210744f33a76e`. The original remains archived at `/tmp/scrum64-combined-integration/test_safety_arrangement_integration.py` and `/tmp/scrum64-safety-integration-0044/required-integration-original-78ad.py`. This is test-infrastructure refactoring, not feature TDD or weakened expectations. Compilation, focused Ruff, CLI help and conditional capability construction passed.

Use a fresh explicitly owned disposable PostgreSQL16 cluster. Follow the scope-aware pinned recipe in [database/README.md](../../database/README.md#pinned-external-safety-decision-compatibility-fixture), with a reviewed offline archive and a second disposable Auth-double identity for the upstream verifier. `decision` loads 32 supplemental files (the independent 30 plus exact Jaren 0034 and 0044), needs no Tate file/function and needs no extra venue SELECT. `handover`/`all` load 33 files including exact Tate 0039, then require the separately evidenced local service-role venue-read prerequisite below. Commit 0041's enum addition before 0042. The runner expects a preloaded DSN; it contains no duplicate loader, product stub or replacement helper. Each transaction ends in ROLLBACK or connection-abort rollback. No shared Auth user/role is created.

Historical 18 October decision-only command (root executed the byte-identical frozen `/tmp/scrum64-safety-integration-0044/` runner copy):

```sh
python3 database/tests/test_safety_arrangement_integration.py \
  --dsn postgresql://postgres@127.0.0.1/scrum48_64_nullfix_decision \
  --psql /tmp/scrum64-safety-integration-0044/decision/bin/psql \
  --disposable --scope decision
```

For full or handover-only diagnostics, use the combined fixture and matching scope:

```sh
python3 database/tests/test_safety_arrangement_integration.py \
  --dsn postgresql://postgres@127.0.0.1/scrum48_64_nullfix_combined \
  --psql /tmp/scrum64-safety-integration-0044/combined/bin/psql \
  --disposable --scope all
# Same combined DSN/wrapper with --scope handover runs only the handover method.
```

Both scope and database guards fail explicitly on invalid inputs; there are no capability skips. At that 18 October point, the runner stayed outside ordinary backend CI discovery and was retained untracked because its required seams were Red. The previous actual 32-schema baseline passed all ten native review scripts and the three-method concurrency harness (`/tmp/scrum64-safety-integration/combined-schema-regression.log`). Exact old primitive verification passed with ROLLBACK (`jaren-primitive-baseline.log`); it used an absent target UUID because the primitive did not enforce membership. That18October upstream verifier still had that fixture limitation: its owner must use real linked targets when wiring the helper. Primitive passes never establish the missing saved-caller integration.

## First execution — actual observed results

Root ran the frozen runner on18October2026; Vera independently read `/tmp/scrum64-safety-integration/required-integration-first.log`. Seven methods ran in0.887s. Unittest reports seven failures because approval and handover each contain two subcases. That aggregate consists of **five meaningful required-seam assertion failures across four methods, two passing native methods and two earlier permission-blocked handover subcases**.

| ID | Actual result | Classification | What was reached / not reached |
| --- | --- | --- | --- |
| AC7-X5 | Actual saved decision succeeded inside the test transaction, but zero versus two required flags. | Failed: missing actual-caller/helper connection | Saved actor/reason/targets control passed; subsequent flag-count ASSERT failed. Its default PLpgSQL ASSERT SQLSTATE is P0004, not a caller stale refusal. Later enqueue/history assertions were not reached. |
| AC7-N1 | Wrong and removed native role refused P0003 with equal state; restored current role/empty-target control passed. | Passed: native role only | Does not close the planned API/JWT authorisation case. |
| AC7-N3 | Actual primitive accepted the other-event reservation; expected P0002 was absent. | Failed: target ownership connection missing | Test raised explicit P9902 after unexpected success; this is not a missing routine/setup failure. Caller rollback assertions after the required refusal were not reached. |
| AC7-X6 | Actual primitive did not raise any review/job, so the expected second-job fault was never reached. | Failed: required transaction connection missing | Explicit P9903 after unexpected success. This does not prove a partial-write bug in our helper; its existing atomicity tests remain Green. |
| AC7-X7 | First empty-target decision saved, subsequent stale action refused P0004 and preserved all evidence. | Passed: native caller stale guard | No actual HTTP/JWT, new-review replay or future revision workflow claim. |
| AC5-X12 ordinary | Actual approval accepted ordinary incomplete readiness. | Failed: approval readiness integration missing | Explicit P9905 after success instead of P0005; no guessed JSON-item assertion. |
| AC5-X12 cancelled-review | Actual approval accepted an outstanding review on a cancelled booking despite an approved sibling/equipment-ready control. | Failed: approval shared-review integration missing | Required P0005 absent; source explicitly documents the gate is not yet connected. |
| AC5-X13 both subcases | service_role hit42501 permission denied for table venues before either intended readiness assertion. | Blocked at prerequisite, not meaningful flag-gate Red | Pinned0039 is SECURITY INVOKER. Current published0016 has no service_role venues SELECT grant; owner-run source tests do not prove this call path. This was the initial fixture/platform ACL discrepancy; its verified-live local precondition and unchanged-oracle rerun are recorded below, not retrospectively relabelled as product Red. |

All effects were contained in rolled-back local fixture transactions. Successful primitive returns in these diagnostics do not mean any shared or lasting lifecycle transition occurred. Proposed readiness-helper publication/issue shape remains separately Blocked. The entire consuming-gate behaviour must not be labelled unexecutable: actual approval was executed and failed meaningfully; handover was attempted but stopped at its earlier permission boundary.

## Initial unchanged-oracle execution — permission prerequisite evidenced

Root queried only live Supabase metadata, read-only: `has_table_privilege('service_role','public.venues','SELECT')` returned true. No shared role, policy, account or data was changed. Evidence `/tmp/scrum64-safety-integration/live-venue-read-precondition.json` records that narrow table capability, not real authenticated execution or a complete security audit. The vanilla PostgreSQL fixture lacked that platform ACL; the initial42501 is therefore fixture-blocked evidence, not a demonstrated Tate production bug.

Devon supplied only `/tmp/scrum64-safety-integration/local-venue-read-precondition.sql`, SHA256 `4eafc51e7a40f66bdf96b2e637c68e621bd09f3fd02cf896c1952d39c1146724`. It refuses a non-scrum48_* database and grants only service_role SELECT on public.venues on the owned local fixture. It is not a repository migration/bootstrap, browser grant, RLS change, SECURITY DEFINER substitution or product implementation. The test oracle/runner did not change (still78ad48...). The actual shared capability justified this environment-only prerequisite; it was not guessed merely to get a different test result.

Root then reran the exact same command and frozen runner. Vera independently read `/tmp/scrum64-safety-integration/required-integration-final.log` and matched the unchanged hash. Seven methods ran in0.852s. Unittest reported six failures: three core missing-connection assertions, two approval subcases and the cancelled-review handover subcase. Two complete methods pass (native wrong/removed-role and stale) and the ordinary handover subcase also passes: **three passing executions and six failing executions out of nine**. No 42501 remains. There are no passing skips, mocked gates or test replacement functions.

| ID / subcase | Initial post-prerequisite result | Required-seam classification |
| --- | --- | --- |
| AC7-X5 | Actual saved changes_requested decision has zero required target flags; post-return ASSERT fails. | Failed: caller/helper connection not implemented; not a native caller P0004 refusal. |
| AC7-N1 | Wrong/removed staff_roles capability P0003 with no writes; restored empty-target control succeeds. | Passed native proof only; planned full API/JWT case remains open. |
| AC7-N3 | Actual caller accepts cross-event target rather than required P0002. | Failed: ownership connection not implemented. |
| AC7-X6 | Actual caller never reaches the required second enqueue/fault seam. | Failed: full saved decision/lifecycle/flags/jobs atomic connection not implemented; partial-write rollback assertion not reached. |
| AC7-X7 | Actual stale repeat P0004 preserves the original saved payload and state. | Passed native proof only. |
| AC5-X12 ordinary | Actual approval accepts ordinary incompleteness instead of P0005. | Failed: consuming readiness connection not implemented. |
| AC5-X12 cancelled-review | Actual approval accepts retained cancelled-booking review work instead of P0005. | Failed: consuming outstanding-fact connection not implemented. |
| AC5-X13 ordinary | Public handover refuses P0005 with useful nonempty JSON issues and unchanged protected state. | Passed after evidenced environment prerequisite; no invented issue-item shape. |
| AC5-X13 cancelled-review | Public handover accepts retained outstanding review work instead of P0005. | Failed: handover/shared-review connection not implemented. |

These are executable public capabilities returning the wrong required result, not an entirely unexecutable gate. Their omitted integrations are external-owner work explicitly acknowledged in the pinned source. Our original native helper/shared-reader/enqueue regressions remain Green on the genuine combined schema. No failing execution identifies a defect requiring a SCRUM-64 production fix. This does not claim future caller atomicity, approval correctness, real JWT/API identity binding or integrated-story Done.


## Published 0044 and independent decision scope — historical 18 October 2026

Root prepared two fresh owned PostgreSQL16 databases and ran exact published files. Vera independently checked all four pinned hashes and raw execution logs. Before 0044, updated upstream verifier 879a... failed at NULL decision: expected 22023, actual 23502 from the decision NOT NULL constraint (`null-validation-red.log`); later added NULL cases were not reached. After exact 0044 applied, the same verifier passed with ROLLBACK on both combined and decision-only fixtures (`combined-null-validation-green.log`, `decision-null-validation-green.log`). It checks NULL decision/targets, missing target keys and a null array member with exact 22023, then original status and zero saved decisions. Caught failing subtransactions roll back their writes. This is sufficient targeted upstream regression evidence; no duplicate NULL tests or new catalogue cases were added. It does not establish full saved-caller/helper atomicity, current JWT identity or complete invalid-input coverage.

| Executed runner / scope | Schema | Methods / transaction executions | Actual passing / failing executions | Raw log and duration |
| --- | --- | --- | --- | --- |
| Original unchanged 78ad / all | Combined 33, with evidenced local venue-read prerequisite | 7 / 9 | 3 / 6 | `original-full-serial.log`,0.927s |
| Scoped 5de75 / all | Same combined 33 | 7 / 9 | 3 / 6 | `scoped-full.log`,0.841s |
| Scoped 5de75 / decision | Independent 32, no Tate 0039 or venue-read grant | 6 / 7 | 2 / 5 | `decision-independent.log`,0.665s |
| Scoped 5de75 / handover | Combined 33, with local venue-read prerequisite | 1 / 2 | 1 / 1 | `handover-only.log`,0.204s |

All logs in this section are under `/tmp/scrum64-safety-integration-0044/`. The full runs contain the identical six omission assertions detailed in the table above: three missing caller connections, two approval subcases and cancelled-review handover. Decision scope excludes only handover, so its five failures remain visible without a Tate dependency. Its two fully passing methods are native wrong/removed-role and stale; its four other methods produce five failures because approval has two subcases. Handover's ordinary subcase passes and cancelled-review subcase fails. No 42501, missing routine, fake gate or passing skip occurs in these current runs.

Decision independence is an actual runtime proof, not only a command label: `decision-independence-proof.log` returns `t|t|f` for **Tate callable absent**, **decision callable present** and **service_role venues SELECT present**, respectively. The first two propositions are true and the third is false. Thus current decision diagnostics need neither Tate's migration nor the additional local venue-read privilege. The scoped runner does not fabricate a public readiness function.

On the new combined 33 schema, all ten unchanged native review SQL scripts passed with ROLLBACK (`review-regression-after44.log`) and the three-method native lock harness passed in 4.489s (`concurrency-after44.log`). Both child-domain subcases report no caller child wait and the expected writer event wait. These are non-additive regression checks, not new integration Green records. Root also reset the decision database and reproduced Devon's exact scope-aware README recipe using an archive containing only the three Jaren inputs, with no Tate 0039 file: 32-file setup and updated verifier passed (`readme-decision-only-reproduction.log`), then the same scoped decision assertions again gave 6 methods/7 transactions, 2 passing/5 failing in 0.665s (`decision-from-readme.log`). This is additional setup reproduction, not new cases. No SCRUM-64 runtime fix was justified by the observed failures. The published NULL fix is locally reproduced; the required caller/gate connections remain **Not done**, real API/JWT checks remain unverified and the unpublished shared ordinary-readiness capability remains Blocked.


## Earlier 19 October 2026 — public-caller contract reconciliation on 4a5bc934

The requester explicitly approved changing the public-caller cross-event expectation to 22023. The private helper's absent/cross-eventP0002 contract remains unchanged. The source used for this execution is published snapshot `4a5bc9349ecb91d260454b6a9db77beea15e5793`, retained at `/tmp/scrum64-approval47-verification-20261019/snapshot`. Its0047 migration SHA256 is `c0ab8732be85a2c8226e7ae5ab2156f89efb1430e4c479d319773c2817435993`. This snapshot is an isolated verification input, not a claim it was merged into the SCRUM-64 checkout.

Before changing the test, root reconstructed the native setup and reproduced the frozen 5de75 runner: seven methods/nine transactions, eight passing executions and one contract mismatch,0.822s (`before-full.log`). The actual public caller refused the cross-event target with 22023 and message `safety decision target is not part of this event`; the old test expected P0002, so its later snapshot equality was not reached. This was not an accepted foreign target or a demonstrated production regression.

Vera archived the original 5de75 runner at `/tmp/scrum64-caller-contract-20261019/runner-before-5de75.py`, then changed exactly two literals inside `test_cross_event_target_rolls_back_actual_caller`: its caught SQLSTATE and expected-code explanation, P0002→22023. Its AC7-N3 purpose comment, valid-first/foreign-second fixture, full protected-state equality and every other function are unchanged. AST comparison and literal diff establish this scope. Private-helper tests were not edited. The Green-executed runner `database/tests/test_safety_arrangement_integration.py` SHA256 was `add2030f8805e2444e3cc1d6749b5d89222c924e8c497a12d054b92de203d3b3`; original 5de75/78ad archives preserve the earlier evidence. No new test or production change was made.

Root then executed the corrected application runner on the same published setup. Vera independently read `/tmp/scrum64-caller-contract-20261019/after-full.log`: **seven methods, nine transaction executions, nine passing, zero failures,0.837s**. The cross-event refusal now catches the approved22023 and reaches/passes the full unchanged decision/event/history/flags/jobs/resources snapshot assertion. The other native groups pass: actual saved UUID/reason/target flags and enqueue, current/removed officer role, exact injected second-enqueue rollback, stale replay, ordinary/outstanding approval refusal and ordinary/cancelled-review handover refusal. These local checks do not prove normal HTTP identity binding, real JWT/browser interaction or every concurrent lifecycle ordering.

Exact Green command executed by root (the before run used the identical arguments with `/tmp/scrum64-caller-contract-20261019/before.py`):

```sh
python3 /Users/tionghengrui/Documents/SCH/Y2S2/SPM/Project/spm/database/tests/test_safety_arrangement_integration.py \
  --dsn postgresql://postgres@127.0.0.1/scrum48_64_caller_contract47 \
  --psql /tmp/scrum64-caller-contract-20261019/bin/psql \
  --disposable --scope all
```

| Group | Latest bounded native result |
| --- | --- |
| AC7-X5 | Actual saved decision owns exact target review flags/jobs, reason and permitted lifecycle audit. Pass. |
| AC7-N1 | Native current/removed/wrong persisted officer checks and empty-target control. Pass; full API/JWT case remains Planned. |
| AC7-N3 | Public caller 22023 plus full protected-state equality. Pass; private helper P0002 unchanged. |
| AC7-X6 | Actual caller reaches the specific second-enqueue 23514 fault and preserves all protected state. Pass. |
| AC7-X7 | Actual stale P0004 preserves saved evidence and state. Pass. |
| AC5-X12 | Both ordinary-unready and retained cancelled-review approval refusals P0005 with useful JSON issues and no writes. Pass. |
| AC5-X13 | Both ordinary and retained cancelled-review handover refusals P0005 with useful JSON issues and no writes. Pass. |

**Publication preparation — 19 October 2026:** the user authorised publishing the Green opt-in runner. Its header now describes the portable external-stack prerequisite instead of a local/uncommitted restriction. Publication source SHA256 is `6861e420fec648561ea7bfb6d0dd46539cb22740c828bdf298c442b8ff124a23`. The Python AST excluding the module docstring is identical to the nine-pass add2030 source; all seven labelled test bodies and every assertion are unchanged. No test was added and no execution count changed. This is documentation-only preparation, not a new native rerun or a claim of passing against the base feature checkout alone. The opt-in runner requires the reviewed external safety/readiness stack through 0047; current nine-pass evidence remains the exact 4a5bc934 snapshot above. Root owns publication, CI and live verification; their outcomes must be recorded separately.

The six draft integration IDs remain this separate layer, not extra baseline 79 cases. This native result supersedes earlier missing-connection/blocked-helper observations only for the exact published snapshot and checks executed. The earlier results remain dated source evidence. Root owns setup/execution, cleanup and the separate execution-handoff record; Vera owns this test correction/evidence review. No shared database, production function, merge, commit or push was changed by this test task.


## Latest 19 October 2026 — e7888dc refresh and duplicate no-write supplement

The user authorised refreshing the published Jaren source and verifying duplicate refusal without changing SCRUM-64 production or the committed runner. The exact snapshot is `e7888dcfdb19777722583b471b1d31e49da3f9c4`, retained at `/tmp/scrum64-e7888dc-verification-20261019/snapshot`. Its relevant SHA256 fingerprints are:

| Source | SHA256 |
| --- | --- |
| `database/migrations/0047_safety_review_approval_readiness.sql` | `647d8e67e13b7307144438473bc298167f49c67b40c0d8c20b82dde435ff0507` |
| `database/verify_safety_review_approval_readiness.sql` | `44455ab8f6848f6abbc9c3877225568614a446c3c1a0234a7cff8eb00a63aadc` |
| `database/verify_safety_review_decisions.sql` | `401938449777cc45827062cf14f08434cbd0eddd82c80b40caee814b3d6f1070` |
| `database/verify_safety_review_arrangement_reviews.sql` | `8c7602f5366229bbc0ae38c02a5f818cc32484a4c82d58ace1bbea8e91e5000c` |
| `database/verify_shared_event_readiness.sql` | `55803187c95990062be3bda03bb45aaa665d05c61bd0293908984bcf85f6059d` |

Root executed against owned PostgreSQL16. Vera independently read the raw logs in `/tmp/scrum64-e7888dc-verification-20261019/`:

| Check | Observed result | Evidence |
| --- | --- | --- |
| Four exact workflow SQL verifiers above | All pass with ROLLBACK. | `verify_safety_review_{decisions,arrangement_reviews,approval_readiness}.log`, `verify_shared_event_readiness.log` |
| Unchanged committed runner 6861 | Seven methods/nine transaction executions, nine pass/zero fail,0.835s. | `combined-integration.log` |
| Existing SCRUM-64 review SQL checks | Ten scripts pass with ROLLBACK. | `review-regression.log` |
| Existing review lock harness | Three methods pass,4.487s. | `review-locks.log` |
| Published handover race harness | Five methods pass,10.267s. | `handover-races.log` |
| Jaren AC6-X13 compatibility supplement | Two diagnostic executions pass: exact duplicate and mixed-case UUID identity, exact 22023/message and full protected-state equality. | `duplicate-no-write.log` |

The upstream AC6-X13 already checks duplicate 22023 and zero saved decisions/flags. Its randomly generated UUID is not a guaranteed alphabetic case-folding fixture, and it does not explicitly compare status/history/jobs/resources. The temporary supplement therefore imports the frozen committed runner 6861, uses its actual linked fixtures, native service-role call and complete `integration_state()` snapshot, and substitutes only the in-process booking fixture UUID `64abcdef-0123-4abc-8def-0123456789ab`. The first transaction repeats that literal exactly; the second uses its uppercase representation. Both require SQLSTATE 22023 and exact message `duplicate safety decision target`, then compare the entire protected-state snapshot. This distinguishes duplicate detection from an unrelated 22023, accepted duplicate or partial-write fault. No test-side production function or copied business rule is supplied.

The diagnostic was frozen before execution: temporary `/tmp/scrum64-e7888dc-verification-20261019/vera/verify_duplicate_target_no_write.py`, SHA256 `3c854c46b64611081765c746d2cbfa501a86ec3c393e1283c191a8bcc6a55269`. It passed Python compilation and focused Ruff. The committed runner remains byte-identical SHA256 `6861e420fec648561ea7bfb6d0dd46539cb22740c828bdf298c442b8ff124a23`; no new repository testcase, matrix ID or baseline count was added. These are two non-additive compatibility executions under Jaren's existing AC6-X13, not extra SCRUM-64 cases, a newly authored production fix or a retroactive Red.

Root executed this exact temporary command (the portable equivalent follows):

```sh
python3 /tmp/scrum64-e7888dc-verification-20261019/vera/verify_duplicate_target_no_write.py \
  --runner /Users/tionghengrui/Documents/SCH/Y2S2/SPM/Project/spm/database/tests/test_safety_arrangement_integration.py \
  --dsn postgresql://postgres@127.0.0.1/scrum48_64_e7888dc \
  --psql /tmp/scrum64-e7888dc-verification-20261019/bin/psql --disposable
```

For reproduction, prepare the reviewed external stack through 0047 using the current README recipe, then save the exact temporary source below outside the repository. Run it with the real committed runner path, an owned loopback `scrum48_*` DSN and the matching psql command. This source is recorded here because its executed `/tmp` path is an ephemeral diagnostic artifact, not a repository test file:

```sh
python3 /tmp/verify_duplicate_target_no_write.py \
  --runner "$SCRUM64_REPO/database/tests/test_safety_arrangement_integration.py" \
  --dsn "$SCRUM64_TEST_DSN" --psql "$SCRUM64_PSQL" --disposable
```

<details>
<summary>Exact frozen temporary AC6-X13 supplement source</summary>

```python
"""Temporary Jaren AC6-X13 compatibility supplement; no production substitute.

Reuse the committed opt-in runner's real linked fixtures and full protected-state
snapshot. Both independent transactions roll back. This adds no repository case.
"""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from urllib.parse import urlparse

EXPECTED_RUNNER_SHA = "6861e420fec648561ea7bfb6d0dd46539cb22740c828bdf298c442b8ff124a23"
LETTER_BOOKING = "64abcdef-0123-4abc-8def-0123456789ab"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner", type=Path, required=True)
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--psql", default="psql")
    parser.add_argument("--disposable", action="store_true")
    args = parser.parse_args()
    parsed = urlparse(args.dsn)
    if (
        not args.disposable
        or parsed.scheme not in ("postgres", "postgresql")
        or parsed.hostname not in ("127.0.0.1", "localhost", "::1")
        or not parsed.path.removeprefix("/").startswith("scrum48_")
    ):
        parser.error("Only an explicitly disposable loopback scrum48_* database is allowed")
    if hashlib.sha256(args.runner.read_bytes()).hexdigest() != EXPECTED_RUNNER_SHA:
        parser.error("Committed fixture/snapshot source does not match frozen runner6861")
    spec = importlib.util.spec_from_file_location("scrum64_frozen_native", args.runner)
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    runner.DSN, runner.PSQL = args.dsn, args.psql
    # Only this process's test fixture identity changes; no repository source changes.
    runner.BOOKING = LETTER_BOOKING
    probe = runner.CombinedSafetyIntegration("test_cross_event_target_rolls_back_actual_caller")
    assert LETTER_BOOKING != LETTER_BOOKING.upper()
    for case, second_id in (
        ("exact-duplicate", LETTER_BOOKING),
        ("mixed-case-same-UUID", LETTER_BOOKING.upper()),
    ):
        targets = json.dumps([
            {"arrangement": "venue_booking", "id": LETTER_BOOKING},
            {"arrangement": "venue_booking", "id": second_id},
        ])
        # Jaren AC6-X13 (negative): duplicate UUID identity must refuse before any protected state change.
        probe.native(f"""DO $case$
        DECLARE before_state jsonb:=pg_temp.integration_state(); actual_message text;
        BEGIN
          ASSERT EXISTS(SELECT 1 FROM public.venue_booking_requests
            WHERE id='{LETTER_BOOKING}' AND event_request_id='{runner.E1}'),
            'AC6-X13 supplement: linked alphabetic UUID fixture missing';
          ASSERT '{LETTER_BOOKING}'::uuid='{second_id}'::uuid,
            'AC6-X13 supplement: input does not represent the same UUID';
          BEGIN
            SET LOCAL ROLE service_role;
            PERFORM {runner.decide(targets=targets)};
            RESET ROLE;
            RAISE EXCEPTION 'AC6-X13 supplement: duplicate target accepted' USING ERRCODE='P9906';
          EXCEPTION WHEN SQLSTATE '22023' THEN
            GET STACKED DIAGNOSTICS actual_message=MESSAGE_TEXT;
            ASSERT actual_message='duplicate safety decision target',
              'AC6-X13 supplement: unrelated22023 caught: ' || actual_message;
          END;
          ASSERT pg_temp.integration_state()=before_state,
            'AC6-X13 supplement: refusal changed protected decision/event/history/flags/jobs/resources';
          RAISE NOTICE 'INTEGRATION ASSERTIONS PASSED AC6-X13 supplement {case}';
        END $case$;""")
        print(f"PASS Jaren AC6-X13 supplement {case}:22023/exact message/full snapshot unchanged; ROLLBACK")
    print("PASS:2 compatibility executions; no new repository case or realJWT claim")


if __name__ == "__main__":
    main()
```

</details>

All test transactions roll back; the first reserved-event cleanup check reports zero retained case events (`first-fixture-cleanup.log`). Root also reproduced the updated37-file README setup from a second empty owned database, then reran all four workflow SQL verifiers and the nine integration transactions successfully (`readme-setup.log`, `readme-upstream-workflow.log`, `readme-combined-integration.log`; runner0.826s). An initial transient local PostgreSQL TCP-readiness failure was retained as startup evidence, not product Red; the same setup passed after TCP readiness. This is separate reproducibility evidence, not new cases. Root owns final cleanup, PR/CI and live evidence. The four workflow verifiers, nine runner transactions, other regression methods and two supplementary executions are different non-additive units. The 79-case baseline and two real-Auth Planned items remain unchanged. No real JWT, shared deployment or full lifecycle-concurrency guarantee follows from these native passes.

## Historical 18 October owner actions — superseded by latest native result

- **Jaren/SCRUM-60:** wire the saved decision UUID/full reason/targets to our private helper inside the real transaction, propagate whole-batch ownership failures and required enqueue failure, and add actual approval refusal using shared outstanding facts plus the agreed ordinary readiness consumer. Preserve current officer/stale checks. Published 0044 now passes its exact upstream NULL-input regression locally; preserve that fix while implementing the separate caller/gate connections.
- **Tate/SCRUM-58:** publish the actual shared ordinary-readiness capability/issue contract and connect the public handover to outstanding review facts. The native environment prerequisite is now evidenced; preserve the distinction between that resolved local ACL mismatch and the still-failing shared-review predicate.
- **SCRUM-64:** the ten existing native checks and three lock tests pass on the genuine combined schema. No failing assertion currently identifies a defect in our private helper, shared facts reader or durable enqueue. At that time, implementing external workflows merely to make the local runner Green was outside the SCRUM-64 increment.
- **Vera/root:** the 18 October handoff retained the failing scoped runner and 78ad archive locally for owner follow-up. That dated restriction is superseded by the 19 October nine-pass result and explicit publication authorisation above. Actual API identity/JWT and real authenticated browser evidence remain separate; the previous 79-case baseline does not close these integration seams.

### Five-question review

Every group has an approved AC/outcome source above, concrete rolled-back setup/action/expected result, a stated plausible wrong implementation and literal nonempty/positive controls. The independent oracle preceded callable inspection; responses were not copied into expectations. Native persisted rows, exact UUID/reason identity and global/unrelated snapshots prevent vacuous passing mocks. Specific error classes and injected23514 distinguish intended refusals from setup faults. Published capability checks fail explicitly instead of silently skipping. Execution separates actual failures, native passes and permission-blocked predicates; no human approval, actual Auth, CI or integrated-story Done claim is fabricated.
