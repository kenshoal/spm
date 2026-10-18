# SCRUM-21 Implementation Plan: Register for a Confirmed Event

Drafted 17 October 2026 by Claude (Cowork) for Yang Xue (story owner). **Status: draft. The AC review (§2) and decisions D1 to D9 (§3) need approval before test design is final or any production code is written** (AGENTS.md principle 2, `testing.md` §1).

**Goal:** An Attendee can see the public details of a Confirmed event, register during its registration window while places remain, and view their registration.

**Source of truth:** [Jira SCRUM-21](https://is212g9t4.atlassian.net/browse/SCRUM-21) and spm-brain (`backlog/user-stories.md` M5-2; Q&A #17, #22, #30, #42, #48, #53, #99). Once §2 is approved, the contract and test catalogue live in `docs/testcases/scrum_21_testcases.md`. This plan only says *how* to build it.

**Branch:** `feat/scrum-21-register-for-event` from `origin/dev`. PR into `dev`.

---

## 1. Dependencies

| Story | State (17 Oct) | Effect on SCRUM-21 |
| --- | --- | --- |
| SCRUM-58 Plan and Confirm (Tate) | In Progress. Approved → Planning merged (#59); AC2 and AC3 parked | Linked blocker. Does not set Confirmed |
| SCRUM-60 Operational Safety Check (Jaren) | To Do | **The only story that sets `Confirmed`.** Not linked to SCRUM-21 in Jira; add "is blocked by" |
| SCRUM-13 Reserve Equipment (Yang) | In review | SCRUM-60 depends on it |
| SCRUM-22 Withdraw, SCRUM-24 Waiting list, SCRUM-38 Notify, SCRUM-41 Manual register, SCRUM-34 Registration info | To Do | Out of scope. They build on the table this story adds |
| *(no story)* Coordinator sets the registration window and capacity | — | **Gap.** Q&A #30 says the coordinator sets the window, but no story does. See D2 |

**Why this can start now:** `Confirmed` is already allowed in `event_requests.status` (migration `0011`). Unit and API tests seed Confirmed events through `FakeEventRequestRepository`, and the DB verification inserts a Confirmed fixture as `service_role`. Only the live end-to-end journey (§7, increment 2) waits for SCRUM-60.

---

## 2. AC review gate (approve before step 4)

| Jira AC | Outcome | Proposed wording |
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
| D5 | Duplicate registration | Team Design Proposal: one active registration per attendee per event. A second attempt is refused with 409 `already_registered` (partial unique index) | Not in the Jira ACs. `testing.md` §6 says not to assert refusals the requirement doesn't demand, so it needs approval |
| D6 | Registration fields | Release 1 stores only the attendee's account id and timestamp. No extra form fields | Q&A #22 leaves this to the team. Keep it minimal until someone needs more |
| D7 | Non-visible event | Viewing or registering for an event that isn't Confirmed returns **404**, not 409 | `security-and-state.md` §2: don't disclose internal events |
| D8 | List of open events | Include `GET /attendee/events` (Confirmed events with an open window) | Q&A #17. Without it the attendee can't find the event. If the PO calls it out of scope, drop AC1-H2 |
| D9 | Clock | A `get_now()` FastAPI dependency returns aware UTC; tests override it. The DB function also takes `p_now` so window tests are deterministic | Matches `equipmentService/app/clock.py` |

---

## 4. Design

**Migration `0029_event_registrations.sql`** (dev ends at `0026` and SCRUM-13 claims `0027` and `0028`, so check the next free number before committing):

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
| `app/repositories/registration_repository.py` | **New.** Protocol and Supabase implementation: `register` (RPC), `list_for_attendee`, `count_active`, `list_open_events` |
| `app/services/registration_service.py` | **New.** Role check (attendee only), calls the rules for reads and the RPC for writes, maps RPC errors |
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
| AC1-P1…P9 | Each non-Confirmed status (Draft, Submitted, Under Review, Changes Requested, Rejected, Approved, Planning, Completed, Cancelled) | 404 | A |
| AC1-N1 | Unknown id | 404 | A |
| AC2-H1 | Register for a Confirmed, open, not-full event | 201 (shared setup with AC5-H1) | A |
| AC2-P1…P9 | Register for each of the 9 non-Confirmed statuses | 404, no registration row | U + A |
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
| AC5-X1 | Organiser, coordinator, operations manager try to register | 403, no row | A |
| AC5-X2 | No session on each endpoint | 401 | A |
| AC5-X3 | Browser roles | `anon` and `authenticated` cannot execute `register_for_event` or select `event_registrations` | D |

Before treating a test as done, ask what plausible one-line bug should make it fail (e.g. `<=` vs `<` on capacity → AC4-B2; `>=` vs `>` on `closes_at` → AC3-B5).

---

## 6. Commit sequence (tests first)

| # | Commit | Files | State after |
| --- | --- | --- | --- |
| 0 | *(no commit)* AC review approved; D1 to D9 answered | Jira comment or standup note | — |
| 1 | `docs(scrum-21): record approved contract and test catalogue` | `docs/testcases/scrum_21_testcases.md` | — |
| 2 | `test(scrum-21): add Red unit tests for the registration rules` | `tests/test_registration_rules.py`, `app/services/registration_rules.py` (stubs raising `NotImplementedError`), `app/clock.py` | Unit tests Red |
| 3 | `test(scrum-21): add Red API tests for attendee registration` | `tests/registration_support.py` (fake repository with Confirmed fixtures and an attendee auth stub), `tests/test_registration_api.py` | API tests Red (route 404) |
| 4 | `test(scrum-21): add DB verification for register_for_event` | `database/verify_event_registrations.sql` | Red until the migration |
| 5 | `feat(db): add event registrations and register_for_event (SCRUM-21)` | `0029_event_registrations.sql`, `database/README.md` | DB script Green (disposable local PostgreSQL first) |
| 6 | `feat(event-request): registration rules (SCRUM-21)` | `registration_rules.py` | Unit tests Green |
| 7 | `feat(event-request): attendee event view and registration endpoints (SCRUM-21)` | model, repository, service, controller, `main.py` | Whole service Green, `ruff check .` clean |
| 8 | `docs(scrum-21): document endpoints and record Green evidence` | service README, test catalogue execution record | — |

Run `pytest -q` after commits 2 and 3 and put the Red counts in the commit body. Confirm every Red fails for the intended reason (`NotImplementedError` or route 404), not a fixture error. Don't push red commits to a shared branch.

**Red tests are locked once committed:** in commits 5 to 8, don't edit them to make them pass. If one is wrong, fix it in its own commit with your sign-off.

---

## 7. Increment 2 (after SCRUM-60 merges)

- Frontend attendee page (`frontend/app/events/…`): open-events list, event detail with Register button, "My registrations". Vitest component tests for the empty, full, closed and success states.
- One Playwright journey: log in as `attendee@example.com` → open a Confirmed event → register → see it under My registrations → reload, and it persists.
- Apply `0029` to shared dev; read-only checks of grants; one live API call.

---

## 8. Open questions (take to standup or the PO)

1. D3 window boundaries, D5 duplicates, D8 list: need PO sign-off.
2. Who owns the "set registration window and capacity" story (D2)? Until it exists, live testing needs SQL-seeded values.
3. Should capacity be checked against the confirmed venue's `max_capacity` (Q&A #99)? Proposed: the setter story enforces it, not SCRUM-21.
4. Discussion #127 (separate Open/Closed registration status) is unanswered. This plan derives "open" from the window, so no new status is needed.
5. Add the SCRUM-60 → SCRUM-21 "blocks" link in Jira.

## 9. Done check

`pytest` and `ruff check .` in `backend/eventRequestService`; DB script on a disposable cluster, then shared dev; every test labelled (`grep -rn "AC[1-5]-" backend/eventRequestService/tests`); teammate review of the AI-drafted cases (`testing.md` §10); PR CI green; `definition-of-done.md`.
