# SCRUM-21 Implementation Plan: Register for a Confirmed Event

Drafted 17 October 2026 by Claude (Cowork) for Yang Xue (story owner). **Status: implemented on this branch on 18 October 2026** (commits `ca5fe6b` to `e24386c`, built as written below). **Updated 19 October 2026** after SCRUM-60 and SCRUM-64 merged into `dev`: `dev` is merged into the branch (`83db01f`), and §0 lists what is left before the PR, including two fixes from the plan review (U7, U8). **Completed 20 October 2026**: commits 10–15 are done (U3–U8; the AC5-N3 case was renumbered **AC5-N4** because the outage case already held that ID) and the pull request into `dev` is open (U9). **The PO approved D3, D5 and D8 on 20 October 2026** — recorded in the test-case doc and PR #69; AC1-H2 was strengthened to prove D8's capacity condition.

**Goal:** An Attendee can see the public details of a Confirmed event, register during its registration window while places remain, and view their registration.

**Source of truth:** issue tracker SCRUM-21 and spm-brain (`backlog/user-stories.md` M5-2; Q&A #17, #22, #30, #42, #48, #53, #99). Once §2 is approved, the contract and test catalogue live in `docs/testcases/scrum_21_testcases.md`. This plan only says *how* to build it.

**Branch:** `feat/scrum-21-register-for-event` from `origin/dev`. PR into `dev`.

---

## 0. Update 19 October: bring the branch up to date with `dev`

SCRUM-60 (PR #62, merge `38ac2a5`) and SCRUM-64 (PR #63, merge `29e535b`) are on `dev`, so events can now reach `Confirmed` through the Safety Officer's approval (`decide_safety_review`, migration `0034`). **Nothing blocks the backend any more.** The branch was cut from `6b36647`. On 19 Oct it merged `dev` at `29e535b` (`83db01f`) and is now 0 commits behind.

| # | Change | Why | Files | State |
| --- | --- | --- | --- | --- |
| U1 | Merge `dev` with the message `chore: merge dev into feat/scrum-21-register-for-event` | Git's default merge message fails CI (AGENTS.md) | — | **Done** (`83db01f`) |
| U2 | Resolve two conflicts by **keeping both sides** | `dev` added `SafetyDecisionInvalidError`, the SCRUM-64 `arrangement_review_router` and `arrangement_review_relay`, and README rows at the same spots as this story's handlers and row | `backend/eventRequestService/app/main.py`, `database/README.md` | **Done.** The first attempt at `main.py` dropped pieces from both sides and would not import. It was rebuilt from `dev`'s version with only the SCRUM-21 parts added (the diff against `dev` adds lines only) |
| U3 | Rename `0029_event_registrations.sql` → **`0048_event_registrations.sql`** | `0029_safety_review_status.sql` is on `dev`, along with `0030`–`0038` and `0040`–`0044`. `0039` and `0045`–`0047` are only on the SCRUM-58/60 branches (`dev`'s README already documents them), so `0048` is the next free number. Fetch again just before this commit | migration, `database/README.md`, `docs/testcases/scrum_21_testcases.md`, both verify scripts, this plan | **Done** (`312dd9b`; `dev` fetched first, still `29e535b`) |
| U4 | Add `Safety Review` to `NON_CONFIRMED` (9 → 10 statuses) | `0029_safety_review_status.sql` added it between Planning and Confirmed. The rules already refuse it; the tests didn't cover it | `tests/registration_support.py`, `tests/test_registration_rules.py`, test-case doc rows AC1-P10 and AC2-P10 | **Done** (`eb35ebd`) |
| U5 | Rebuild the disposable DB with `dev`'s migrations (`0001`–`0038`, `0040`–`0044`), then `0048`, and re-run `verify_event_registrations.sql` and `verify_event_registrations_race.sh` | The old evidence used `0026` + `0029` only. Confirm the CHECKs still hold with `Safety Review` in the status list. SCRUM-64's trigger `record_event_arrangement_reviews` fires only on updates to dates, attendance, venue or equipment needs, so the row lock in `register_for_event` (no update) does not fire it | evidence in the test-case doc | **Done** (20 Oct: throwaway docker `postgres:16`, one transaction per file because `0041`'s new enum value cannot share its adding transaction; verify, race and an extra `Safety Review` refusal check all passed) |
| U6 | Re-run `pytest` and `ruff check .` in `backend/eventRequestService`, and record the new execution record | Earlier results are no longer current evidence (`testing.md` §8). The merged `main.py` has only been compiled so far | test-case doc | **Done** (20 Oct: 508 passed, 1 skipped; ruff clean; record added) |
| U7 | **Fix: refuse a repeat registration as `already_registered`, even when the event is full** | `RegistrationService.register` runs `check_registration` (capacity) before the RPC, but the RPC checks duplicates *before* capacity. An attendee who holds the last place and registers again gets 409 `event_full`. AC5-N2 only covers a not-full event. Fix: check for an active registration before `check_registration`, so the API matches the DB function's order | `registration_service.py`, `registration_repository.py` (`has_active(event_id, attendee_id)`), `tests/registration_support.py`, `tests/test_registration_api.py`, test-case doc (new **AC5-N4** — the outage case already holds AC5-N3, `testing.md` §3) | **Done** (Red `b0d9d53`, Green `8f8d520`) |
| U8 | **Fix: count active registrations with a count query, not by fetching rows** | `count_active_for_events` fetches every `Registered` row and counts in Python. The Supabase Data API returns at most 1,000 rows by default, so `places_remaining` is wrong past that. Use `Prefer: count=exact` with `HEAD` (or `limit=1`) and read `Content-Range`, once per event | `registration_repository.py`, `tests/test_registration_repository.py` | **Done** (`de651d0`; `HEAD` + `count=exact`, one request per event) |
| U9 | Say in the PR description that D3, D5 and D8 are provisional, naming the tests that change if the PO decides otherwise (AC3-B2/B5, AC5-N2/N4, AC1-H2) | The §2 approval gate was not completed before building | PR description | **Done** — flagged at PR open; the PO approved all three on 20 Oct 2026, PR and test-case doc updated |

**Commit sequence:**

| # | Commit |
| --- | --- |
| 9 | `chore: merge dev into feat/scrum-21-register-for-event` (U1, U2). **Done: `83db01f`** |
| 10 | `fix(database): renumber event registrations migration to 0048 (SCRUM-21)` (U3; same pattern as SCRUM-59's renumber to `0043`). **Done: `312dd9b`** |
| 11 | `test(scrum-21): cover the Safety Review status in the non-Confirmed partitions` (U4). **Done: `eb35ebd`** |
| 12 | `test(scrum-21): add Red test for a repeat registration on a full event` (U7; Red: expects `already_registered`, gets `event_full`). **Done: `b0d9d53`** |
| 13 | `fix(event-request): check for an existing registration before capacity (SCRUM-21)` (U7). **Done: `8f8d520`** |
| 14 | `fix(event-request): count active registrations with an exact count query (SCRUM-21)` (U8, with its repository test written first). **Done: `de651d0`** |
| 15 | `docs(scrum-21): record post-merge local and disposable-database evidence` (U5, U6). **Done 20 Oct** |

Then `git push`, since the branch is ahead of `origin/feat/scrum-21-register-for-event`, and open the PR into `dev` (U9). Applying `0048` to shared development is a separate step after review.

---

## 1. Dependencies

| Story | State (19 Oct) | Effect on SCRUM-21 |
| --- | --- | --- |
| SCRUM-58 Plan and Confirm (Tate) | In Progress. Approved → Planning merged (#59) and the Start Planning button (#61). Planning → Safety Review (`0039_send_for_safety_review.sql`) is still only on `feat/scrum-58-safety-review` | Linked blocker in the issue tracker, but not needed by SCRUM-21's code. Without `0039` on `dev`, no real event can reach Confirmed, so the live run (§7) waits for it |
| SCRUM-60 Operational Safety Check (Jaren) | **Merged into `dev` on 19 Oct (PR #62).** issue tracker still shows To Do | **The only story that sets `Confirmed`** (`decide_safety_review`, `0034`/`0044`). No longer a blocker. Not linked to SCRUM-21 in the issue tracker |
| SCRUM-64 Arrangement review (Jaren) | **Merged into `dev` on 19 Oct (PR #63)** | No effect on registration. Its trigger on `event_requests` ignores the registration columns (U5) |
| SCRUM-13 Reserve Equipment (Yang) | Merged (#60) | SCRUM-60 depends on it |
| SCRUM-22 Withdraw, SCRUM-24 Waiting list, SCRUM-38 Notify, SCRUM-41 Manual register, SCRUM-34 Registration info | To Do | Out of scope. They build on the table this story adds |
| *(no story)* Coordinator sets the registration window and capacity | — | **Gap.** Q&A #30 says the coordinator sets the window, but no story does. See D2 |

**Why this could start before SCRUM-60:** `Confirmed` was already allowed in `event_requests.status` (migration `0011`). Unit and API tests seed Confirmed events through `FakeEventRequestRepository`, and the DB verification inserts a Confirmed fixture as `service_role`. Since 19 Oct the status list also has `Safety Review` (`0029_safety_review_status.sql`), which this story must treat as not Confirmed (U4).

---

## 2. AC review gate (approve before step 4)

| issue tracker AC | Outcome | Proposed wording |
| --- | --- | --- |
| An Attendee can view the event information appropriate for external users before registering. | **Clarify** | **AC1:** Given a Confirmed event, when an Attendee opens it, then they see its public details (D4) and places remaining. Internal planning data is never returned, and an event that isn't Confirmed is reported as not found. |
| Registration is only possible for a **confirmed** event within its open registration period (separate start/end dates). | **Split** | **AC2:** Given an event that isn't Confirmed, when an Attendee tries to register, then they are refused and no registration is stored. The window half moves into AC3. |
| Registration attempted outside the open period is not permitted. | **Merge** with the window half of the AC above | **AC3:** Given a Confirmed event, when an Attendee registers before the window opens, at or after it closes, or when no window is set, then they are refused with the reason and nothing is stored (D3). |
| Given an event at full capacity, when an Attendee attempts to register, then registration is refused. | **Keep, clarified** | **AC4:** Given a Confirmed, open event whose active registrations equal its capacity, when an Attendee registers, then they are refused as full and the count is unchanged. Two attendees racing for the last place: exactly one succeeds. |
| Given a successful registration, when confirmed, then the Attendee's place is recorded and they can view their registration. | **Keep, clarified** | **AC5:** Given a Confirmed, open, not-full event, when an Attendee registers, then one registration is stored for them with status `Registered`, the response includes the event's public details, and they can list their own registrations (and no one else's). |

**Cross-cutting (all ACs, `security-and-state.md` §2):** only the `attendee` role registers. Other roles get 403, no session gets 401, and the browser roles can't call the DB function or read the table.

---

## 3. Decisions to approve

| # | Decision | Proposal | Why |
| --- | --- | --- | --- |
| D1 | Service | Build in **eventRequestService**. It owns `event_requests`, so status, window and capacity are checked in one transaction without a cross-service call | Same pattern as SCRUM-58 |
| D2 | Window and capacity fields | Migration adds `registration_opens_at timestamptz`, `registration_closes_at timestamptz` (CHECK closes > opens) and `registration_capacity integer` (CHECK > 0), all nullable, to `event_requests`. **The screen for coordinators to set them is a new story** (raise at standup; Q&A #30, #42 extension, #99 capacity ≤ venue). SCRUM-21 only reads them | Q&A #30; persona note "do not invent default registration dates or capacity numbers" |
| D3 | Window boundaries | Open from `registration_opens_at` (inclusive) until `registration_closes_at` (exclusive). Null window or null capacity = not open | Needs PO confirmation. Determines AC3-B2/B5 |
| D4 | Public fields | `id, event_name, purpose, description, proposed_date_times, registration_opens_at, registration_closes_at, registration_capacity, places_remaining`. **Not returned:** organiser, coordinator, accessibility/venue/equipment/registration needs, status history, review decisions | Briefing §8b; persona ATT "must not see internal planning info" |
| D5 | Duplicate registration | Team Design Proposal: one active registration per attendee per event. A second attempt is refused with 409 `already_registered` (partial unique index) | Not in the issue tracker ACs. `testing.md` §6 says not to assert refusals the requirement doesn't demand, so it needs approval |
| D6 | Registration fields | Release 1 stores only the attendee's account id and timestamp. No extra form fields | Q&A #22 leaves this to the team. Keep it minimal until someone needs more |
| D7 | Non-visible event | Viewing or registering for an event that isn't Confirmed returns **404**, not 409 | `security-and-state.md` §2: don't disclose internal events |
| D8 | List of open events | Include `GET /attendee/events` (Confirmed events with an open window) | Q&A #17. Without it the attendee can't find the event. If the PO calls it out of scope, drop AC1-H2 |
| D9 | Clock | A `get_now()` FastAPI dependency returns aware UTC; tests override it. The DB function also takes `p_now` so window tests are deterministic | Matches `equipmentService/app/clock.py` |

---

## 4. Design

**Migration `0048_event_registrations.sql`** (first built as `0029`; renumbered on 19 Oct because `0029` to `0047` are taken on `dev` or teammates' branches, see U3. Check again just before merging):

- the three D2 columns on `event_requests`;
- `event_registrations (id uuid pk, event_request_id uuid fk, attendee_id uuid fk auth.users, status text CHECK IN ('Registered') DEFAULT 'Registered', created_at timestamptz)`. SCRUM-22 widens the CHECK for `Withdrawn`;
- partial unique index `(event_request_id, attendee_id) WHERE status = 'Registered'` (D5) and index `(attendee_id, created_at)`;
- RLS on with no browser policies (service role only);
- `register_for_event(p_event_request_id, p_attendee_id, p_now) RETURNS event_registrations`, `SECURITY INVOKER`, `search_path = ''`:
  1. `SELECT … FOR UPDATE` the event. Missing or not `Confirmed` → `P0002`.
  2. Window null or `p_now` outside [opens, closes) → `P0004 'registration not open'`.
  3. Already registered → `P0004 'already registered'`.
  4. `count(*) WHERE status = 'Registered'` ≥ capacity → `P0004 'event full'`.
  5. Insert and return.
- `REVOKE … FROM PUBLIC, anon, authenticated; GRANT EXECUTE … TO service_role` (pattern from `0006`, `0013`).

Locking the event row makes concurrent last-place attempts queue up, which is what AC4-X1 checks.

**Backend files (eventRequestService):**

| File | Change |
| --- | --- |
| `app/services/registration_rules.py` | **New.** Pure `check_registration(event, now, registered_count) -> None`, raising `EventNotVisibleError`, `RegistrationNotOpenError` or `EventFullError`. Also `places_remaining()` and `to_public_event()` (D4 whitelist) |
| `app/models/registration.py` | **New.** `PublicEventResponse`, `RegistrationResponse` |
| `app/repositories/registration_repository.py` | **New.** Protocol and Supabase implementation: `register` (RPC), `list_for_attendee`, `count_active` (an exact count query, U8), `has_active` (U7), `list_open_events` |
| `app/services/registration_service.py` | **New.** Role check (attendee only), calls the rules for reads and the RPC for writes, maps RPC errors. Its early checks run in the RPC's order: visible, window, already registered, capacity (U7) |
| `app/controllers/registration_controller.py` | **New.** Routes below |
| `app/main.py` | Include the router; map new errors to 404/409 |
| `app/clock.py` | **New.** `get_now()` (D9) |

**Endpoints:**

| Method and path | Success | Refusals |
| --- | --- | --- |
| `GET /attendee/events` | 200, list of public events (D8) | 401, 403 |
| `GET /attendee/events/{id}` | 200, public event | 404 if missing or not Confirmed, 401, 403 |
| `POST /attendee/events/{id}/registrations` | 201, registration and public event | 404, 409 `registration_not_open` / `event_full` / `already_registered`, 401, 403 |
| `GET /attendee/registrations` | 200, the caller's own registrations | 401, 403 |

---

## 5. Test catalogue outline (`docs/testcases/scrum_21_testcases.md`)

The full table (pre-conditions, steps, data, forbidden side effects) is written in commit 1. Layers: **U** = unit (`test_registration_rules.py`), **A** = API (`test_registration_api.py`), **D** = DB (`database/verify_event_registrations.sql`).

| ID | Scenario | Expected | Layer |
| --- | --- | --- | --- |
| AC1-H1 | Attendee views a Confirmed event | 200, D4 fields, correct `places_remaining` | A |
| AC1-H2 | List shows only Confirmed events with an open window (D8) | Open event listed; closed, not-yet-open and Planning events absent | A |
| AC1-X1 | No internal field leaks | Response keys equal the D4 whitelist exactly | U + A |
| AC1-P1…P10 | Each non-Confirmed status (Draft, Submitted, Under Review, Changes Requested, Rejected, Approved, Planning, Safety Review, Completed, Cancelled) | 404 | A |
| AC1-N1 | Unknown id | 404 | A |
| AC2-H1 | Register for a Confirmed, open, not-full event | 201 (shared setup with AC5-H1) | A |
| AC2-P1…P10 | Register for each of the 10 non-Confirmed statuses (P10 = Safety Review, added 19 Oct) | 404, no registration row | U + A |
| AC2-X1 | Event cancelled between view and register | `P0002`, no row | D |
| AC3-B1/B2/B3 | 1 s before / exactly at / 1 s after `opens_at` | refused / allowed / allowed | U |
| AC3-B4/B5/B6 | 1 s before / exactly at / 1 s after `closes_at` | allowed / refused (D3) / refused | U |
| AC3-N1 | Window not set | 409 `registration_not_open` | U + A |
| AC3-N2 | API refusal before the window | 409 `registration_not_open`, no row | A |
| AC3-X1 | Rule uses the injected clock, not the wall clock | Non-default `now` values decide the result | U |
| AC4-B1/B2 | capacity − 1 registered → allowed; = capacity → refused | 201; 409 `event_full`, count unchanged | U + A |
| AC4-B3 | Capacity 1, first registrant | 201, then `places_remaining` = 0 | U |
| AC4-N1 | Capacity not set | 409 `registration_not_open` | U |
| AC4-X1 | Two sessions race for the last place | Exactly one row inserted; the other gets `P0004 event full` | D (two `psql` sessions, as in SCRUM-13 AC3-N2) |
| AC5-H1 | Successful registration is stored and returned | Row: attendee, event, `Registered`, `created_at`; body includes the public event | A + D |
| AC5-H2 | Attendee lists own registrations | Only theirs, newest first | A |
| AC5-N1 | Attendee B lists registrations | A's registration absent | A |
| AC5-N2 | Duplicate registration (D5) | 409 `already_registered`, still one row | A + D |
| AC5-N4 | Duplicate registration when the attendee holds the last place (added 19 Oct, U7; numbered N4 on 20 Oct because AC5-N3 was already taken) | 409 `already_registered`, not `event_full`; still one row | A + R |
| AC5-X1 | Organiser, coordinator, operations manager try to register | 403, no row | A |
| AC5-X2 | No session on each endpoint | 401 | A |
| AC5-X3 | Browser roles | `anon` and `authenticated` cannot execute `register_for_event` or select `event_registrations` | D |

Before treating a test as done, ask what plausible one-line bug should make it fail (e.g. `<=` vs `<` on capacity → AC4-B2; `>=` vs `>` on `closes_at` → AC3-B5; the capacity check before the duplicate check → AC5-N3).

---

## 6. Commit sequence (tests first)

| # | Commit | Files | State after |
| --- | --- | --- | --- |
| 0 | *(no commit)* AC review approved; D1 to D9 answered | issue tracker comment or standup note | — |
| 1 | `docs(scrum-21): record approved contract and test catalogue` | `docs/testcases/scrum_21_testcases.md` | — |
| 2 | `test(scrum-21): add Red unit tests for the registration rules` | `tests/test_registration_rules.py`, `app/services/registration_rules.py` (stubs raising `NotImplementedError`), `app/clock.py` | Unit tests Red |
| 3 | `test(scrum-21): add Red API tests for attendee registration` | `tests/registration_support.py` (fake repository with Confirmed fixtures and an attendee auth stub), `tests/test_registration_api.py` | API tests Red (route 404) |
| 4 | `test(scrum-21): add DB verification for register_for_event` | `database/verify_event_registrations.sql` | Red until the migration |
| 5 | `feat(db): add event registrations and register_for_event (SCRUM-21)` | `0029_event_registrations.sql` (renumbered to `0048` in commit 10), `database/README.md` | DB script Green (disposable local PostgreSQL first) |
| 6 | `feat(event-request): registration rules (SCRUM-21)` | `registration_rules.py` | Unit tests Green |
| 7 | `feat(event-request): attendee event view and registration endpoints (SCRUM-21)` | model, repository, service, controller, `main.py` | Whole service Green, `ruff check .` clean |
| 8 | `docs(scrum-21): document endpoints and record Green evidence` | service README, test catalogue execution record | — |

Run `pytest -q` after commits 2 and 3 and put the Red counts in the commit body. Confirm every Red fails for the intended reason (`NotImplementedError` or route 404), not a fixture error. Don't push red commits to a shared branch.

**Red tests are locked once committed:** in commits 5 to 8, don't edit them to make them pass. If one is wrong, fix it in its own commit with your sign-off.

---

## 7. Increment 2 (frontend and live run)

SCRUM-60 and SCRUM-64 are merged, so this no longer waits on them. A live run needs (a) SCRUM-58's Planning → Safety Review move (`0039`, still only on `feat/scrum-58-safety-review` as of 19 Oct) on `dev`, so a real event can reach Confirmed, and (b) a registration window and capacity on that event. No story sets those yet, so seed them with SQL until one exists.


- Frontend attendee page (`frontend/app/events/…`): open-events list, event detail with Register button, "My registrations". Vitest component tests for the empty, full, closed and success states.
- One Playwright journey: log in as `attendee@example.com` → open a Confirmed event → register → see it under My registrations → reload, and it persists.
- Apply `0048` to shared dev; read-only checks of grants; one live API call.

---

## 8. Open questions (take to standup or the PO)

1. ~~D3 window boundaries, D5 duplicates, D8 list: need PO sign-off.~~ Approved by the PO on 20 Oct 2026: D3 and D5 as proposed; D8 kept in this story, conditional on listing only in-window Confirmed events and always reflecting capacity (both proven by the strengthened AC1-H2).
2. Who owns the "set registration window and capacity" story (D2)? Until it exists, live testing needs SQL-seeded values. **Still no issue tracker story as of 19 Oct; now the main gap for a live demo.**
3. Should capacity be checked against the confirmed venue's `max_capacity` (Q&A #99)? Proposed: the setter story enforces it, not SCRUM-21.
4. Discussion #127 (separate Open/Closed registration status) is unanswered. This plan derives "open" from the window, so no new status is needed.
5. ~~Add the SCRUM-60 → SCRUM-21 "blocks" link in the issue tracker.~~ No longer needed: SCRUM-60 merged on 19 Oct. The issue tracker still shows SCRUM-60 as To Do; ask Jaren to move it.

## 9. Done check

`pytest` and `ruff check .` in `backend/eventRequestService`; DB script on a disposable cluster, then shared dev; every test labelled (`grep -rn "AC[1-5]-" backend/eventRequestService/tests`); teammate review of the AI-drafted cases (`testing.md` §10); PR CI green; `definition-of-done.md`.
