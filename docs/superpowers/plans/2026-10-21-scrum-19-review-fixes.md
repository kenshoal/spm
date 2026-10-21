# SCRUM-19 Review-Fix Plan: Hardening Increment 1 Before the PR

Drafted 21 October 2026 by Claude (Cowork) for Yang Xue. **Status: draft, needs approval of §1 (the test-restoration sign-off) before commit R1.**
Source: the code review of commits `8aa0a73`…`79835b3` on `feat/scrum-19-assign-technical-support` (21 Oct). Runs **before** increment 2 (`2026-10-21-scrum-19-increment-2.md`, commit 10a onwards), because R4 changes migration `0052`, and that stays cheap only while `0052` has not been applied to shared dev.

**Test rule for this plan:** no test is changed to make code pass. A test changes only in two cases: (a) **restoring** a test exactly as it was in its Red commit, which needs your sign-off (plan §6 of the increment-1 plan), or (b) **adding** a new labelled case. Each fix below says which, if either, it needs.

---

## 1. Sign-off needed

| Item | What changes in a test | Why |
| --- | --- | --- |
| S1 | Restore `test_notification_failure_keeps_the_assignment` (AC5-N2) and `RecordingNotificationClient.fail` to their `b821d54` versions | `4d1488a` weakened the case to fit the code: it now uses the real client, which swallows `httpx.HTTPError`, so the service's own failure handling is never tested. This puts the original oracle back. Nothing new is invented |

Everything else in this plan is production code, new tests, or documentation.

## 2. Fixes

| # | Finding (review #) | Fix | Tests | Severity |
| --- | --- | --- | --- | --- |
| R1 | Notification exception escapes as a 500 after the assignment commits (#1) | `technical_support_service.py`: wrap `notify_technical_support_assigned(...)` in `try/except Exception`, and `logger.warning(..., exc_info=True)` naming the staff, requirement and event ids. Return the assignment either way. Fix the comment that says "NotificationClient never raises" | S1 restoration (Red: 500 ≠ 201), then Green | High |
| R2 | Business rules are only proven by a manual database run (#2) | Two parts: **(a)** the service calls `ensure_support_allowed(event.status)` in `record_requirement` and `assign` after the coordinator pre-check, so the rules module runs in production, refuses early, and the DB function stays the authoritative recheck. **(b)** CI job `database-verify` in `backend-ci.yml`: a `postgres:16` service container; `bootstrap_safety_review.py --disposable --through 0052_technical_support_assignments.sql`; then `psql -v ON_ERROR_STOP=1 -f database/verify_technical_support_assignments.sql`. The race script stays manual (two sessions plus committed fixtures) | (a) existing AC1-P4…P10 / AC2-P4…P10 API tests already cover it. The fake raises the same refusal, so they stay green with no edit. Add **AC2-N8 (A)**: a refused status makes **no** RPC call, recorded with a new call counter on a subclass of the fake defined in a **new** test file. (b) CI evidence goes into the execution record | High |
| R3 | "Requirement not found" is told apart from "event not found" by matching message text (#3) | Changing the errcode to P0006 would break the AC2-N1 assertions in the DB verifier and the fake (`P0002`), which would mean editing tests, so it is **deferred** (§4). Mitigation now: move both message strings into module constants (`REQUIREMENT_NOT_FOUND_REASON` in the repository) and compare against those. In the DB verifier's new block (R4), add **AC2-N9 (D)**: `SQLERRM` for the wrong-event requirement equals exactly `'technical support requirement not found'`, so rewording the SQL fails CI instead of silently changing the 404 code | AC2-N9 new (D) | Medium |
| R4 | Nothing in the database stops `assignments.event_request_id` disagreeing with its requirement's event (#4) | Edit `0052` in place (not on shared dev yet, so no new migration). Add `CONSTRAINT technical_support_requirements_id_event_key UNIQUE (id, event_request_id)` on requirements, and replace the single `requirement_id` FK on assignments with `CONSTRAINT technical_support_assignments_requirement_event_fkey FOREIGN KEY (requirement_id, event_request_id) REFERENCES public.technical_support_requirements (id, event_request_id) ON DELETE CASCADE`. Both are inline in `CREATE TABLE IF NOT EXISTS`, so the file stays safe to re-run on a fresh database. Re-run the disposable cluster from scratch | New **AC2-X7 (D)**: a direct `service_role` insert of `(REQ_OTHER, EVENT, …)` raises `23503`. Existing AC2-N3's direct insert uses a matching pair, so it still passes unchanged | Medium |
| R5 | Two different `SupportNotAllowedError` classes (#5) | Give the rules class `code = "support_not_allowed"`. Delete the service's copy and re-export the rules class from `technical_support_service.py`, so `main.py`'s import still works. R2(a) and `_map_refusal` then raise the same class | Covered by existing API 409 tests | Low |
| R6 | `assert` used for control flow (#6) | Replace with `return error` and a comment: any other errcode is an unexpected database refusal and stays a 502 | Existing AC2-N7 | Low |
| R7 | Repository and error-handler duplication (#9) | `_rpc(name, json, single=True)` helper in the repository used by `record_requirement`, `assign` and `list_candidates`. Base exception `TechnicalSupportError(code, status)` in the service, with one `main.py` handler replacing four. Behaviour identical | Existing R and A tests; **no test edits** | Low |
| R8 | The notification is best-effort and lost if notificationService is down (#10) | No code change. State it in the PR description and the service README: delivery matches SCRUM-14's best-effort pattern, not the submission outbox | — | Note |

Not in this plan: the skill-vocabulary duplication (#7) and `technical_support_skills.user_id` having no FK (#8). Both are tied to a future "maintain staff skills" story. Record them in the catalogue's assumptions.

## 3. Commit sequence

| # | Commit | Files | Done when |
| --- | --- | --- | --- |
| R0 | `docs(scrum-19): record review findings and new test rows` | this plan; `scrum_19_testcases.md`: add AC2-N8, AC2-N9, AC2-X7; a "Review corrections" note listing the three test edits made in `4d1488a` and `53b2bcb`, and S1 | You approve S1 |
| R1a | `test(scrum-19): restore the AC5-N2 failing-notifier oracle` | `tests/test_technical_support_api.py` (AC5-N2 only), `tests/technical_support_fakes.py` (`fail` flag), both byte-identical to `b821d54` for those blocks | `pytest -k AC5_N2` or the test name: **1 failed (500)**. Commit body records it. Not pushed alone |
| R1b | `fix(event-request): keep the assignment when the notice raises (SCRUM-19)` | `technical_support_service.py` | Whole service green. Push R1a and R1b together |
| R2a | `test(scrum-19): a refused status makes no database call` | new `tests/test_technical_support_precheck.py` (AC2-N8) | Red (call count 1 ≠ 0) |
| R2b | `fix(event-request): refuse disallowed statuses before the database call (SCRUM-19)` | service (+ R5, R6 in the same commit, since they touch the same lines) | Green; `ruff check .` clean |
| R3/R4a | `test(scrum-19): pin the requirement-not-found reason and the event pairing` | `verify_technical_support_assignments.sql`: **append** a new block for AC2-N9 and AC2-X7, existing blocks untouched | Red on a fresh disposable cluster (X7 insert accepted) |
| R3/R4b | `fix(database): bind each assignment to its requirement's event (SCRUM-19)` | `0052_technical_support_assignments.sql`; repository constants (R3) | Verifier: ALL … PASSED; race script passes again |
| R7 | `refactor(event-request): share the RPC call and error handling (SCRUM-19)` | repository, service, `main.py` | Whole service green with zero test changes (`git diff --stat` on `tests/` is empty) |
| R2c | `ci: run the SCRUM-19 database verifier in backend CI` | `.github/workflows/backend-ci.yml` | Green on the pushed branch |
| R9 | `docs(scrum-19): record review-fix evidence` | execution record; service README (R8) | §5 done |

## 4. Deferred, needs your decision later

1. **Give "requirement not found" its own errcode (P0006).** This is the proper fix for R3, but it edits the AC2-N1 expectations in the DB verifier and the fake. Raise it as its own sign-off if you want it. Otherwise R3's pinned-message test is enough for this release.
2. **Skill vocabulary as a database domain type, and an FK from `technical_support_skills.user_id` to `auth.users`.** Belongs with the future staff-skills story.

## 5. Done check

- `backend/eventRequestService`: `ruff check .` clean; `pytest -q` = 694 + 1 (AC2-N8) passed, 1 skipped. Report the exact counts, not "passed".
- `git diff b821d54 HEAD -- tests/test_technical_support_api.py` shows only the `4d1488a` timestamp/AC4-P1 corrections, and the AC5-N2 block matches `b821d54`.
- Fresh disposable `postgres:16`: verifier and race script pass. CI `database-verify` job green.
- Every new test has its `# AC…` label comment (`grep -n "AC2-N8\|AC2-N9\|AC2-X7"`).
- Then start increment 2 at commit 10a.
