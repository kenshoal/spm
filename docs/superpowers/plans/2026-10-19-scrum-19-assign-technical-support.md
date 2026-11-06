# SCRUM-19 Implementation Plan: Assign Technical Support Staff to an Event

Drafted 19 October 2026 by Claude (Cowork) for Yang Xue (story owner). **Status: approved 20 October 2026 — Yang Xue (story owner) approved the §2 AC wording (AC1 narrow-in) and D1–D12 as proposed, and scoped delivery to increment 1 (commits 1–9). D2/D3/D7 stay flagged for PO confirmation at standup (§9).**

**Goal:** The assigned Event Coordinator records what technical support an event needs (with one skill tag), assigns Technical Support Staff who hold that skill, sees who is assigned on the event, and the assigned staff are told.

**Source of truth:** issue tracker SCRUM-19 (Sprint 3, 2 points, Lowest) and spm-brain (`backlog/user-stories.md` M4-3 and E4-2; `backlog/customer-clarifications.md` #6; Q&A #25, #66, #87, #88, #89). Once §2 is approved, the contract and test catalogue live in `docs/testcases/scrum_19_testcases.md`. This plan only says *how* to build it.

**Branch:** `feat/scrum-19-assign-technical-support`, 20 Oct 2026 even with `origin/dev` `a14ed6d`. PR into `dev`.

---

## 1. Dependencies and gaps

| Story / artefact | State (19 Oct) | Effect on SCRUM-19 |
| --- | --- | --- |
| *(no issue tracker story)* E4-2 Record a Technical Support Requirement | Backlog card only, "prerequisite for M4-3" | **Gap.** issue tracker AC1's precondition ("an event that indicated a technical-support requirement") has nothing in the schema to point at. `event_requests` has only free-text `equipment_requirements`; `equipment_requirements` (SCRUM-33) is equipment, not people. See D2 |
| *(no table)* Staff skill tags | — | **Gap.** issue tracker AC2 defines "suitable" by a skill tag, but `staff_roles` holds roles only. See D3 |
| SCRUM-14 Assign Coordinator | Done | Reused: "latest assignment is the caller" decides who may assign support (`event_coordinator_assignments`, highest `id`) |
| SCRUM-37 In-app notifications | Done | Reused: `NotificationClient` → `POST /notifications/events`; `notifications_recipient_event_key` dedupes retries by `event_id` |
| SCRUM-58 Plan and Confirm | In Progress (Approved → Planning merged) | Planning exists in dev, so all three allowed statuses can be seeded |
| SCRUM-64 Flag Affected Arrangements for Review (Heng Rui) | In Progress | **Out of scope here.** If SCRUM-64 wants support assignments flagged on a date change, it builds on the table this story adds. Tell Heng Rui the table name at standup |
| SCRUM-62 Event Coordinator Lead | To Do | None. Coordinator reassignment already moves the right to assign support (AC2-N5) |
| Migrations | dev ends at `0026`; SCRUM-13 uses `0027`/`0028`; SCRUM-21 uses `0029` | ~~This story takes **`0030`**~~. ~~Corrected 20 Oct: this story takes `0051`~~. **Corrected 21 Oct: SCRUM-65's `0051_venue_block_times.sql` merged to dev first, so this story takes `0052`** — as the plan itself required, the next free number was re-checked before committing |

**Why this fits in the sprint:** it is the SCRUM-14 pattern (role + relationship check, locked RPC, best-effort notification) applied to a new child table. Sprint 3 ends **22 Oct**, so increment 1 (DB + backend, all five ACs at API level) is the sprint target; increment 2 (frontend panel + Playwright) follows if time allows (§8).

**Proportionality flag:** 2 points was estimated before the D2/D3 gaps were visible. Recording the requirement (AC1) and the skills table add roughly a point. Raise at standup; do not silently absorb it.

---

## 2. AC review gate (approve before commit 1)

| issue tracker AC | Outcome | Proposed wording |
| --- | --- | --- |
| *(none: precondition of issue tracker AC1)* | **Narrow-in from E4-2 (Team Design Proposal)** | **AC1:** Given an Approved, Planning or Confirmed event, when its assigned Coordinator records a technical-support requirement with a description and one skill tag, then the requirement is stored against the event. Any other caller or event status is refused and nothing is stored. |
| For an event that indicated a technical-support requirement, the Coordinator can assign Technical Support Staff. | **Clarify** | **AC2:** Given an Approved, Planning or Confirmed event with a recorded requirement, when its assigned Coordinator assigns a suitable staff member to that requirement, then one assignment is stored. An unknown requirement, a requirement on another event, a disallowed status, a repeat assignment of the same person, or a caller who is not the assigned Coordinator is refused and nothing is stored. |
| "Suitable" for this release means the staff member holds the technical-support role/skill tag recorded against the requirement; the system does not check staff scheduling availability or double-booking in this slice. | **Keep, clarified** | **AC3:** Given a requirement with skill tag *T*, a person is suitable only if they hold the `technical_support` role **and** tag *T*. The candidate list shows exactly those people; assigning anyone else is refused as not suitable. Being assigned to another event at the same time does not make someone unsuitable. |
| Given a support requirement, when staff are assigned, then the event shows the assigned staff. | **Keep, clarified** | **AC4:** Given an event with requirements, when its assigned Coordinator or any Technical Support Staff member views the event's technical support, then each requirement is listed with its assigned staff (who, assigned by, when) in a stable order, and a requirement with nobody assigned shows an empty list. |
| Assigned staff are notified. | **Clarify** | **AC5:** Given a successful assignment, then the newly assigned staff member, and only they, receives one in-app notification naming the event and requirement. A refused assignment notifies nobody, and a notification failure never undoes the assignment. |

**Cross-cutting (all ACs, `security-and-state.md` §2):** no session → 401; a role outside the allowed set → 403; an `event_coordinator` who is not the event's latest coordinator → 404 (do not disclose the event); the coordinator and the event status are rechecked inside the locked DB function, not only at page load; browser roles (`anon`, `authenticated`) cannot execute the new functions or read the new tables.

**Expected scope change:** +1 AC (AC1) and +2 tables versus the issue tracker text. If the PO prefers, AC1 can instead become its own story (E4-2 slice) that blocks SCRUM-19; then SCRUM-19 tests seed requirements by SQL and the live journey waits for that story.

---

## 3. Decisions to approve

| # | Decision | Proposal | Why |
| --- | --- | --- | --- |
| D1 | Service | **eventRequestService.** It owns `event_requests` and `event_coordinator_assignments`, so status and coordinator are checked under one row lock | Same as SCRUM-14, SCRUM-21, SCRUM-58 |
| D2 | Requirement record | New `technical_support_requirements`: `id, event_request_id, description (1–2000 chars, not blank), skill_tag, recorded_by, recorded_at`. **Excluded from E4-2:** when-needed (before/during), TSS acknowledgement statuses, clarification thread (#87), notify-on-new-requirement, edit/delete, flag-on-reschedule | Smallest record that makes issue tracker AC1–AC3 testable |
| D3 | Skill tags | Fixed vocabulary: `audio_visual`, `lighting`, `it_network`, `livestream` (CHECK constraint + Python `StrEnum`). Staff tags in `technical_support_skills (user_id varchar(64), skill_tag, PRIMARY KEY (user_id, skill_tag))`, **seeded by SQL**. A screen to maintain staff skills is a new story | issue tracker AC2 needs a tag; Q&A #89 lets us propose how availability/suitability data is kept |
| D4 | Suitability rule | Suitable ⇔ `staff_roles` has (`user_id`, `technical_support`) **and** `technical_support_skills` has (`user_id`, requirement's tag). One SQL helper `private.is_suitable_technical_support(p_staff_id, p_skill_tag)` used by both the candidate list and the assign function. No availability or double-booking check | issue tracker AC2 verbatim; one source of truth so the list and the write never disagree |
| D5 | Who records and assigns | Only the **latest-assigned** `event_coordinator`. Unrelated coordinator → 404; other roles → 403 | `security-and-state.md` §2; matches `GET /event-requests/{id}` |
| D6 | Allowed event statuses | `Approved`, `Planning`, `Confirmed`. All others → 409 `support_not_allowed` | README: "venue and equipment work begins only after approval"; Completed/Cancelled/Rejected are terminal |
| D7 | Repeat assignment | One row per (requirement, staff). A repeat is 409 `already_assigned` (unique constraint → `23505`). Several different staff per requirement are allowed | Not in the issue tracker ACs, so needs PO sign-off (`testing.md` §6) |
| D8 | Unassign | **Out of scope** (no AC). Assignments are append-only in this slice | Keep within 2–3 points |
| D9 | Notification | After the DB commit, `NotificationClient.notify_technical_support_assigned(...)`: `event_type = "technical_support_assigned"`, `recipient_id = staff_id`, `event_id = assignment id`, payload `{event_request_id, event_name, requirement_id, skill_tag, assigned_by}`. Failure is logged, never raised | Existing SCRUM-37 contract; `event_id` makes retries idempotent |
| D10 | Who can view | `GET …/technical-support`: latest coordinator, or any `technical_support` (Q&A #66: TSS not restricted by type). Organiser, venue staff, ops manager, attendee → 403 | issue tracker AC3 names "the event"; staff need to see what they are on |
| D11 | Candidate list | `GET …/requirements/{rid}/candidates` (coordinator only) returns suitable staff ids sorted ascending, each with `already_assigned`. Emails come from authService `GET /auth/users?role=technical_support` in the frontend, like `coordinatorLabel` | Avoids a cross-service call in the backend |
| D12 | Error body | `{"detail": {"code": "<code>", "message": "<text>"}}` for the new 404/409 codes; 401/403/422 stay as FastAPI defaults | Lets tests assert the specific failure (`testing.md` §6) |

---

## 4. Design

### Migration `0030_technical_support_assignments.sql` (safe to re-run)

```sql
-- tables
technical_support_requirements (
  id uuid PK DEFAULT gen_random_uuid(),
  event_request_id uuid NOT NULL REFERENCES event_requests(id),
  description varchar NOT NULL CHECK (btrim(description) <> '' AND char_length(description) <= 2000),
  skill_tag varchar NOT NULL CHECK (skill_tag IN ('audio_visual','lighting','it_network','livestream')),
  recorded_by varchar(64) NOT NULL,
  recorded_at timestamptz NOT NULL DEFAULT now()
);
INDEX (event_request_id, recorded_at, id);

technical_support_skills (
  user_id varchar(64) NOT NULL,
  skill_tag varchar NOT NULL CHECK (same four),
  PRIMARY KEY (user_id, skill_tag)
);

technical_support_assignments (
  id uuid PK DEFAULT gen_random_uuid(),
  requirement_id uuid NOT NULL REFERENCES technical_support_requirements(id),
  event_request_id uuid NOT NULL REFERENCES event_requests(id),   -- denormalised for the per-event read
  staff_id varchar(64) NOT NULL,
  assigned_by varchar(64) NOT NULL,
  assigned_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT technical_support_assignments_once UNIQUE (requirement_id, staff_id)   -- D7
);
INDEX (event_request_id, assigned_at, id);
```

- RLS on all three, no policies; `REVOKE ALL … FROM anon, authenticated`; `GRANT SELECT, INSERT … TO service_role` (pattern `0011`, `0017`, `0021`).
- `private.is_suitable_technical_support(p_staff_id varchar, p_skill_tag varchar) RETURNS boolean` (D4).
- `record_technical_support_requirement(p_event_request_id uuid, p_coordinator_id varchar, p_description text, p_skill_tag varchar) RETURNS technical_support_requirements`
- `assign_technical_support_staff(p_event_request_id uuid, p_requirement_id uuid, p_staff_id varchar, p_coordinator_id varchar) RETURNS technical_support_assignments`
- `list_technical_support_candidates(p_requirement_id uuid) RETURNS TABLE (staff_id varchar, already_assigned boolean)`

Both write functions are `SECURITY INVOKER`, `SET search_path = ''`, and do, in order:

1. `SELECT … FROM event_requests WHERE id = p_event_request_id FOR UPDATE` (the same row lock as `assign_event_request_coordinator` and `advance_event_request_by_coordinator`, so a reassignment or cancellation cannot interleave). Missing → `P0002 'event request not found'`.
2. Latest `coordinator_id` (`ORDER BY id DESC LIMIT 1`) ≠ caller → `P0003 'caller is not the assigned coordinator'`.
3. Status not in (`Approved`, `Planning`, `Confirmed`) → `P0004 'technical support not allowed from status %'`.
4. *(assign only)* Requirement missing **or** `requirement.event_request_id <> p_event_request_id` → `P0002 'technical support requirement not found'`.
5. *(assign only)* `NOT private.is_suitable_technical_support(p_staff_id, requirement.skill_tag)` → `P0005 'staff member is not suitable'`.
6. Insert and return. A duplicate raises `23505` from the unique constraint.

`REVOKE EXECUTE … FROM PUBLIC, anon, authenticated; GRANT EXECUTE … TO service_role` on all three public functions and the private helper.

**Seed (`database/seed_technical_support_skills.sql`, dev only, re-runnable):** `technical_support@example.com` → `audio_visual`, `it_network`; `venue_staff@example.com` → `audio_visual` (the "tag without role" fixture). Optional: create `technical_support2@example.com` (role `technical_support`, tag `lighting`) through authService so the live partition check has a TSS who is *not* suitable for an AV requirement.

### Backend files (eventRequestService)

| File | Change |
| --- | --- |
| `app/models/technical_support.py` | **New.** `SkillTag(StrEnum)`; `RequirementCreate` (`description: str` stripped, 1–2000; `skill_tag: SkillTag`; `extra="forbid"`); `AssignmentCreate` (`staff_id: str` 1–64, `extra="forbid"`); `RequirementResponse`, `AssignmentResponse`, `CandidateResponse`, `EventTechnicalSupportResponse` (requirement + `assigned_staff: list[AssignedStaff]`) |
| `app/services/technical_support_rules.py` | **New, pure.** `SUPPORT_STATUSES`; `ensure_support_allowed(status)` → `SupportNotAllowedError`; `is_suitable(roles, tags, skill_tag) -> bool` (mirror of D4 for unit tests and the fake); `group_by_requirement(requirements, assignments)` (ordering for AC4) |
| `app/repositories/technical_support_repository.py` | **New.** `TechnicalSupportRepository` Protocol + Supabase impl: `record_requirement` (RPC), `assign` (RPC), `list_candidates` (RPC), `list_requirements(event_id)`, `list_assignments(event_id)`. `TechnicalSupportRpcError(errcode, reason)`; transport failures stay `SupabaseRepositoryError` |
| `app/services/technical_support_service.py` | **New.** Role gate (D5/D10), coordinator relationship pre-check via the existing coordinator repository (for 404 on read endpoints), RPC error mapping (`P0002`→404 `requirement_not_found` / `event_request_not_found`, `P0003`→404, `P0004`→409 `support_not_allowed`, `P0005`→409 `staff_not_suitable`, `23505`→409 `already_assigned`), notification after success only |
| `app/controllers/technical_support_controller.py` | **New.** Routes below |
| `app/services/notification_client.py` | Add `notify_technical_support_assigned(...)` (D9) |
| `app/main.py` | `create_app(..., technical_support_repository=None)`; include router; exception handlers (D12) |
| `README.md` | Endpoint table rows; migration note |

### Endpoints

| Method and path | Who | Success | Refusals |
| --- | --- | --- | --- |
| `POST /event-requests/{id}/technical-support/requirements` | latest coordinator | 201 `RequirementResponse` | 401, 403, 404, 409 `support_not_allowed`, 422 |
| `GET /event-requests/{id}/technical-support` | latest coordinator, any TSS | 200 `list[EventTechnicalSupportResponse]` | 401, 403, 404 |
| `GET /event-requests/{id}/technical-support/requirements/{rid}/candidates` | latest coordinator | 200 `list[CandidateResponse]` | 401, 403, 404 |
| `POST /event-requests/{id}/technical-support/requirements/{rid}/assignments` | latest coordinator | 201 `AssignmentResponse` | 401, 403, 404, 409 `support_not_allowed` / `staff_not_suitable` / `already_assigned`, 422, 502 |

### Frontend (increment 2)

| File | Change |
| --- | --- |
| `frontend/lib/technical-support.ts` | **New.** Types, API calls, `SKILL_TAG_LABELS`, `staffLabel(id, staff)` |
| `frontend/app/coordination/requests/[id]/technical-support-panel.tsx` | **New.** Record-requirement form (description with 2000-char counter, skill-tag select); per requirement: assigned staff (email labels), candidate select, Assign button, empty states ("No suitable Technical Support Staff hold the Lighting skill", "Nobody assigned yet") and mapped 409 messages |
| `frontend/app/coordination/actions.ts` | Server actions `recordSupportRequirement`, `assignSupportStaff` |
| `frontend/app/coordination/requests/[id]/page.tsx` | Render the panel for Approved/Planning/Confirmed |

---

## 5. Test catalogue summary

Full rows (pre-conditions, steps, data, expected result, forbidden side effects) are in `docs/testcases/scrum_19_testcases.md`. **83 case IDs** (58 rows): AC1 29, AC2 28, AC3 12, AC4 8, AC5 6.

| Layer | File | Cases |
| --- | --- | --- |
| U unit | `backend/eventRequestService/tests/test_technical_support_rules.py` | status partitions, suitability partitions, description boundaries, tag partitions, AC4 ordering |
| A API | `tests/test_technical_support_api.py` + `tests/technical_support_fakes.py` | every endpoint × role × relationship; error mapping; notification calls via a recording fake client |
| R repository | `tests/test_technical_support_repository.py` | RPC payloads, errcode parsing, transport errors, read query filters/order |
| N notification | `tests/test_notification_client.py` (extend) | request body, unset URL, HTTP failure logged |
| D database | `database/verify_technical_support_assignments.sql`, `database/verify_technical_support_assignments_race.sh` | constraints, lock-time rechecks, suitability helper, grants, concurrency |
| F frontend | `frontend/__tests__/technical-support-panel.test.tsx`, `frontend/__tests__/technical-support-actions.test.ts` | rendering states, validation, error messages |
| E end-to-end | `frontend/e2e/assign-technical-support.spec.ts` + `e2e/support/technical-support-api.mjs` | one coordinator → TSS journey |

Plausible one-line bugs the catalogue must catch (`testing.md` §2):

| Bug | Caught by |
| --- | --- |
| Suitability checks role **or** tag instead of **and** | AC3-P3, AC3-P4 |
| Suitability compares the staff's tag to a constant, not the requirement's tag | AC3-P2, AC3-X2 |
| Candidate list and assign function use different rules | AC3-H1 + AC3-P2 at D layer |
| Requirement id not checked against the path's event | AC2-N1 |
| Relationship checked against *any* past coordinator, not the latest | AC2-N5 |
| `char_length(description) < 2000` instead of `<= 2000` | AC1-B4 |
| Status list includes `Under Review` or omits `Confirmed` | AC1-P3, AC1-P6, AC2-P* |
| Notification sent before the insert, or on refusal | AC5-N1 |
| Notification exception propagates → 500 | AC5-N2 |
| Every assigned staff member re-notified on each new assignment | AC5-H2 |
| An availability check sneaks in | AC3-X1 |

---

## 6. Commit sequence (tests first)

| # | Commit | Files | State after |
| --- | --- | --- | --- |
| 0 | *(no commit)* AC review and D1–D12 approved | issue tracker comment / standup note | — |
| 1 | `docs(scrum-19): record approved contract and test catalogue` | `docs/testcases/scrum_19_testcases.md`, this plan | — |
| 2 | `test(scrum-19): add Red unit tests for the technical support rules` | `tests/test_technical_support_rules.py`, `app/services/technical_support_rules.py` (stubs raising `NotImplementedError`), `app/models/technical_support.py` | Unit Red |
| 3 | `test(scrum-19): add Red API tests for technical support assignment` | `tests/technical_support_fakes.py`, `tests/test_technical_support_api.py`, stub `technical_support_repository.py` + `TechnicalSupportRpcError`, `create_app` param | API Red (route 404) |
| 4 | `test(scrum-19): add Red repository and notification tests` | `tests/test_technical_support_repository.py`, extend `tests/test_notification_client.py` | Red (`NotImplementedError` / `AttributeError` on the new method) |
| 5 | `test(scrum-19): add DB verification for technical support assignment` | `database/verify_technical_support_assignments.sql`, `…_race.sh` | Red until `0030` |
| 6 | `feat(database): add technical support requirements and assignments (SCRUM-19)` | `0030_technical_support_assignments.sql`, `seed_technical_support_skills.sql`, `database/README.md` | DB Green on disposable PostgreSQL 16 |
| 7 | `feat(event-request): technical support rules (SCRUM-19)` | `technical_support_rules.py` | Unit Green |
| 8 | `feat(event-request): technical support endpoints and notification (SCRUM-19)` | repository, service, controller, notification client, `main.py` | Whole service Green, `ruff check .` clean |
| 9 | `docs(scrum-19): document endpoints and record Green evidence` | service README, execution record | Increment 1 done |
| 10 | `test(frontend): add Red tests for the technical support panel (SCRUM-19)` | `__tests__/technical-support-*.test.ts(x)` | Red |
| 11 | `feat(frontend): technical support panel on the coordination request page (SCRUM-19)` | lib, panel, actions, page | Vitest Green; lint/typecheck/build clean |
| 12 | `test(e2e): assign technical support journey (SCRUM-19)` | `e2e/assign-technical-support.spec.ts`, `e2e/support/technical-support-api.mjs` | Green against local stack |

Run `pytest -q` after commits 2–4 and put the Red counts in the commit body; each Red must fail for the intended reason (`NotImplementedError`, route 404, missing method), never a fixture error. Do not push red commits. **Red tests are locked once committed:** if one is wrong, fix it in its own commit with Yang's sign-off.

---

## 7. Test data and environments

| Environment | How data is created | Reset |
| --- | --- | --- |
| Unit / API | In-memory `FakeEventRequestRepository`, `FakeCoordinatorAssignmentRepository`, `FakeTechnicalSupportRepository` (mirrors the DB function order: lock → coordinator → status → requirement → suitability → unique), `RecordingNotificationClient` | New instances per test; no shared state |
| DB | `database/tests/bootstrap_event_status_history.py` builds a disposable PostgreSQL 16 cluster; apply `0026`, `0030`; script inserts its own `auth.users`, `staff_roles`, skills, events and assignments inside `BEGIN … ROLLBACK` | Rolled back each run. Race script commits two fixtures and leaves one Cancelled event (status history is immutable) |
| Shared dev (Supabase) | `0030` + `seed_technical_support_skills.sql`; event created via API as `event_organiser@example.com`, assigned to `event_coordinator1@example.com`, moved to Planning | Read-only grant checks only; live API run uses a fresh event each time |
| E2E | `e2e/support/technical-support-api.mjs` seeds a Planning event through the APIs | New event per run |

Fixture ids used throughout the catalogue (unit/API):

| Name | Value | Roles | Skill tags |
| --- | --- | --- | --- |
| `COORD` | `coord-1` | `event_coordinator` (latest on `EVENT`) | — |
| `OTHER_COORD` | `coord-2` | `event_coordinator` (not on `EVENT`) | — |
| `TSS_AV` | `tss-av` | `technical_support` | `audio_visual`, `it_network` |
| `TSS_AV2` | `tss-av2` | `technical_support` | `audio_visual` |
| `TSS_LIGHT` | `tss-light` | `technical_support` | `lighting` |
| `TSS_NONE` | `tss-none` | `technical_support` | — |
| `VENUE_AV` | `venue-av` | `venue_staff` | `audio_visual` |
| `ORGANISER` | `org-1` | `event_organiser` (owns `EVENT`) | — |
| `OPS` | `ops-1` | `event_operations_manager` | — |
| `ATTENDEE` | `att-1` | `attendee` | — |
| `EVENT` | `11111111-1111-4111-8111-111111111111` | Planning, `event_name` "Tech Summit 2030", `proposed_date_times` [2030-03-10T09:00+08] | — |
| `OTHER_EVENT` | `22222222-2222-4222-8222-222222222222` | Planning, same date, coordinator `coord-1` | — |
| `REQ_AV` | `aaaa0000-0000-4000-8000-000000000001` | on `EVENT`, `audio_visual`, "Two wireless mics and a mixing-desk operator for the keynote" | — |
| `REQ_IT` | `aaaa0000-0000-4000-8000-000000000002` | on `EVENT`, `it_network` | — |
| `REQ_OTHER` | `aaaa0000-0000-4000-8000-000000000003` | on `OTHER_EVENT`, `audio_visual` | — |

---

## 8. Increment plan

- **Increment 1 (target 22 Oct, sprint end):** commits 1–9. All five ACs proven at U/A/R/N/D layers; local and disposable-DB evidence.
- **Increment 2 (next sprint if needed):** commits 10–12, apply `0030` to shared dev, live grant checks, one live API run, PR CI.

## 9. Open questions (standup / PO)

1. Approve the AC1 narrow-in from E4-2, or split it into its own story? (§2)
2. D3 skill-tag vocabulary: are the four tags right? Who will maintain staff tags long-term (new story)?
3. D7 repeat assignment refused with 409: confirm.
4. D10 should the Organiser see who is supporting their event? Proposed no for this slice.
5. Re-estimate: 2 → 3 points?
6. Tell Heng Rui (SCRUM-64) about `technical_support_assignments` in case date changes should flag them.

## 10. Done check

`ruff check .` and `pytest` in `backend/eventRequestService`; DB script and race script on a disposable cluster, then grant checks on shared dev; every test labelled (`grep -rn "AC[1-5]-" backend/eventRequestService/tests database frontend/__tests__ frontend/e2e`); teammate review of the AI-drafted cases (`testing.md` §10); PR CI green; `definition-of-done.md`.
