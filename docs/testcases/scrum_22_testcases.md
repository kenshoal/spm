# SCRUM-22 — Withdraw a Registration

Source: [Jira SCRUM-22](https://is212g9t4.atlassian.net/browse/SCRUM-22). Builds on SCRUM-21 (`0048_event_registrations.sql`, `registration_*` modules in eventRequestService), merged to `dev` (re-checked at `9276da2`, 23 Oct).
Status: **D1–D3 approved as recommended by Yang (story owner) on 23 October 2026**; recorded here, not written back to Jira. PO sign-off on D1–D3 is still worth confirming. D7 and D8 are deferred: they need `0061` / `0060`, which are not in `dev` (see Scope).

## Dependency check (23 Oct 2026, `origin/dev` at `9276da2`)

| Needed | Where it exists | OK |
| --- | --- | --- |
| `event_registrations` table with `status` column | `0048` (CHECK currently `IN ('Registered')`, comment "SCRUM-22 widens this CHECK") | Yes |
| Partial unique index on active registrations only | `event_registrations_one_active_idx … WHERE status = 'Registered'` — a Withdrawn row frees the slot for re-registration | Yes |
| Capacity counted from `Registered` rows only | `register_for_event`, `count_active` (`status=eq.Registered`) — withdrawn rows drop out with no change | Yes |
| Event row lock to serialise against `register_for_event` | `SELECT … FOR UPDATE` on `event_requests` in `0048` | Yes |
| Attendee auth, role check, injected clock | `get_attendee_id`, `get_now` (SCRUM-21 D9) | Yes |
| Attendee can see their registrations | `GET /attendee/registrations` | Yes |
| Test fakes | `tests/registration_support.py` (`FakeRegistrationRepository`, `add_event`) | Yes |

No Jira blockers on SCRUM-22. Not dependencies (stay out of scope): SCRUM-24 waiting-list promotion, SCRUM-38 notifications.
SCRUM-36 merged into `dev` (PR #93, `9276da2`). It touches no registration code or migrations, so it doesn't affect SCRUM-22.

Unmerged branches that do touch `event_registrations` (no blockers, but they need coordinating):

| Branch | Migration | Effect on SCRUM-22 |
| --- | --- | --- |
| `feat/scrum-41-manual-registration` | `0060` adds `registered_by`, `coordinator_register_attendee` | Coordinator-made registrations exist → D8. Same `registration_*` files and fakes → merge conflicts |
| `feat/scrum-25-record-attendance` (includes 0060) | `0061` adds `attended_at`, `checked_in_by`; `check_in_attendee` only accepts `Registered` | Check-in can happen on the event day before start → D7. Same files |
| in `dev`: SCRUM-35 / `0059` date approval | can change `proposed_date_times` on a Confirmed event | The cut-off must be read under the lock, not cached → AC1-B5 |

Caveat: there is **no attendee frontend on `dev` yet** (SCRUM-21 increment 2), so this plan proves AC3/AC4 visibility at the API. A Withdraw button waits on that page.

## Scope of this increment

- **Included:** AC1 to AC4 at the API and database. Endpoint `POST /attendee/registrations/{id}/withdrawal`, migration `0062`.
- **Deferred (cannot be built or tested against `dev` yet):** D7 and AC2-N8 / AC2-N9 (need SCRUM-25 `0061`), D8 and AC1-H3 (need SCRUM-41 `0060`). D8 needs no code: ownership is `attendee_id` only, so a coordinator-made registration is already withdrawable by its attendee once `0060` lands. Add the tests after those branches merge.
- **Excluded:** the Withdraw button (no attendee frontend on `dev`), waiting-list promotion (SCRUM-24, hook comment left in `withdraw_registration`), notifications (SCRUM-38).
- Test IDs added during the build: AC2-N10 (event with no dates), plus spy tests for AC2-N2 / AC1-B2 / AC2-N1 proving early refusals never reach the write, and AC3-N1 (re-registering after the window closed is refused).

## AC review

| Jira AC | Outcome | Proposed wording |
| --- | --- | --- |
| An Attendee can withdraw a registration they currently hold (where withdrawal is permitted). | **Split** — "where permitted" is undefined | **AC1:** Given an Attendee holding a `Registered` registration for a Confirmed event that has not started (D1), when they withdraw it, then its status becomes `Withdrawn`, `withdrawn_at` is set and the updated registration is returned. **AC2:** Given a registration that is not theirs, unknown, already `Withdrawn`, or whose event is not Confirmed or has started, when they try to withdraw, then they are refused with the reason and nothing changes. |
| Given a withdrawal, when completed, then the place is released and freed capacity becomes available to others. | **Keep, clarified** | **AC3:** Given a completed withdrawal, then the event's `places_remaining` rises by one, another Attendee can take that place while the window is open, and the withdrawn Attendee may register again (D3). |
| The Attendee's status updates to withdrawn and the change is visible to them. | **Clarify** (status part overlaps AC1) | **AC4:** Given a withdrawn registration, when the Attendee lists their registrations, then it appears with status `Withdrawn` and `withdrawn_at`; no other attendee sees it. |

## Decisions (proposed)

| # | Decision | Needs approval |
| --- | --- | --- |
| D1 | Withdrawal permitted while the event is `Confirmed` **and** `now <` the earliest `proposed_date_times` (event start). Not tied to the registration window: an attendee should be able to release a place after sign-ups close. | **Yes** |
| D2 | Soft withdrawal: `UPDATE status = 'Withdrawn', withdrawn_at = p_now`; the row is kept (history, AC4). No hard delete. | Yes |
| D3 | Re-registering after withdrawal is allowed (new `Registered` row, normal SCRUM-21 rules); the partial index already permits it. | **Yes** |
| D4 | `POST /attendee/registrations/{registration_id}/withdrawal` → 200 `RegistrationResponse`. Not yours / unknown → 404 (no existence leak). Already withdrawn → 409 `already_withdrawn`. Not permitted (D1) → 409 `withdrawal_not_permitted`. | No (technical) |
| D5 | DB function `withdraw_registration(p_registration_id, p_attendee_id, p_now)` in new migration `0062_withdraw_registration.sql` (0056, 0058, 0059 are in `dev`; 0060, 0061 are taken by unmerged SCRUM-41/25 branches). Locks the **event row** `FOR UPDATE` first (same lock as `register_for_event`), then the registration row. Errcodes: `P0002` not found / not owner; `P0004` reasons `already withdrawn`, `withdrawal not permitted`. `SECURITY INVOKER`, `service_role` only; adds `GRANT UPDATE (status, withdrawn_at)` to `service_role`. Widens CHECK to `('Registered','Withdrawn')`; adds `withdrawn_at timestamptz` + CHECK `(status = 'Withdrawn') = (withdrawn_at IS NOT NULL)`. | No |
| D7 | A checked-in registration (`attended_at IS NOT NULL`, SCRUM-25) cannot be withdrawn → 409 `withdrawal_not_permitted`. Only applies once `0061` is in `dev`; branch from `dev` after SCRUM-25 merges, or add it then. | **Yes** |
| D8 | An attendee may withdraw a registration a coordinator made for them (SCRUM-41 `registered_by`); ownership is `attendee_id` only. | **Yes** |
| D6 | `RegistrationResponse.status: Literal["Registered","Withdrawn"]`, new `withdrawn_at: datetime | None`. | No |

## Test case specification

Layers: U = `tests/test_withdrawal_rules.py`, A = `tests/test_withdrawal_api.py`, R = `tests/test_withdrawal_repository.py` (new files, so they do not collide with the SCRUM-41 / SCRUM-25 edits to the SCRUM-21 test files), D = new `database/verify_registration_withdrawal.sql` + `verify_registration_withdrawal_race.sh`. Fixture clock: `NOW = 2030-01-15 12:00Z`; event start `START = 2030-02-01 18:00Z` (`add_event` default).

| ID | AC | Scenario | Tech | Pre-conditions | Steps | Expected | Forbidden side effects | Layer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AC1-H1 | AC1 | Attendee withdraws own registration | Happy | A `Registered` on Confirmed open event, cap 10 | POST withdrawal as A | 200; `status` Withdrawn; `withdrawn_at` = NOW; body includes public event | Other rows untouched | A + D |
| AC1-H2 | AC1, AC3 | Withdraw after registration window closed, before start (D1) | Happy | A Registered; NOW ≥ `closes_at`, < START | POST withdrawal | 200 Withdrawn | — | U + A |
| AC1-B1 | AC1 | 1 s before event start | Boundary | A Registered | `check_withdrawal(now = START − 1 s)` | allowed | — | U + D |
| AC1-B2 | AC1 | Exactly at start | Boundary | as above | now = START | `WithdrawalNotPermittedError` | Row stays Registered | U + D |
| AC1-B3 | AC1 | 1 s after start | Boundary | as above | now = START + 1 s | `WithdrawalNotPermittedError` | — | U |
| AC1-B4 | AC1 | Multi-date event uses the earliest date | Boundary | `proposed_date_times` = [Feb 3, Feb 1] | now = Feb 2 | refused (started) | — | U |
| AC1-B5 | AC1 | Cut-off follows an approved date change (SCRUM-35 `0059`) | Boundary | A Registered; event dates moved earlier so START′ < NOW | withdraw | refused (started); later move → allowed | — | D |
| AC1-H3 | AC1 | Withdraw a coordinator-made registration (D8; needs `0060`) | Happy | Row with `registered_by` = coordinator, `attendee_id` = A | POST withdrawal as A | 200 Withdrawn | — | A + D |
| AC2-P1…P10 | AC2 | Event in each non-Confirmed status (Cancelled, Completed, …) | Partition | A Registered, then event status set | POST withdrawal | 409 `withdrawal_not_permitted` | Row stays Registered | U + A |
| AC2-N8 | AC2 | Checked-in registration (D7; needs `0061`) | Negative | A Registered, `attended_at` set | POST withdrawal | 409 `withdrawal_not_permitted` | Row unchanged | U + A + D |
| AC2-N9 | AC2 | Withdrawn registration can't be checked in (needs `0061`) | Negative | A Withdrawn, event day | `check_in_attendee` | `P0002`/refusal from SCRUM-25 | Stays Withdrawn | D |
| AC2-N1 | AC2 | Already withdrawn | Negative | A's registration Withdrawn | POST withdrawal again | 409 `already_withdrawn` | `withdrawn_at` unchanged | A + D |
| AC2-N2 | AC2 | Another attendee's registration | Negative | B owns registration | POST withdrawal as A on B's id | 404 | B's row unchanged | A + D |
| AC2-N3 | AC2 | Unknown registration id | Negative | — | POST random uuid | 404 | — | A |
| AC2-N4 | AC2 | Malformed id | Negative | — | POST `/registrations/not-a-uuid/withdrawal` | 422 | — | A |
| AC2-N5 | AC2 | DB refusal wins over a stale pre-check (event cancelled between read and write) | Negative | Fake read says Confirmed; write raises `P0004 withdrawal not permitted` | POST withdrawal | 409 `withdrawal_not_permitted` | — | A |
| AC2-N6 | AC2 | Supabase outage | Negative | Repo raises `SupabaseRepositoryError`; mocked 500 / network error | POST; `withdraw` | 502; `SupabaseRepositoryError` (not `RegistrationRpcError`) | — | A + R |
| AC2-N7 | AC2 | RPC refusals carry errcode + reason | Negative | Mocked RPC: P0002, P0004 ×2 | `withdraw` | `RegistrationRpcError(errcode, reason)` | — | R |
| AC2-X1 | AC2 | Other roles cannot withdraw | Cross-cutting | Open event, A Registered | POST as organiser, coordinator, ops manager | 403 | Row unchanged | A |
| AC2-X2 | AC2 | No session | Cross-cutting | real auth dependency | POST no header | 401 | — | A |
| AC2-X3 | AC2 | Browser roles cannot call the function or update the table | Cross-cutting | local cluster with `0056` | `has_function_privilege`, `has_column_privilege(... 'UPDATE')` for `anon`, `authenticated` | false; `service_role` true | — | D |
| AC3-H1 | AC3 | Places remaining rises by one | Happy | cap 5, 5 Registered incl. A | withdraw A; GET `/attendee/events/{id}` | `places_remaining` 0 → 1 | — | A |
| AC3-H2 | AC3 | Freed place can be taken by someone else | Happy | cap 1, A holds it; window open | A withdraws; C registers | 201 for C (before: 409 `event_full`) | Never 2 Registered | A + D |
| AC3-H3 | AC3 | Withdrawn attendee re-registers (D3) | Happy | A Withdrawn, place free, window open | POST registration as A | 201; new row; old Withdrawn row kept | — | A + D |
| AC3-X1 | AC3 | Race: withdraw vs register for the last place | Cross-cutting | cap 1 full by A; two `psql` sessions | S1 withdraws A, S2 registers C concurrently | ≤ 1 Registered row at all times; C succeeds iff S1 committed first, else `P0004 event full` | Never 2 Registered | D |
| AC3-X2 | AC3 | Race: double withdraw | Cross-cutting | A Registered; two sessions | both call `withdraw_registration` | one succeeds, other `P0004 already withdrawn` | `withdrawn_at` set once | D |
| AC4-H1 | AC4 | List shows Withdrawn with timestamp | Happy | A has one Registered, one Withdrawn | GET `/attendee/registrations` as A | both, newest first; statuses and `withdrawn_at` correct | — | A |
| AC4-N1 | AC4 | B cannot see A's withdrawn row | Negative | A Withdrawn | GET as B | empty | — | A |
| AC4-X1 | AC4 | DB CHECK pairs status and `withdrawn_at` | Cross-cutting | local cluster | direct UPDATE with mismatched pair as superuser | CHECK violation | — | D |
| AC1-R1 | AC1 | RPC payload correct | Happy | mocked transport | `withdraw` | POST `/rpc/withdraw_registration` with `p_registration_id`, `p_attendee_id`, `p_now` ISO | — | R |

Mutation checks to confirm the tests bite (§7): start-time comparison `<` → `<=`; using `max(proposed_date_times)`; skipping the ownership filter; counting Withdrawn rows in `count_active`; locking only the registration row (AC3-X1 must fail).

## TDD order

1. **Contract** — get D1–D3 approved; record in `docs/testcases/scrum_22_testcases.md`.
2. **Red U** — `check_withdrawal(event, registration, now)` stub raising `NotImplementedError`; AC1-B1…B4, AC1-H2, AC2-P*. Green: rules.
3. **Red A** — extend `FakeRegistrationRepository` with `get_registration`, `withdraw` (mirrors D5); add route + handlers for `WithdrawalNotPermittedError`, `AlreadyWithdrawnError`, `RegistrationNotFoundError`. AC1-H1, AC2-*, AC3-H1…H3, AC4-*. Green: service + controller + `main.py` handlers + model D6.
4. **Red R** — mocked transport: AC1-R1, AC2-N6, AC2-N7. Green: `SupabaseRegistrationRepository.withdraw`, `get_registration`, add `withdrawn_at` to `list_for_attendee` select.
5. **Red D** — `verify_registration_withdrawal.sql` against docker `postgres:16` with dev migrations + `0048`; fails on missing function. Green: `0062`. Then race script (AC3-X1, AC3-X2).
6. Re-run SCRUM-21 suite + whole service `pytest -q`, `ruff check .`; record execution table.

## Open questions

1. D1 — start of event vs. registration close as the withdrawal cut-off? (Recommended: event start.)
2. D3 — allow re-registration after withdrawal? (Recommended: yes.)
3. SCRUM-24: when built, should a withdrawal auto-promote the first waitlisted attendee inside `withdraw_registration`? Leave a hook comment, don't build it here.
4. Merge order with SCRUM-41 and SCRUM-25: both edit `registration_service.py`, `registration_repository.py`, `models/registration.py`, `main.py` and `registration_support.py`. Recommended: branch SCRUM-22 after they merge, or agree with Jaren on who widens the `status` Literal.
5. Frontend Withdraw button — part of SCRUM-21 increment 2, or a separate increment here?

## Execution results (23 October 2026)

Environment: cloud workspace, Python 3.13, `uv`; disposable local PostgreSQL 16.15 cluster (database `scrum48_s22`) built by `bootstrap_event_status_history.py` + `0026` + `0048` + `0062`. Base `9276da2` (`origin/dev`). Local only: not run against shared Supabase, a browser or CI.

| Check | Command | Result |
| --- | --- | --- |
| Baseline before changes | `cd backend/eventRequestService && pytest -q` | 772 passed, 1 skipped |
| Withdrawal tests, red first | `pytest -q tests/test_withdrawal_*.py` before code | collection error / 28 failed, for the missing code |
| Whole service after | `pytest -q` | 834 passed, 1 skipped (62 new) |
| Lint | `ruff check .` | All checks passed |
| Migration re-run | `psql -f migrations/0062_withdraw_registration.sql` twice | no error (idempotent) |
| DB verification | `psql -f verify_registration_withdrawal.sql` | ALL REGISTRATION WITHDRAWAL VERIFICATIONS PASSED |
| SCRUM-21 DB verification, unchanged | `psql -f verify_event_registrations.sql` | ALL EVENT REGISTRATION VERIFICATIONS PASSED |
| Races AC3-X1, AC3-X2 | `DSN=… ./verify_registration_withdrawal_race.sh` | RACE VERIFICATION PASSED |

Mutation checks (the tests failed for each): `now >= start` → `>`; `min` → `max` of the dates; ownership filter removed; early `check_withdrawal` removed; event row not locked (the race script failed with `event full`). Not run: `count_active` counting Withdrawn rows (covered by AC3-H1 asserting places remaining).

Not yet done: AC1-H3, AC2-N8, AC2-N9 (blocked on `0060` / `0061`), shared-database rollout of `0062`, the Withdraw button.

## Follow-up: withdrawal notice (AC5, added 26 October 2026)

Not in the Jira ACs. SCRUM-38 AC1 split it out ("the confirmation of a withdrawal is SCRUM-22's `registration_withdrawn`", `docs/testcases/scrum_38_testcases.md`), and Yang agreed to build it. Built on the SCRUM-38 branch (`feat/scrum-38-registration-notices`) because it reuses that branch's `NotificationClient` registration helper and the `RegistrationService` constructor wiring. Merge SCRUM-38 first.

**AC5:** Given an Attendee's withdrawal is saved, when it completes, then the Attendee receives `registration_withdrawn` (event name, status `Withdrawn`) through the same `POST /notifications/events` call, once per registration. A refused withdrawal, or one the database refuses after the early check, tells nobody. A notification failure never undoes the withdrawal.

Decisions: the key is per registration and type (`registration-withdrawn:<registration id>`), so a repeat is stored once and a later registration, once withdrawn, notifies again. Recipient is the Attendee only. No link in the inbox line, because the frontend has no Attendee event page yet.

| ID | AC | Scenario | Technique | Expected | Layer |
| --- | --- | --- | --- | --- | --- |
| AC5-H1 | AC5 | Withdrawing tells the Attendee after the withdrawal is saved | Happy | 200; one `registration_withdrawn` with event id, attendee, name, registration id | API + service |
| AC5-N1 | AC5 | Refused withdrawal (not owner, unknown, already withdrawn, started, not Confirmed) | Negative | 404 / 409; nothing sent | API + service |
| AC5-N2 | AC5 | Notification service unreachable | Negative | 200 Withdrawn; row stays Withdrawn | API + client |
| AC5-H2 | AC5 | Client posts the agreed shape with a stable key | Happy | `event_type`, `recipient_id`, `event_id` = uuid5 of `registration-withdrawn:<id>`, payload with status Withdrawn | Client |
| AC5-B1 | AC5 | Two registrations by one attendee | Boundary | Different keys | Client |
| AC5-N3 | AC5 | Notification service answers 500 | Negative | Swallowed, not raised | Client |
| AC5-N4 | AC5 | No notification URL configured | Negative | Nothing posted | Client |
| AC5-N5 | AC5 | Database refuses after the early check passed | Negative | 409; row Registered; nothing sent | API + service |
| AC5-H3 | AC5 | Inbox line names the event, no link | Happy | "You've withdrawn from Community Dinner."; `href` null | UI (unit) |
| AC5-N6 | AC5 | Inbox line when the event has no name | Negative | "Your registration has been withdrawn." | UI (unit) |

Results (26 October 2026, cloud sandbox, Python 3.13 / Node 22; local only, not CI or a browser). Base `dcf4672` (the SCRUM-38 branch):

| Check | Result |
| --- | --- |
| `pytest -q` in eventRequestService, before | 950 passed, 1 skipped |
| New tests red first | 5 failed (AC5-H1, H2, B1, N3, N4) before the code |
| `pytest -q` after | 962 passed, 1 skipped (12 new) |
| `ruff check .` | All checks passed |
| `npm test` in frontend, after | 67 files, 525 tests passed; the 2 new tests failed first with the generic fallback line |
| `npm run lint`, `npm run typecheck` | clean |
| Mutation checks | notice removed, and notice sent before the write: each fails a test |
