# SCRUM-19 — Assign Technical Support Staff to an Event

Source: [Jira SCRUM-19](https://is212g9t4.atlassian.net/browse/SCRUM-19) and `docs/superpowers/plans/2026-10-19-scrum-19-assign-technical-support.md`. Branch: `feat/scrum-19-assign-technical-support`, based on `origin/dev` `a14ed6d` (merged 20 Oct 2026).

> **Status: Approved 20 October 2026.** Yang Xue (story owner) approved the §2 AC wording — including the AC1 narrow-in from E4-2 — and decisions D1–D12 as proposed, and scoped the story to increment 1 (database + backend). PO confirmed D2/D3/D7 as proposed on 21 October 2026 and the 2-to-3-point re-estimate is in Jira (the open questions are closed). The rewording is recorded here, not written back to Jira. Migration numbering: this story takes `0052` — corrected 21 October; SCRUM-65's `0051_venue_block_times.sql` landed on dev first, taking the `0051` this document originally claimed (itself a correction from the plan's `0030`). On 21 October 2026 Yang Xue approved the review-fix plan (`docs/superpowers/plans/2026-10-21-scrum-19-review-fixes.md`), including its §1 sign-off S1, and the three cases it added (AC2-N8, AC2-N9, AC2-X7) are recorded below. Later on 21 October 2026 Yang Xue approved executing the increment-2 plan (`docs/superpowers/plans/2026-10-21-scrum-19-increment-2.md`): AC5-H3 is split into AC5-H3a (mock journey) and AC5-H3b (live manual run), AC5-H4 is added for the inbox rendering, and authService is widened so an `event_coordinator` may list `role=technical_support` (G1, noted under AC4-X1).

## Approved contract

As an Event Coordinator, I want to assign suitable Technical Support Staff to an event that needs on-site support, so that the event's technical needs are covered on the day.

| Jira AC | Outcome | Approved wording |
| --- | --- | --- |
| *(precondition of Jira AC1)* | **Narrow-in from E4-2 (Team Design Proposal)** | **AC1:** Given an Approved, Planning or Confirmed event, when its assigned Coordinator records a technical-support requirement with a description and one skill tag, then the requirement is stored against the event. Any other caller or event status is refused and nothing is stored. |
| For an event that indicated a technical-support requirement, the Coordinator can assign Technical Support Staff. | **Clarify** | **AC2:** Given an Approved, Planning or Confirmed event with a recorded requirement, when its assigned Coordinator assigns a suitable staff member to that requirement, then one assignment is stored. An unknown requirement, a requirement on another event, a disallowed status, a repeat assignment of the same person, or a caller who is not the assigned Coordinator is refused and nothing is stored. |
| "Suitable" … holds the technical-support role/skill tag recorded against the requirement; no availability or double-booking check. | **Keep, clarified** | **AC3:** Given a requirement with skill tag *T*, a person is suitable only if they hold the `technical_support` role **and** tag *T*. The candidate list shows exactly those people; assigning anyone else is refused as not suitable. Being assigned to another event at the same time does not make someone unsuitable. |
| Given a support requirement, when staff are assigned, then the event shows the assigned staff. | **Keep, clarified** | **AC4:** Given an event with requirements, when its assigned Coordinator or any Technical Support Staff member views the event's technical support, then each requirement is listed with its assigned staff (who, assigned by, when) in a stable order, and a requirement with nobody assigned shows an empty list. |
| Assigned staff are notified. | **Clarify** | **AC5:** Given a successful assignment, then the newly assigned staff member, and only they, receives one in-app notification naming the event and requirement. A refused assignment notifies nobody, and a notification failure never undoes the assignment. |

Cross-cutting: no session → 401; role outside the allowed set → 403; an `event_coordinator` who is not the event's latest coordinator → 404; coordinator and status are rechecked inside the locked DB function; `anon` and `authenticated` cannot execute the new functions or read the new tables.

## Decisions

| # | Decision |
| --- | --- |
| D1 | Built in eventRequestService. |
| D2 | `technical_support_requirements (id, event_request_id, description 1–2000 not blank, skill_tag, recorded_by, recorded_at)`. E4-2's when-needed, TSS acknowledgement, clarification thread, notify-on-requirement, edit/delete and reschedule flagging are excluded. **Needs PO confirmation.** |
| D3 | Skill tags: `audio_visual`, `lighting`, `it_network`, `livestream`. Staff tags in `technical_support_skills (user_id, skill_tag)`, seeded by SQL. **Needs PO confirmation.** |
| D4 | Suitable ⇔ `technical_support` role **and** the requirement's tag; one helper `private.is_suitable_technical_support` used by the candidate list and the assign function. No availability check. |
| D5 | Only the latest-assigned coordinator records and assigns. Unrelated coordinator → 404; other roles → 403. |
| D6 | Allowed statuses: `Approved`, `Planning`, `Confirmed`; others → 409 `support_not_allowed`. |
| D7 | One row per (requirement, staff); a repeat → 409 `already_assigned`. Several staff per requirement allowed. **Needs PO confirmation.** |
| D8 | No unassign in this slice. |
| D9 | Notification `technical_support_assigned` to the staff member after commit; `event_id` = assignment id; payload `{event_request_id, event_name, requirement_id, skill_tag, assigned_by}`; failure logged, never raised. |
| D10 | View: latest coordinator or any `technical_support`. Organiser, venue staff, ops manager, attendee → 403. |
| D11 | Candidates: coordinator only; suitable staff ids ascending with `already_assigned`. |
| D12 | New refusals return `{"detail": {"code", "message"}}`. |

## Scope

- **Included:** AC1 to AC5. Endpoints `POST /event-requests/{id}/technical-support/requirements`, `GET /event-requests/{id}/technical-support`, `GET /event-requests/{id}/technical-support/requirements/{rid}/candidates`, `POST /event-requests/{id}/technical-support/requirements/{rid}/assignments`. Coordinator-page panel (increment 2).
- **Excluded:** the rest of E4-2 (no Jira story yet), maintaining staff skill tags in the UI (new story), staff availability and double-booking (Jira AC2, customer clarification #6), unassigning or replacing staff, flagging support assignments on a reschedule (SCRUM-64), a TSS-facing "my assignments" page, notifying on a new requirement.

## Actors and permissions

| Actor | Record requirement | View technical support | List candidates | Assign |
| --- | --- | --- | --- | --- |
| Latest-assigned `event_coordinator` | ✔ | ✔ | ✔ | ✔ |
| Other `event_coordinator` | 404 | 404 | 404 | 404 |
| `technical_support` | 403 | ✔ (any event) | 403 | 403 |
| `event_organiser` (even the owner), `venue_staff`, `event_operations_manager`, `attendee` | 403 | 403 | 403 | 403 |
| No session | 401 | 401 | 401 | 401 |

## Allowed state

Requirements may be recorded and staff assigned only while the event's status is `Approved`, `Planning` or `Confirmed`. No status change is made by this story.

## Persistence and atomicity

`record_technical_support_requirement` and `assign_technical_support_staff` (migration `0052_technical_support_assignments.sql`) lock the `event_requests` row `FOR UPDATE` (the lock shared with coordinator assignment and status transitions), then check, in order: event exists (`P0002`), caller is the latest coordinator (`P0003`), status allowed (`P0004`), requirement exists on this event (`P0002`), staff suitable (`P0005`), then insert (duplicate → `23505`). A refusal writes nothing. The notification is sent by the service only after the RPC returns.

## Assumptions and open questions

1. Approve AC1 narrow-in vs a separate E4-2 story (plan §9.1).
2. D3 tag vocabulary and long-term owner of staff tags.
3. D7 repeat → 409.
4. D10 Organiser visibility (proposed: no).
5. Re-estimate 2 → 3 points.
6. Shared dev has one TSS account; live partition checks need `technical_support2@example.com` (role `technical_support`, tag `lighting`) created through authService.
7. The skill-tag vocabulary is duplicated between the API model and the database CHECK constraints; a single source (domain type or generated list) belongs to the future maintain-staff-skills story (review finding #7).
8. `technical_support_skills.user_id` has no foreign key to `auth.users`; adding one belongs to the same story (review finding #8).

## Fixtures

Unit/API fixtures (in `tests/technical_support_fakes.py`):

| Name | Value | Roles | Skill tags |
| --- | --- | --- | --- |
| `COORD` | `coord-1` | `event_coordinator`, latest on `EVENT` and `OTHER_EVENT` | — |
| `OTHER_COORD` | `coord-2` | `event_coordinator`, on no event | — |
| `TSS_AV` | `tss-av` | `technical_support` | `audio_visual`, `it_network` |
| `TSS_AV2` | `tss-av2` | `technical_support` | `audio_visual` |
| `TSS_LIGHT` | `tss-light` | `technical_support` | `lighting` |
| `TSS_NONE` | `tss-none` | `technical_support` | — |
| `VENUE_AV` | `venue-av` | `venue_staff` | `audio_visual` |
| `ORGANISER` | `org-1` | `event_organiser`, owns `EVENT` | — |
| `OPS` | `ops-1` | `event_operations_manager` | — |
| `ATTENDEE` | `att-1` | `attendee` | — |
| `EVENT` | `11111111-1111-4111-8111-111111111111` | Planning, "Tech Summit 2030", 2030-03-10T09:00+08:00 | — |
| `OTHER_EVENT` | `22222222-2222-4222-8222-222222222222` | Planning, same date and time | — |
| `REQ_AV` | `aaaa0000-0000-4000-8000-000000000001` | on `EVENT`, `audio_visual`, "Two wireless mics and a mixing-desk operator for the keynote" | — |
| `REQ_IT` | `aaaa0000-0000-4000-8000-000000000002` | on `EVENT`, `it_network`, "Venue Wi-Fi for 300 delegates" | — |
| `REQ_OTHER` | `aaaa0000-0000-4000-8000-000000000003` | on `OTHER_EVENT`, `audio_visual` | — |

Live accounts (password `12345678`, `database/seed_test_accounts.sql` + `database/seed_technical_support_skills.sql`): `event_coordinator1@example.com`, `event_coordinator2@example.com`, `technical_support@example.com` (`audio_visual`, `it_network`), `technical_support2@example.com` (`lighting`, to be created), `venue_staff@example.com` (`audio_visual`, no TSS role), `event_organiser@example.com`, `event_operations_manager@example.com`, `attendee@example.com`.

Endpoint shorthand: **REQ-POST** = `POST /event-requests/{EVENT}/technical-support/requirements`; **TS-GET** = `GET /event-requests/{EVENT}/technical-support`; **CAND-GET** = `GET /event-requests/{EVENT}/technical-support/requirements/{rid}/candidates`; **ASSIGN-POST** = `POST /event-requests/{EVENT}/technical-support/requirements/{rid}/assignments`.

## Test case specification

Layers: U = unit (`backend/eventRequestService/tests/test_technical_support_rules.py`), A = API (`tests/test_technical_support_api.py`), R = repository (`tests/test_technical_support_repository.py`), N = notification client (`tests/test_notification_client.py`), D = DB (`database/verify_technical_support_assignments.sql`, `database/verify_technical_support_assignments_race.sh`), F = frontend (`frontend/__tests__/technical-support-panel.test.tsx`, `frontend/__tests__/technical-support-actions.test.ts`, `frontend/__tests__/technical-support-notifications.test.ts`), E = Playwright (`frontend/e2e/assign-technical-support.spec.ts`). authService rows (AC4-X1's staff labels) run in `backend/authService/tests/test_list_technical_support_users.py`. Unless stated, the caller is `COORD`, the event is `EVENT` in Planning and the requirement is `REQ_AV`.

### AC1 — Record a technical-support requirement

| ID | AC | Test scenario | Technique | Pre-conditions | Test steps | Test data | Expected result | Forbidden side effects | Layer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AC1-H1 | AC1 | The assigned coordinator records a requirement on a Planning event | Happy | `EVENT` Planning, latest coordinator `COORD`, no requirements | 1. REQ-POST as `COORD`. 2. TS-GET as `COORD` | `{"description": "Two wireless mics and a mixing-desk operator for the keynote", "skill_tag": "audio_visual"}` | 1. 201; body has `id` (uuid), `event_request_id` = `EVENT`, the description, `skill_tag` `audio_visual`, `recorded_by` `coord-1`, `recorded_at`. 2. One requirement with `assigned_staff: []`. DB: one row with the same values | Event status and `updated_at` unchanged; no notification sent | A + D |
| AC1-P1…P3 | AC1 | Each allowed status accepts a requirement | Partition | `EVENT` in the given status, `COORD` latest | `ensure_support_allowed(status)`; REQ-POST | `Approved` (P1), `Planning` (P2), `Confirmed` (P3) | No error; 201 | Status unchanged | U + A |
| AC1-P4…P10 | AC1 | Each other status refuses a requirement | Partition | `EVENT` in the given status, `COORD` latest | `ensure_support_allowed(status)`; REQ-POST | `Draft` (P4), `Submitted` (P5), `Under Review` (P6), `Changes Requested` (P7), `Rejected` (P8), `Completed` (P9), `Cancelled` (P10) | `SupportNotAllowedError`; 409, `detail.code` `support_not_allowed` | No requirement row; status unchanged | U + A |
| AC1-P11…P14 | AC1 | Each skill tag in the vocabulary is accepted | Partition | as AC1-H1 | Validate `RequirementCreate`; REQ-POST | `audio_visual` (P11), `lighting` (P12), `it_network` (P13), `livestream` (P14) | Valid; 201 with that tag | — | U + A |
| AC1-N1 | AC1 | An unknown skill tag is rejected | Negative | as AC1-H1 | REQ-POST | `skill_tag: "plumbing"` | 422 | No row | A |
| AC1-N2 | AC1 | Tags are case-sensitive | Negative | — | Validate `RequirementCreate` | `skill_tag: "Audio_Visual"` | `ValidationError` | — | U |
| AC1-N3 | AC1 | Missing skill tag or missing description is rejected | Negative | as AC1-H1 | REQ-POST twice | `{"description": "Mics"}`; `{"skill_tag": "lighting"}` | 422 each | No row | A |
| AC1-N4 | AC1 | A coordinator who is not on the event cannot record | Negative | `EVENT` latest coordinator `COORD` | REQ-POST as `OTHER_COORD` | valid body | 404, `detail.code` `event_request_not_found` | No row | A |
| AC1-N5 | AC1 | Unknown event | Negative | Empty repository | REQ-POST to `/event-requests/99999999-9999-4999-8999-999999999999/…` as `COORD` | valid body | 404 | No row | A |
| AC1-N6 | AC1 | The client cannot choose `recorded_by` | Negative | as AC1-H1 | REQ-POST | valid body + `"recorded_by": "coord-2"` | 422 (`extra="forbid"`) | No row | A |
| AC1-B1 | AC1 | Empty description | Boundary | — | Validate; REQ-POST | `""` | `ValidationError`; 422 | No row | U + A |
| AC1-B2 | AC1 | Whitespace-only description | Boundary | — | Validate; REQ-POST | `"   \n\t"` | `ValidationError`; 422 | No row | U + A |
| AC1-B3 | AC1 | Shortest valid description | Boundary | — | Validate | `"A"` | Valid; stored as `"A"` | — | U |
| AC1-B4 | AC1 | Description at the limit | Boundary | as AC1-H1 | Validate; REQ-POST; DB insert | `"x" * 2000` | Valid; 201; DB accepts | — | U + A + D |
| AC1-B5 | AC1 | Description one over the limit | Boundary | as AC1-H1 | Validate; REQ-POST; direct DB insert as `service_role` | `"x" * 2001` | `ValidationError`; 422; DB raises `23514` (check violation) | No row | U + A + D |
| AC1-X1 | AC1 | No other role can record, including the owning organiser and TSS | Cross-cutting | as AC1-H1 | REQ-POST as each role | `ORGANISER`, `TSS_AV`, `VENUE_AV`, `OPS`, `ATTENDEE` | 403 each | No row | A |
| AC1-X2 | AC1 | Reassignment between page load and submit is caught at write time | Cross-cutting | `EVENT` assigned to `COORD`; then a new assignment row to `OTHER_COORD` | Call `record_technical_support_requirement(EVENT, 'coord-1', …)`; then REQ-POST as `COORD` with the fake reassigned | — | `P0003`; 404 | No row | D + A |
| AC1-X3 | AC1 | The form blocks a blank or over-long description and offers exactly the four tags | Cross-cutting | Panel rendered for a Planning event | Type nothing / 2001 chars; open the tag select | — | Submit disabled with message "Describe the support needed" / counter shows 2001/2000 in error style; select lists Audio-visual, Lighting, IT and network, Livestream | No server action call | F |

### AC2 — Assign staff to a requirement

| ID | AC | Test scenario | Technique | Pre-conditions | Test steps | Test data | Expected result | Forbidden side effects | Layer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AC2-H1 | AC2 | The assigned coordinator assigns a suitable staff member | Happy | `REQ_AV` on `EVENT`, no assignments | ASSIGN-POST (`rid` = `REQ_AV`) as `COORD` | `{"staff_id": "tss-av"}` | 201; body `id`, `requirement_id` `REQ_AV`, `event_request_id` `EVENT`, `staff_id` `tss-av`, `assigned_by` `coord-1`, `assigned_at`. DB: one row with those values | Requirement and event unchanged | A + D |
| AC2-H2 | AC2 | Several staff can be assigned to one requirement | Happy | AC2-H1 done | ASSIGN-POST as `COORD` | `{"staff_id": "tss-av2"}` | 201; two rows for `REQ_AV` | `tss-av` row unchanged | A + D |
| AC2-P1…P3 | AC2 | Each allowed status accepts an assignment | Partition | `EVENT` in the given status with `REQ_AV` | ASSIGN-POST `tss-av` | `Approved`, `Planning`, `Confirmed` | 201 | — | U + A |
| AC2-P4…P10 | AC2 | Each other status refuses an assignment | Partition | `REQ_AV` recorded while Planning, then event status set to the given value (fake / SQL) | ASSIGN-POST `tss-av` | `Draft`, `Submitted`, `Under Review`, `Changes Requested`, `Rejected`, `Completed`, `Cancelled` | 409 `support_not_allowed` | No assignment row; no notification | U + A (D: `Cancelled` only) |
| AC2-N1 | AC2 | A requirement that belongs to another event is refused | Negative | `REQ_OTHER` on `OTHER_EVENT`; `COORD` on both | ASSIGN-POST to `EVENT` with `rid` = `REQ_OTHER`; call the DB function the same way | `tss-av` | 404 `requirement_not_found`; `P0002` | No row on either event; no notification | A + D |
| AC2-N2 | AC2 | Unknown requirement id | Negative | `EVENT` with no requirements | ASSIGN-POST `rid` = `aaaa0000-0000-4000-8000-0000000000ff` | `tss-av` | 404 `requirement_not_found` | No row | A |
| AC2-N3 | AC2 | Assigning the same person twice is refused (D7) | Negative | AC2-H1 done | ASSIGN-POST again; direct second insert in DB | `tss-av` | 409 `already_assigned`; DB `23505` | Still one row; exactly one notification in total | A + D |
| AC2-N4 | AC2 | A coordinator who is not on the event cannot assign | Negative | `EVENT` latest `COORD` | ASSIGN-POST as `OTHER_COORD` | `tss-av` | 404 `event_request_not_found` | No row; no notification | A |
| AC2-N5 | AC2 | Reassignment between page load and assign is caught at write time | Negative | `EVENT` reassigned from `COORD` to `OTHER_COORD` after `COORD` loaded the page | DB: `assign_technical_support_staff(EVENT, REQ_AV, 'tss-av', 'coord-1')`; API: fake reassigned, ASSIGN-POST as `COORD` | — | `P0003`; 404 | No row; no notification | D + A |
| AC2-N6 | AC2 | Event cancelled between page load and assign | Negative | `EVENT` Planning with `REQ_AV`; then cancelled via `advance_event_request_by_coordinator(..., 'Cancelled')` | Call `assign_technical_support_staff` | `tss-av` | `P0004` | No row | D |
| AC2-N7 | AC2 | Supabase unavailable | Negative | Fake repository raises `SupabaseRepositoryError` on `assign`; mocked 503 and `httpx.ConnectError` at R | ASSIGN-POST; `repository.assign(...)` | `tss-av` | 502; `SupabaseRepositoryError` (not `TechnicalSupportRpcError`) | No row; **no notification** | A + R |
| AC2-N8 | AC2 | A refused status never reaches the database | Negative | AC2-H1 fixtures; `EVENT` status set to a disallowed value | ASSIGN-POST `tss-av` against a fake subclass that counts RPC calls (`tests/test_technical_support_precheck.py`) | status `Completed`; `tss-av` | 409 `support_not_allowed` and the RPC call count is 0 — the service's own status pre-check refuses first | No assignment row; no notification | A |
| AC2-N9 | AC2 | The wrong-event refusal keeps its exact message, so the 404 mapping cannot drift | Negative | `REQ_OTHER` on `OTHER_EVENT` committed | `assign_technical_support_staff(EVENT, REQ_OTHER, …)`; capture `SQLERRM` | `tss-av2` | `P0002` with `SQLERRM` exactly `technical support requirement not found` | — | D |
| AC2-B1 | AC2 | Blank staff id | Boundary | as AC2-H1 | ASSIGN-POST | `"staff_id": ""` | 422 | No row | A |
| AC2-B2 | AC2 | Staff id at the 64-char limit is accepted for checking | Boundary | as AC2-H1 | ASSIGN-POST | `"s" * 64` (unknown user) | 409 `staff_not_suitable` (passes validation, fails suitability) | No row | A |
| AC2-B3 | AC2 | Staff id over the limit | Boundary | as AC2-H1 | ASSIGN-POST | `"s" * 65` | 422 | No row | A |
| AC2-X1 | AC2 | No other role can assign, including TSS assigning themselves | Cross-cutting | as AC2-H1 | ASSIGN-POST as each role | `ORGANISER`, `TSS_AV` (body `tss-av`), `VENUE_AV`, `OPS`, `ATTENDEE` | 403 each | No row; no notification | A |
| AC2-X2 | AC2 | No session on every endpoint | Cross-cutting | Real auth dependency (no override) | Call REQ-POST, TS-GET, CAND-GET, ASSIGN-POST with no `Authorization` header | — | 401 each | No row | A |
| AC2-X3 | AC2 | The client cannot choose `assigned_by` | Cross-cutting | as AC2-H1 | ASSIGN-POST | `{"staff_id": "tss-av", "assigned_by": "coord-2"}` | 422 | No row | A |
| AC2-X4 | AC2 | Browser roles cannot reach the new functions or tables | Cross-cutting | Local cluster with `0052` | `has_function_privilege` for the three public functions and the private helper; `has_table_privilege` SELECT/INSERT on the three tables | `anon`, `authenticated`, `service_role` | false for `anon`/`authenticated`; `service_role` can execute and select/insert | — | D |
| AC2-X5 | AC2 | Two sessions assign the same person concurrently | Cross-cutting | `REQ_AV` committed, no assignments; two `psql` sessions | Both call `assign_technical_support_staff(EVENT, REQ_AV, 'tss-av', 'coord-1')` at the same time | — | Exactly one row; the other session gets `23505` | Never two rows | D (race script) |
| AC2-X6 | AC2 | Refusals are shown as readable messages in the panel | Cross-cutting | Server action mocked to return each 409 code | Click Assign | `support_not_allowed`, `staff_not_suitable`, `already_assigned` | "Technical support can only be arranged for approved, planning or confirmed events" / "This person doesn't hold the required skill" / "Already assigned to this requirement" | Assigned list not changed | F |
| AC2-X7 | AC2 | The database refuses an assignment whose event disagrees with its requirement's | Cross-cutting | `REQ_OTHER` on `OTHER_EVENT` committed; composite FK from `0052` | Direct insert of `(REQ_OTHER, EVENT, …)` into `technical_support_assignments`, bypassing the function | — | `23503` (`technical_support_assignments_requirement_event_fkey`) | No row | D |

### AC3 — Suitability

| ID | AC | Test scenario | Technique | Pre-conditions | Test steps | Test data | Expected result | Forbidden side effects | Layer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AC3-H1 | AC3 | The candidate list shows exactly the suitable staff | Happy | All fixture users exist; `REQ_AV`; `tss-av` already assigned | CAND-GET (`rid` = `REQ_AV`) as `COORD` | — | 200; `[{"staff_id": "tss-av", "already_assigned": true}, {"staff_id": "tss-av2", "already_assigned": false}]` (ascending id). Absent: `tss-light`, `tss-none`, `venue-av`, `coord-1` | No write | A + D |
| AC3-P1 | AC3 | Role and matching tag → suitable | Partition | — | `is_suitable({"technical_support"}, {"audio_visual"}, "audio_visual")` | — | `True` | — | U |
| AC3-P2 | AC3 | Role but a different tag → not suitable | Partition | `TSS_LIGHT` | `is_suitable(...)`; ASSIGN-POST; DB function | `tss-light` on `REQ_AV` | `False`; 409 `staff_not_suitable`; `P0005` | No row; no notification | U + A + D |
| AC3-P3 | AC3 | Role but no tags → not suitable | Partition | `TSS_NONE` | `is_suitable({"technical_support"}, set(), "audio_visual")`; DB helper | `tss-none` | `False`; helper false | — | U + D |
| AC3-P4 | AC3 | Tag but no `technical_support` role → not suitable | Partition | `VENUE_AV` | `is_suitable({"venue_staff"}, {"audio_visual"}, "audio_visual")`; ASSIGN-POST; DB function | `venue-av` | `False`; 409 `staff_not_suitable`; `P0005` | No row | U + A + D |
| AC3-P5 | AC3 | Role removed after tagging → not suitable at write time | Partition | `tss-av2` tagged; then its `staff_roles` row deleted (in the transaction) | Call `assign_technical_support_staff` | `tss-av2` | `P0005` | No row | D |
| AC3-P6 | AC3 | No one holds the tag → empty list, shown as an empty state | Partition | Requirement on `EVENT` with `livestream`; no one holds it | CAND-GET; render panel with `[]` | — | 200 `[]`; panel shows "No suitable Technical Support Staff hold the Livestream skill" and no Assign button | — | A + F |
| AC3-N1 | AC3 | Unknown user id is "not suitable", not "not found" | Negative | — | ASSIGN-POST; DB function | `staff_id: "ghost-user"` | 409 `staff_not_suitable`; `P0005` (does not reveal whether the account exists) | No row | A + D |
| AC3-X1 | AC3 | No availability or double-booking check | Cross-cutting | `tss-av` assigned to `REQ_OTHER` on `OTHER_EVENT` at the same date and time | CAND-GET for `REQ_AV`; ASSIGN-POST `tss-av` to `REQ_AV` | — | `tss-av` is listed; 201 | — | A + D |
| AC3-X2 | AC3 | A multi-tag staff member is suitable for each of their tags, and only those | Cross-cutting | `TSS_AV` (`audio_visual`, `it_network`) | `is_suitable` for each of the four tags | — | `True` for `audio_visual`, `it_network`; `False` for `lighting`, `livestream` | — | U |
| AC3-X3 | AC3 | Candidate list access | Cross-cutting | as AC3-H1 | CAND-GET as `OTHER_COORD`; as `TSS_AV`, `ORGANISER`, `OPS` | — | 404; 403 each | — | A |
| AC3-X4 | AC3 | The candidate list and the assign function never disagree | Cross-cutting | All fixture users in `auth.users`, `staff_roles`, `technical_support_skills` | For each user: is the user in `list_technical_support_candidates(REQ_AV)`? Does `assign_technical_support_staff` succeed (in a savepoint)? | `tss-av`, `tss-av2`, `tss-light`, `tss-none`, `venue-av`, `coord-1` | Listed ⇔ assign succeeds, for every user | Savepoints rolled back | D |

### AC4 — The event shows its assigned staff

| ID | AC | Test scenario | Technique | Pre-conditions | Test steps | Test data | Expected result | Forbidden side effects | Layer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AC4-H1 | AC4 | The coordinator sees who is assigned | Happy | `REQ_AV` with `tss-av` assigned by `coord-1` | TS-GET as `COORD` | — | 200; `[{"id": REQ_AV, "description", "skill_tag": "audio_visual", "recorded_by", "recorded_at", "assigned_staff": [{"staff_id": "tss-av", "assigned_by": "coord-1", "assigned_at"}]}]` | No write | A |
| AC4-H2 | AC4 | Any Technical Support Staff member sees the same view | Happy | as AC4-H1 | TS-GET as `TSS_LIGHT` (not assigned to anything) | — | 200; same body as AC4-H1 | — | A |
| AC4-P1 | AC4 | A requirement with nobody assigned shows an empty list | Partition | `REQ_IT` recorded, no assignments | TS-GET as `COORD` | — | `REQ_IT` present with `assigned_staff: []` | — | A |
| AC4-P2 | AC4 | Staff are listed under the right requirement only | Partition | `tss-av` and `tss-av2` on `REQ_AV`; only `tss-av` on `REQ_IT` | `group_by_requirement(...)`; TS-GET | — | `REQ_AV` → [`tss-av`, `tss-av2`]; `REQ_IT` → [`tss-av`] only (`tss-av2` not under `REQ_IT`) | — | U + A |
| AC4-P3 | AC4 | An event with no requirements | Partition | `EVENT` with none | TS-GET as `COORD` | — | 200 `[]` | — | A |
| AC4-B1 | AC4 | Stable order when timestamps tie | Boundary | Two requirements with identical `recorded_at`; two assignments with identical `assigned_at` | `group_by_requirement(...)`; repository list query | ids `…01` < `…02`; staff ids `tss-av` < `tss-av2` | Requirements by (`recorded_at`, `id`); staff by (`assigned_at`, `id`); repository orders by `recorded_at.asc,id.asc` and `assigned_at.asc,id.asc` | — | U + R |
| AC4-N1 | AC4 | View access is refused correctly | Negative | as AC4-H1 | TS-GET as `OTHER_COORD`; as `ORGANISER`, `VENUE_AV`, `OPS`, `ATTENDEE`; for an unknown event as `COORD` | — | 404; 403 each; 404 | — | A |
| AC4-X1 | AC4 | The view leaks nothing beyond the agreed fields, and the coordinator page shows emails | Cross-cutting | as AC4-H1; staff list from `/auth/users?role=technical_support` mocked | TS-GET keys; render panel | `tss-av` → `technical_support@example.com` | Keys exactly as AC4-H1 (no `organiser_id`, event fields or notes); panel shows "technical_support@example.com", falls back to the id when the email is unknown | — | A + F |

G1 (increment 2, approved 21 October): the AC4-X1 staff labels need `GET /auth/users?role=technical_support`, which authService previously granted only to `admin`. It is widened so an `event_coordinator` may list `role=technical_support` only — every other role stays refused — so the panel shows emails instead of unusable UUID fallbacks (see `backend/authService/tests/test_list_technical_support_users.py`).

### AC5 — Assigned staff are notified

| ID | AC | Test scenario | Technique | Pre-conditions | Test steps | Test data | Expected result | Forbidden side effects | Layer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AC5-H1 | AC5 | A successful assignment sends one notification to the staff member | Happy | `RecordingNotificationClient`; `respx`/`httpx` mock at N | ASSIGN-POST `tss-av`; call `notify_technical_support_assigned(...)` directly | — | Exactly one call / one POST to the configured URL with `{"event_type": "technical_support_assigned", "recipient_id": "tss-av", "event_id": <assignment id>, "payload": {"event_request_id": EVENT, "event_name": "Tech Summit 2030", "requirement_id": REQ_AV, "skill_tag": "audio_visual", "assigned_by": "coord-1"}}` | Not sent to `coord-1`, the organiser or other TSS | A + N |
| AC5-H2 | AC5 | Only the newly assigned person is notified | Happy | `tss-av` already assigned and notified | ASSIGN-POST `tss-av2` | — | One new call, recipient `tss-av2` | No second notification to `tss-av` | A |
| AC5-H3 | AC5 | The staff member sees the notification in their inbox | Happy | Local stack (or shared dev) with `0052`; seeded Planning event assigned to `event_coordinator1@example.com` with an AV requirement | 1. Log in as `event_coordinator1@example.com` / `12345678`. 2. Open the event under Coordination. 3. Choose `technical_support@example.com`, click Assign. 4. Log out; log in as `technical_support@example.com`. 5. Open Notifications. 6. Reload | — | Step 3: listed under the requirement. Step 5: a notification naming "Tech Summit…" and the requirement. Step 6: both still shown | — | E — split 21 Oct (increment-2 plan G3) into AC5-H3a (mock journey) and AC5-H3b (live manual run); this row stays as the umbrella |
| AC5-H3a | AC5 | The staff member sees the notice in their inbox — journey against the Playwright mock stack | Happy | `e2e/support/*.mjs` mocks; seeded Planning event "Tech Summit 2030" assigned to the coordinator; the mock event-request API does not call notificationService, so the spec seeds via `__seed` the notice the real service would have written (emission itself is AC5-H1's proof) | 1. Log in as `coordinator@example.com`. 2. Open `/coordination/requests/{id}`. 3. Record an audio-visual requirement. 4. Assign `technical_support@example.com`. 5. Switch to the `tech-session` (`technical_support` role). 6. Open Notifications. 7. Reload | Mock password `test-password-123` | Step 4: the assignment is listed under the requirement. Step 6: the inbox shows "You've been assigned as Audio-visual support for Tech Summit 2030." with no link. Step 7: it is still there | The coordinator's own inbox gains nothing; a refused action leaves the requirement list unchanged | E |
| AC5-H3b | AC5 | The staff member sees the notification in their inbox — live shared-dev run | Happy | Shared dev with `0052` + `seed_technical_support_skills.sql`; live accounts per Fixtures | Steps as AC5-H3 with the live accounts (`event_coordinator1@example.com` → `technical_support@example.com`) | Password `12345678` | Step 3: listed under the requirement. Step 5: the notification names the event and the requirement. Step 6: both still shown | Evidence is screenshots recorded separately from local and CI results | E (manual) |
| AC5-H4 | AC5 | The inbox renders the assignment notice for the assigned staff member | Happy | The inbox rendering called with a `technical_support_assigned` notice | Call `describeNotification` with payload `{event_request_id, event_name: "Tech Summit 2030", skill_tag: "audio_visual", assigned_by}`; again with `event_name` missing | — | "You've been assigned as Audio-visual support for Tech Summit 2030." with `href` null (a TSS page is out of scope); without `event_name` still a sentence naming the skill | — | F |
| AC5-N1 | AC5 | A refused assignment notifies nobody | Negative | Each refusal set up as in its own case | ASSIGN-POST for each refusal | 409 `support_not_allowed`, `staff_not_suitable`, `already_assigned`; 404 (unrelated coordinator, wrong requirement); 403 (`OPS`); 502 | Zero notification calls in every case | — | A (parametrised, ids per refusal) |
| AC5-N2 | AC5 | A notification failure never undoes the assignment | Negative | notificationService returns 500; then raises `httpx.ConnectError` | ASSIGN-POST `tss-av`; call the client directly | — | 201 and the row is kept; client returns `None` and logs one `WARNING` naming the staff id and event | No exception escapes; no rollback | A + N |
| AC5-X1 | AC5 | Notifications are idempotent and skipped when not configured | Cross-cutting | (a) URL unset; (b) the same assignment notified twice against the real `notifications` table | (a) call the client; (b) insert twice with the same `(recipient_id, event_id)` | — | (a) no HTTP call; (b) one notification row (existing `notifications_recipient_event_key`) | — | N + D |

**ID count:** AC1 29, AC2 31, AC3 12, AC4 8, AC5 9 = **89 IDs** (ranges counted individually; 70 rows — recounted 21 Oct when AC5-H3a/H3b/H4 were added; the previous "61 rows" no longer matched the tables after the review additions).

## Coverage check

| AC | Happy | Partition | Boundary | Negative | Cross-cutting |
| --- | --- | --- | --- | --- | --- |
| AC1 | H1 | P1–P14 (status ×10, tag ×4) | B1–B5 (description 0 / blank / 1 / 2000 / 2001) | N1–N6 | X1 roles, X2 reassignment race, X3 UI |
| AC2 | H1, H2 | P1–P10 (status ×10) | B1–B3 (staff id 0 / 64 / 65) | N1–N9 | X1 roles, X2 401, X3 forged actor, X4 grants, X5 race, X6 UI, X7 event pairing |
| AC3 | H1 | P1–P6 (role × tag) | — (no numeric boundary; empty list is P6) | N1 | X1 no availability, X2 multi-tag, X3 access, X4 list = write |
| AC4 | H1, H2 | P1–P3 | B1 ordering tie | N1 | X1 field whitelist + UI |
| AC5 | H1, H2, H3 / H3a (mock), H3b (live manual), H4 (F) | — | — | N1, N2 | X1 idempotency / unset URL |

## Review corrections (21 October 2026)

A code review of commits `8aa0a73`…`79835b3` (findings and fixes:
`docs/superpowers/plans/2026-10-21-scrum-19-review-fixes.md`) audited the
tests this matrix records. The test edits already made during the sprint are
recorded here so the Red → Green chain stays honest:

1. `4d1488a` corrected three Red tests while reaching Green: AC5-N2 (A) was
   rewritten to drive the real `NotificationClient` over a monkeypatched
   `httpx.post` instead of the recording fake's `fail` flag; the AC4 expected
   timestamps use the `Z` form pydantic serializes; the AC4-P1 fixture gained
   the assigned-staff contrast it asserts against.
2. `53b2bcb` corrected three DB-verifier fixture bugs from the Green run, none
   of them migration defects: the AC3-H1 candidate expectation moved before
   AC2-H2 assigns the second staff member, the post-reassignment assign now
   records and assigns on a fresh audio-visual requirement the new coordinator
   owns, and the race script's loser output needed `2>&1`.
3. **S1, signed off by Yang Xue on 21 October 2026:** the `4d1488a` rewrite of
   AC5-N2 is reverted to the `b821d54` oracle — the recording fake's `fail`
   flag raising `RuntimeError` — because the rewritten case let the real
   client swallow the failure, so the service's own handling of a raising
   notifier went untested. Commit R1a restores the test, R1b makes it pass.

## Latest execution record

| ID | Automation status | Actual result | Execution status | Build or commit | Executed by and date | Remarks and evidence |
| --- | --- | --- | --- | --- | --- | --- |
| AC1-*, AC2-*, AC3-*, AC4-*, AC5-* (U) | Green | 31 passed | Pass | `216df55` Red (18 failed / 13 passed, all failures `NotImplementedError`); `ba46c50` Green | Claude, local, 20 Oct 2026 | `pytest tests/test_technical_support_rules.py`; rules implemented in `ba46c50` |
| AC1-*, AC2-*, AC3-*, AC4-*, AC5-* (A) | Green | 87 passed | Pass | `b821d54` Red (76 failed / 11 passed; all failures plain route 404, the 11 pass vacuously on 4xx-only or bare-404 assertions); `4d1488a` Green | Claude, local, 20 Oct 2026 | `pytest tests/test_technical_support_api.py`; repository faked with the database functions' check order (`technical_support_fakes.py`) |
| AC2-N7, AC4-B1 (R) | Green | 15 passed | Pass | `e5c3b85` Red (NotImplementedError); `4d1488a` Green | Claude, local, 20 Oct 2026 | `pytest tests/test_technical_support_repository.py`; httpx MockTransport against the Supabase shapes |
| AC5-H1, AC5-N2, AC5-X1a (N) | Green | 16 passed (11 pre-existing + 5 new) | Pass | `e5c3b85` Red (`AttributeError: notify_technical_support_assigned`); `4d1488a` Green | Claude, local, 20 Oct 2026 | `pytest tests/test_notification_client.py`; `httpx.post` monkeypatched |
| Whole service | Green | 691 passed, 1 skipped | Pass | `4d1488a` | Claude, local, 20 Oct 2026 | `ruff check .` clean; `pytest -q` (554 baseline + 137 new); dependencies mocked, no live Supabase |
| AC1-H1/B4/B5/X2, AC2-H1/H2/P10/N1/N3/N5/N6/X4, AC3-H1/P2–P5/N1/X1/X4, AC5-X1b (D) | Green | ALL SCRUM-19 TECHNICAL SUPPORT VERIFICATIONS PASSED (rolled back) | Pass | `fe579dd` Red (`relation "public.technical_support_requirements" does not exist`); `75bcf34` Green | Claude, disposable docker `postgres:16` cluster `scrum19-verify-pg`, 20 Oct 2026 | Cluster built by `python3 -I database/tests/bootstrap_safety_review.py --disposable --dsn postgresql://postgres@127.0.0.1:5432/scrum48_scrum19 --psql <docker wrapper> --through 0052_technical_support_assignments.sql` (the file was named `0051_…` when this run happened; renamed 21 Oct after SCRUM-65 took `0051`, contents unchanged); verifier run via `psql -X -v ON_ERROR_STOP=1`. Two mid-run failures were verifier fixture bugs (a stale `already_assigned` expectation, an unsuitable staff choice), not migration defects; corrected in `53b2bcb` |
| AC2-X5 (D race) | Green | RACE VERIFICATION PASSED: one row; the loser hit the unique constraint | Pass | `75bcf34` | Claude, same disposable cluster, 20 Oct 2026 | `verify_technical_support_assignments_race.sh` run inside the container; leaves one Cancelled event and its organiser behind (status history immutable) |
| AC5-N2 (A) | Red → Green | R1a `b71b860` Red: `RuntimeError("notification service down")` escaped the service (1 failed, 86 passed); R1b `8ee0998` Green: 201, row kept | Pass | `b71b860`/`8ee0998` | Claude, local, 21 Oct 2026 | S1 restoration to the `b821d54` oracle; `pytest tests/test_technical_support_api.py` |
| AC2-N8 (A) | Red → Green | R2a `5f67024` Red: `assert 1 == 0` on `rpc_calls` (the assign RPC was made); R2b `5cb17f2` Green: 409 `support_not_allowed`, 0 calls, no row | Pass | `5f67024`/`5cb17f2` | Claude, local, 21 Oct 2026 | `pytest tests/test_technical_support_precheck.py` |
| AC2-N9, AC2-X7 (D) | Red → Green | R3/R4a `087b7ce` Red on the unmodified 0052: AC2-X7's wrong-event insert accepted (psql exit 3); R3/R4b `b522397` Green: ALL SCRUM-19 TECHNICAL SUPPORT VERIFICATIONS PASSED (exit 0), both cases included | Pass | `087b7ce`/`b522397` | Claude, fresh disposable docker `postgres:16` cluster `scrum19-reviewfix-pg`, 21 Oct 2026 | Cluster rebuilt from scratch through the new `0052` via `bootstrap_safety_review.py --disposable --through 0052_technical_support_assignments.sql`; AC2-N9 passed both runs (it pins existing behaviour) |
| AC2-X5 (D race, rerun) | Green | RACE VERIFICATION PASSED: one row; the loser hit the unique constraint | Pass | `b522397` | Claude, same fresh cluster, 21 Oct 2026 | Race script rerun after the composite-FK change |
| Whole service (review fixes) | Green | 695 passed, 1 skipped (694 baseline + AC2-N8); `ruff check .` clean | Pass | `12795db` (R7) | Claude, local, 21 Oct 2026 | `pytest -q`; R7 made zero test changes (`git diff --stat` on `tests/` empty) |
| AC2-N9, AC2-X7, AC2-X4 (CI database-verify) | Green | Job "Verify the SCRUM-19 database schema" success; whole Backend CI run success (11/11 jobs) | Pass | `c535a34`, dispatched run 39617016083 | Workflow dispatch on `feat/scrum-19-assign-technical-support`, 21 Oct 2026 | [Run](https://github.com/jarenlimhaan/spm/actions/runs/39617016083): postgres:16 service container, migrations through `0052`, verifier with `ON_ERROR_STOP=1`; backend jobs green on the same run |
| AC4-X1 (G1, authService) | Red → Green | `798d091` Red: coordinator listing `role=technical_support` got 403 (`assert 403 == 200`; 1 failed / 13 passed — the 13 pin the refusals that survive). `141bccb` Green: 60 passed (46 existing + 14 new), `ruff check .` clean | Pass | `798d091`/`141bccb` | Claude, local, 21 Oct 2026 | `backend/authService`: `pytest tests/test_list_technical_support_users.py` then `pytest -q`; mocked dependencies, no live Supabase. Two new tests AC4-X1 and AC4-X1a–l and regression cases live in `tests/test_list_technical_support_users.py` |
| AC1-X3, AC2-X6, AC3-P6, AC4-X1 (F) | Red → Green | `51705b1` Red: 3 new files, 35 cases — notifications 6 failed / 0 passed on the default-inbox branch (the G2 gap); actions + panel files failed to resolve their not-yet-written modules. `3a073c4` Green | Pass | `51705b1`/`3a073c4` | Claude, local, 21 Oct 2026 | `frontend/__tests__/technical-support-panel.test.tsx`, `technical-support-actions.test.ts`, `technical-support-notifications.test.ts`; vitest/jsdom, APIs mocked. Two Red-test data bugs corrected while reaching Green (both in the panel test): `getAllByText` for the repeated "Recorded by" line, and the labels test now renders an empty requirement so "Nobody assigned yet" can appear |
| AC5-H4 (F) | Red → Green | Same run as the F row: Red 6 failed on the default branch; Green renders "You've been assigned as Audio-visual support for Tech Summit 2030." with `href` null, each tag's label, and the missing-event-name sentence | Pass | `51705b1`/`3a073c4` | Claude, local, 21 Oct 2026 | `frontend/__tests__/technical-support-notifications.test.ts` |
| Frontend suite (whole) | Green | 460 passed, 0 failed (43 files; 425 pre-existing + 35 new); `npm run lint`, `npm run typecheck`, `npm run build` clean | Pass | `3a073c4` | Claude, local, 21 Oct 2026 | `npm test` in `frontend/`; no pre-existing test file edited |
| AC5-H3a (E) | Green | Coordinator records an AV requirement on a seeded Planning event, assigns `technical_support@example.com`, sees the assignment and the all-assigned state; the TSS inbox shows the AC5-H4 message and keeps it across reload | Pass | `a96c772` | Claude, local Chromium via the Playwright mock webServers, 21 Oct 2026 | `npx playwright test` — 46 passed (45 pre-existing + 1 new), 0 failed; notice seeded via `__seed` (no cross-service write in the mocks), so emission evidence stays AC5-H1 |
| AC5-H3b (E, live) | Planned | — | Not executed | — | — | Blocked for this session: shared dev has not had `0052` + `seed_technical_support_skills.sql` applied (migrations go through the Supabase dashboard/SQL editor), and `technical_support2@example.com` does not exist yet. Manual run with screenshots remains |
| Whole branch (CI) | Green | All 16 checks success: frontend lint/typecheck/build, unit tests, end-to-end tests, all five backend services (lint, test, container build), "Verify the SCRUM-19 database schema", conventional commits | Pass | `0d01996`, branch push (not the PR) | GitHub Actions on push, 21 Oct 2026 | Branch `feat/scrum-19-assign-technical-support` pushed 21 Oct; frontend-ci has no `workflow_dispatch`, so PR CI runs when the pull request opens — this push-level run is the equivalent evidence until then |

Scope note (plan §1): increment 1 delivered commits `8aa0a73`…`4d1488a` on
`feat/scrum-19-assign-technical-support`, hardened by the review fixes
`8eb3304`…`c535a34` (21 Oct 2026, review-fix plan §3). Increment 2 (21 Oct
2026, increment-2 plan) delivered commits `5658584`…`a96c772`: the authService
widening (G1), the frontend panel and inbox rendering (AC1-X3, AC2-X6, AC3-P6,
AC4-X1, AC5-H4), and the mock e2e journey (AC5-H3a). Remaining before Done:
shared-dev application of `0052` and the seed, `technical_support2@example.com`,
live grant checks, the AC5-H3b manual run and PR CI.
Closed 21 Oct: PO confirmed D2/D3/D7 as proposed. Still open: teammate review
of these AI-drafted cases (`testing.md` §10).
