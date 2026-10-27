# SCRUM-24 Implementation Plan: Join an Event Waiting List

Drafted 27 October 2026 by Claude (Cowork) for Yang Xue (story owner). **Status: not started.** The contract, decisions D1–D10 and the full test catalogue are in `docs/testcases/scrum_24_testcases.md`; this plan only says *how* to build it and in what order.

**Goal:** When a Confirmed event is full, an Attendee can join its waiting list. Each place that opens is held for the next eligible Attendee for 3 days. They are told when they are offered a place, warned before the offer expires, and told when it expires. They can accept, withdraw, or let the offer pass on. An assigned Coordinator can choose the recipient instead.

**Source of truth:** [Jira SCRUM-24](https://is212g9t4.atlassian.net/browse/SCRUM-24); spm-brain M6-2a/M6-2b; Q&A #26, #44, #116; Briefing §4.

**Branch:** `feat/scrum-24-waiting-list` from `origin/dev` (at `de2d755` on 25 Oct; fetch again first). PR into `dev`.

---

## 0. Before any production code

| # | Gate | Who | State |
| --- | --- | --- | --- |
| G1 | D1–D5 decided | Yang | **Done** (26–27 Oct) |
| G2 | D6 (offers hold capacity): SCRUM-21 side | Yang (SCRUM-21 owner) | **Done** (27 Oct) |
| G3 | D6: SCRUM-41's `coordinator_register_attendee` also counts holds; and should a Coordinator-registered attendee's waiting entry close (open question 3) | Jaren (SCRUM-41) | Message drafted 27 Oct; waiting |
| G4 | D7 per-place memory, D8 #116 offer cut-off (and its strict boundary, open question 5), D9 Coordinator chooses the recipient | PO | Waiting |
| G5 | Who may override (ledger §D) | PO | Waiting; tests assume the assigned Coordinator |
| G6 | Teammate review of the AI-drafted test cases (`testing.md` §10) | any teammate | Waiting |
| G7 | D11 list closes at the cut-off, D12 post-cut-off places go to registration, D13 SCRUM-24 owns waiting-list cancellation notices | PO | **Approved 27 Oct.** Test rows AC10–AC12 folded into commits 4, 6, 10 and 11 (below), not a separate pair |
| G8 | D14: SCRUM-57's per-type channel settings include the waiting-list types (email) | Tate (SCRUM-57) | Waiting; doesn't block SCRUM-24's in-app Done |

Steps 1–4 below (test catalogue commit and Red tests) can start now. Hold commit 6 onward (Green) until G3 and G4 are answered, because they decide AC3, AC4-P*, AC4-B8/B9 and AC8-N1. Increments are ordered so the least contested work lands first.

---

## 1. Dependencies (checked 27 Oct on local refs)

| Story | State | Effect on SCRUM-24 |
| --- | --- | --- |
| SCRUM-21 Register | Merged (`0048`) | Its capacity check and `places_remaining` change to count holds (D6) |
| SCRUM-22 Withdraw | Merged (`0062`) | `withdraw_registration` is where a place opens. **Its `SCRUM-24 hook` comment sits *before* the `UPDATE`**; the promotion call has to go *after* it, once the place is actually free |
| SCRUM-41 Manual register | `0060` on `dev`; Jira "In Review" | Its capacity check changes too (D6, G3) |
| SCRUM-40 Auto-completion | Merged (`PeriodicTaskRunner`, `build_periodic_task_runner` in `main.py`) | The waitlist timer registers as one more handler |
| SCRUM-64 Arrangement reviews | Merged (`0037`/`0038` outbox + `ArrangementReviewNotificationRelay`) | Pattern for a durable notification outbox (§3) |
| SCRUM-38 Registration notices | Branch only | Inbox-line pattern (`describeNotification`); no code dependency. SCRUM-38 explicitly leaves waiting-list notices to SCRUM-24 |

---

## 2. Design

### 2.1 Migration `00NN_event_waitlist.sql` (next free number after `0064`; fetch again just before merging)

1. **Tables** (D10):
   - `event_waitlist_entries (id uuid pk, seq bigserial, event_request_id fk, attendee_id fk auth.users, status text CHECK IN ('Waiting','Offered','Accepted','Withdrawn'), queued_at, offered_at, expires_at, warned_at, withdrawn_at, place_id fk null)`, plus CHECKs: `Offered` ⇔ `offered_at`/`expires_at`/`place_id` set; `Withdrawn` ⇔ `withdrawn_at` set.
   - `event_waitlist_places (id uuid pk, event_request_id fk, opened_at, closed_at, outcome text CHECK IN ('Accepted','Released'))`.
   - `event_waitlist_place_offers (place_id, attendee_id, outcome text CHECK IN ('Offered','Lapsed','Revoked','Withdrawn','Accepted'))`, PK `(place_id, attendee_id)`. This holds D7's per-place memory: "already had it" means outcome `Lapsed` (a revoked holder may get the same place again, AC3-H2).
   - `waitlist_notification_outbox (id, entry_id, recipient_id, event_type, idempotency_key unique, payload jsonb, occurred_at, published_at)`.
   - Partial unique index: one `Waiting`/`Offered` entry per `(event_request_id, attendee_id)`. Index on `(event_request_id, status, queued_at, seq)` for FIFO.
   - RLS on, no browser policies; `REVOKE` from `PUBLIC, anon, authenticated`; grants to `service_role` (pattern from `0048`/`0062`).
2. **Private helpers** (not executable by `service_role` directly):
   - `private.places_taken(event_id) → int` = `Registered` registrations + `Offered` entries (D6).
   - `private.offer_open_place(event_id, place_id, now)`. Picks the earliest `Waiting` entry (by `queued_at`, `seq`) with no `Lapsed` row for this place. If `now + 72h < start` (D8) it marks the entry `Offered` and writes the place-offer row and the outbox row. Otherwise it closes the place as `Released`.
   - `private.open_place(event_id, now)`: inserts an `event_waitlist_places` row and calls `offer_open_place`. If nobody is waiting, it closes the place immediately as `Released`.
3. **Changed existing functions** (`CREATE OR REPLACE`; same signatures):
   - `register_for_event` (`0048`) and `coordinator_register_attendee` (`0060`): replace `count(*) … status = 'Registered'` with `private.places_taken(...)`.
   - `withdraw_registration` (`0062`): after the `UPDATE … 'Withdrawn'`, call `private.open_place(v_event.id, p_now)`; remove the hook comment.
4. **New public functions** (`SECURITY INVOKER`, `search_path = ''`, event row `FOR UPDATE` first, `service_role` only; errcodes `P0002` not found, `P0004` + reason):
   - `join_waitlist(event, attendee, now)`: Confirmed, window open (SCRUM-21 D3), `places_taken ≥ capacity`, not registered, not already waiting.
   - `accept_waitlist_offer(entry, attendee, now)`: `Offered`, `now ≤ expires_at` (D1). Inserts the `Registered` row, marks the entry `Accepted`, closes the place as `Accepted`.
   - `withdraw_from_waitlist(entry, attendee, now)`: `Waiting` → `Withdrawn`; or `Offered` → `Withdrawn` (outcome `Withdrawn`) followed by `offer_open_place` (AC7/AC9).
   - `choose_waitlist_recipient(event, entry, coordinator, now)`: assigned-Coordinator check, an open place exists, target `Waiting`. Revokes the in-flight offer (holder → `Waiting`, same `queued_at`, outcome `Revoked`, outbox `waitlist_offer_revoked`), then offers the chosen entry (D9).
   - `process_waitlist_timers(now)`:
     - Warn where `now ≥ offered_at + 48h` and `warned_at` is null (D2).
     - Expire where `now > expires_at`: the entry goes to `Waiting` with `queued_at = now` (D3), the place-offer outcome becomes `Lapsed`, and `offer_open_place` runs.
     - Locks each event in turn and is idempotent (AC4-X1).

Positions are not stored. They are computed as `row_number()` over `Waiting` entries ordered by `queued_at, seq`, so a withdrawal closes the gap automatically (AC6-H1).

### 2.2 Notifications

Notices are written to `waitlist_notification_outbox` **inside** the same transaction, then delivered by a relay. This is the SCRUM-64 `0037`/`0038` pattern; registration and withdrawal stay unaffected by a notification outage. It meets the test doc's rules: nothing is sent on rollback (AC5-N4), an outage never undoes the change (AC5-N3), and one key per notice gives no repeats (AC5-N1). Update the test doc's Persistence line from "best-effort after commit" to "outbox, delivered after commit". Delivery waits for the next relay pass (default 60 s); that's acceptable for a 3-day window.

Event types: `waitlist_offered`, `waitlist_offer_expiring`, `waitlist_offer_expired`, `waitlist_offer_revoked`.

### 2.3 Backend (eventRequestService)

| File | Change |
| --- | --- |
| `app/services/waitlist_rules.py` | **New.** Pure functions mirroring the DB rules, for unit tests and early API refusals: `check_join`, `check_accept` (D1), `offer_deadline`, `expiry_due` (D1, the timer's expiry pass), `warning_due` (D2), `may_issue_offer` (D8), `next_recipient` (FIFO + D7), `requeue` (D3) |
| `app/models/waitlist.py` | **New.** `WaitlistEntryResponse` (id, event, status, position, queued_at, offered_at, expires_at) |
| `app/repositories/waitlist_repository.py` | **New.** Protocol + Supabase implementation: the five RPCs, `list_for_attendee`, `pending_outbox`, `mark_published` |
| `app/services/waitlist_service.py` | **New.** Role checks, calls the rules then the RPC, maps `P0002`/`P0004` to 404/409 codes (D10) |
| `app/services/waitlist_notification_relay.py` | **New.** Reads the outbox, posts through `notification_client.py`, marks published |
| `app/services/waitlist_timer.py` | **New.** `run_once()` → `process_waitlist_timers(get_now())`, then relay |
| `app/controllers/waitlist_controller.py` | **New.** Endpoints in §2.4 |
| `app/main.py` | Include the router; map errors; in `build_periodic_task_runner` add `handlers["waitlist_timers"]` behind `WAITLIST_TIMERS_ENABLED` (same switch pattern as auto-completion) |
| `app/repositories/registration_repository.py` | `count_active_for_events` counts `Offered` entries too (D6) — second exact-count query per event, same `Prefer: count=exact` approach as SCRUM-21 U8 |
| `tests/waitlist_support.py` | **New.** `FakeWaitlistRepository`, fixtures for `E`, `A`–`D`, `R1`/`R2`, Coordinator `K`; reuses `registration_support.py` |

### 2.4 Endpoints

| Method and path | Success | Refusals |
| --- | --- | --- |
| `POST /attendee/events/{id}/waitlist` | 201 entry | 404; 409 `places_available` / `registration_not_open` / `already_registered` / `already_waitlisted`; 401; 403 |
| `GET /attendee/waitlist` | 200, caller's entries with positions | 401; 403 |
| `POST /attendee/waitlist/{entry_id}/acceptance` | 200, entry + registration | 404; 409 `offer_expired` / `not_offered`; 502; 401; 403 |
| `POST /attendee/waitlist/{entry_id}/withdrawal` | 200 entry | 404; 409 `already_withdrawn` / `not_offered` (accepted); 401; 403 |
| `POST /event-requests/{id}/waitlist/{entry_id}/offer` | 200 entry | 403 (not assigned Coordinator); 404; 409 `not_waiting` / `no_open_place` |

### 2.5 Frontend (small)

- Add the four types to `describeNotification` in `frontend/lib/notifications.ts`, with no link (there's no Attendee event page yet), plus their Vitest cases (AC5-H5).
- The waitlist buttons wait for the Attendee event page (SCRUM-21 increment 2).

---

## 3. Commit sequence (tests first, one AC group at a time)

Run `pytest -q` after each Red commit and put the Red counts in the commit body. Each Red must fail for the intended reason (route 404, `NotImplementedError`, missing function), not a fixture error. Don't push red commits to a shared branch; push only at Green points (★).

| # | Commit | Covers | State after |
| --- | --- | --- | --- |
| 1 | `docs(scrum-24): record story contract, test catalogue and plan` | test doc + this plan | ★ |
| 2 | `test(scrum-24): add Red unit tests for the waiting-list rules` | all `U` rows; `waitlist_rules.py` stubs | Red |
| 3 | `feat(event-request): waiting-list rules (SCRUM-24)` | | Unit Green ★ |
| 4 | `test(scrum-24): add DB verification for the waiting list` | `database/verify_event_waitlist.sql`, `verify_event_waitlist_race.sh` (all `D` rows, including AC12's cancellation trigger) | Red (no tables) |
| 5 | `test(scrum-24): add Red API tests for joining and listing` | AC1, AC8-H1 | Red (route 404) |
| — | *Gate: G3 and G4 answered; adjust the test doc if anything changed* | | |
| 6 | `feat(db): add event waiting list and hold places in capacity (SCRUM-24)` | migration §2.1, plus the `Closed` status and the D13 cancellation trigger (AC12); `database/README.md` | DB script Green on a disposable `postgres:16` (apply `dev`'s migrations first, one transaction per file, as SCRUM-21 U5) |
| 7 | `feat(event-request): join and list the waiting list (SCRUM-24)` | AC1, AC8 | AC1/AC8 API Green ★ |
| 8 | `test(scrum-24): add Red API tests for offers, acceptance and withdrawal` | AC2, AC4, AC6, AC7 | Red |
| 9 | `feat(event-request): accept and withdraw waiting-list offers (SCRUM-24)` | | Green ★ |
| 10 | `test(scrum-24): add Red tests for the waiting-list timer and outbox relay` | AC4-B4/B5, AC4-X1, AC5-*, AC9-H1, AC10, AC11 | Red |
| 11 | `feat(event-request): waiting-list timer and notifications (SCRUM-24)` | relay, timer, `main.py` handler | Green ★ |
| 12 | `test(scrum-24): add Red API tests for a Coordinator choosing the recipient` | AC3 | Red |
| 13 | `feat(event-request): let the assigned Coordinator choose the recipient (SCRUM-24)` | | Green ★ |
| 14 | `feat(frontend): waiting-list notification lines (SCRUM-24)` | AC5-H5 (test first in the same commit is fine: UI unit) | ★ |
| 15 | `test(scrum-24): re-run SCRUM-21 and SCRUM-41 capacity tests as regression` | AC8-X1, AC8-X2 | ★ |
| 16 | `docs(scrum-24): document endpoints and record Green evidence` | service README, execution record | ★ |

AC3 is last because it is the most likely to change after G4/G5. If the PO rejects D9, drop commits 12–13 and retire the AC3 rows.

**Red tests are locked once committed:** in the Green commits, don't edit them to make them pass. If one is wrong, fix it in its own commit with your sign-off.

**One-line bugs each Red should catch:** `<` vs `≤` on `expires_at` (AC4-B2/B3); `>` vs `≥` in the timer (AC4-B4); counting `Registered` only (AC2-N2, AC8-N1); promoting before the `UPDATE` in `withdraw_registration` (AC2-H1, since the place isn't free yet); `queued_at` not reset on expiry (AC4-H2); reset on revoke (AC3-H1); missing D7 filter (AC4-P1); releasing before everyone had it (AC4-P4); `≤` vs `<` on the D8 cut-off (AC4-B9).

---

## 4. Risks

| Risk | Mitigation |
| --- | --- |
| Changing three existing capacity checks breaks SCRUM-21/41 | One helper used everywhere; regression run (commit 15); with no offers the count is identical |
| Merge conflicts with SCRUM-41/25 branches in `registration_*` files | Merge `dev` before commit 6 (`chore: merge dev into feat/scrum-24-waiting-list`) and again before the PR |
| Timer runs on several instances at once | Event row lock + idempotent outcomes (AC4-X1); outbox key unique |
| Migration number taken by a teammate | Fetch and renumber just before merging (SCRUM-21 U3 pattern) |
| Promotion inside `withdraw_registration` slows withdrawal | One indexed `SELECT … LIMIT 1` + two inserts; fine at demo scale |

---

## 5. Done check

- `pytest` and `ruff check .` in `backend/eventRequestService`.
- `npm run lint`, `npm run typecheck` and `npm test` in `frontend`.
- The DB scripts on a disposable cluster, then shared dev after review.
- Every test labelled: `grep -rn "AC[1-9]-" backend/eventRequestService/tests`.
- The execution record filled in (`testing.md` §8).
- A teammate review of the test design (G6).
- PR CI green, then `definition-of-done.md`.
