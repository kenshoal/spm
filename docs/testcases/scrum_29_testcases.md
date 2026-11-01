# SCRUM-29 — Update Event Information

Source: [Jira SCRUM-29](https://is212g9t4.atlassian.net/browse/SCRUM-29). The AC wording below is the **approved Jira pull of 1 November 2026**; **Jira remains the source of truth.**

Status (1 Nov 2026): **AI-drafted test design from the approved ACs, teammate review pending (`testing.md` §10).** Labels in the test files read `SCRUM-29 AC<n>-<L><k>` (story-prefixed, following the `SCRUM-38 AC4-X1` precedent) because the shared files carry SCRUM-8/11/35/39/60 labels. Nothing was executed in this pass: the matrix and the labels were added; every execution row below is `Not executed`.

## Story contract

### Acceptance criteria

- **AC1:** Authorised users can view and edit relevant information for an event they have access to.
- **AC2:** The system distinguishes ordinary edits from significant changes — those that may affect arrangements already made (date/time, expected attendance, venue requirements, equipment requirements).
- **AC3:** Given a significant change, when saved, then the affected arrangements are flagged for review. (The flag itself is built in SCRUM-64; this story triggers it.)
- **AC4:** Given an ordinary edit, when saved, then no arrangement review is triggered.

### Dependencies (as recorded in Jira, 1 Nov 2026)

| Dependency | Effect on this story |
| --- | --- |
| SCRUM-64 (flag) — **built** (`database/migrations/0031_arrangement_review_event_changes.sql`) | AC3's flag raising is SCRUM-64's private audit trigger; SCRUM-29 owns *triggering* it with a significant save, not the flag's lifecycle |
| SCRUM-58 (Approved → Planning) | Editing during Planning is shown end-to-end only once SCRUM-58 lets an event move into Planning; **until then SCRUM-29's editing is built and tested on Approved events** (and, in the current code, on Drafts — see open question 1) |
| SCRUM-35 (post-approval change requests) | SCRUM-35 uses the **same significant-fields list**. The list is tested **once, here (SCRUM-29)**, and referenced from SCRUM-35; SCRUM-29 is not blocked by SCRUM-35 |

### Scope

| | Behaviour | Owner |
| --- | --- | --- |
| Included | Viewing and editing the nine organiser-editable fields through the request's edit endpoint (AC1) | SCRUM-29 |
| Included | The significant-vs-ordinary classification of an edit and the four-field significant list (AC2 — one partition row per significant field, tested once here and referenced from SCRUM-35) | SCRUM-29 |
| Included | Triggering SCRUM-64's arrangement-review flag with a significant save; ordinary saves raising nothing (AC3, AC4) | SCRUM-29 |
| Excluded | The flag's storage, read API, clearing and review workflow | SCRUM-64 |
| Excluded | The post-approval change-request workflow (proposal, approval, its own audit) — SCRUM-29's AC column cross-references it as an edit path for Approved events | SCRUM-35 |
| Excluded | The Approved → Planning transition and Planning-stage editing UI | SCRUM-58 |
| Excluded | Relationship-based read access and attendee/public projections | SCRUM-39 |
| Excluded | Draft save/create semantics themselves (the AC1-H1/P1 rows reuse SCRUM-8/SCRUM-11's endpoint) | SCRUM-8 / SCRUM-11 |

### Actors and permissions

- **Event Organiser (owner):** the only actor who can currently edit through `PATCH /event-requests/{id}`; the repository scopes the write to the request id, the verified organiser and the editable status (`AC1-P1`).
- **Authorised viewers:** an authorised user reads only a request they have access to; the read is scoped to id + owner at the repository (`AC1-P2`), and relationship-based access is SCRUM-39's.
- **Another organiser:** 404, and the stored event is unchanged (SCRUM-8's labelled test — named, not claimed, `AC1-N1`).

### Allowed state transitions

| From | To | Trigger |
| --- | --- | --- |
| `Draft` | `Draft` | AC1 edit (the endpoint's current editable state) |
| `Approved` / `Planning` | unchanged | AC1 edit once SCRUM-58 opens Planning-stage editing; today post-approval edits arrive through SCRUM-35's approved change request |

No status change ever results from an edit save itself.

### Persistence and atomicity

- An edit is **one** owner-scoped PATCH writing only the changed values (`AC1-P1`); a blank string normalises to a cleared field (`AC1-H1`).
- A significant save and its arrangement-review flags commit together in the database transaction: `0031`'s private trigger raises one review per live affected arrangement, sharing one trigger UUID per save (`AC3-P1`), and no client role can insert a review directly (`AC3-X1`).

### Assumptions and open questions

1. **Requirement vs code (flagged, not resolved here):** AC1 says "an event they have access to", but today `PATCH /event-requests/{id}` is scoped to `Draft` status — an Approved event cannot be edited through it (the SCRUM-11-labelled read-only test proves the 409). Post-approval edits currently arrive through SCRUM-35's change-request workflow, whose approval writes the fields. The Jira dependency note (built/tested on Approved events; Planning editing waits for SCRUM-58) is recorded as the contract; the endpoint's status scoping is a design decision for the story owner to confirm against Jira.
2. `0031`'s trigger skips `Draft` and terminal statuses, so AC3/AC4 flags can only arise for saves on non-Draft events — today reachable via SCRUM-35's approved change, and later via direct Planning-stage edits (SCRUM-58).
3. The four significant fields and the blank-equivalence rule (`nullif(btrim(…))` — blank text equals absent text) are implemented in `0031`; SCRUM-29 tests the list once (AC2, AC2-B1) and SCRUM-35 references it.
4. The DB-level proof of the flag behaviour lives in SCRUM-64's own script (`database/verify_arrangement_review_flags.sql`) under SCRUM-64's matrix IDs; those rows are named in the execution record as cross-references, **not claimed**. SCRUM-29's own AC2–AC4 rows are gaps until the story owner writes SCRUM-29-labelled cases through SCRUM-29's save path.
5. `backend/eventRequestService/tests/test_event_planning.py` is wholly SCRUM-58's (module docstring and labels); no test there evidences SCRUM-29's ACs, so nothing was labelled in it. `test_arrangement_reviews.py` is wholly SCRUM-64's AC5 read contract — the flag TRIGGER is not exercised there either, so nothing was labelled in it.

### How to run the suites

| Area | Command |
| --- | --- |
| Event-request service | `cd backend/eventRequestService && .venv/bin/pytest` |
| SCRUM-64's cross-referenced flag oracle | `psql -X -v ON_ERROR_STOP=1 -f database/verify_arrangement_review_flags.sql` on a disposable cluster (SCRUM-64's file — named, not claimed) |
| Gates | `ruff check .` (backend), `npm run lint` / `npm run typecheck` / `npm run build` (frontend) |

## Test case specification

Layers: API = `backend/eventRequestService/tests/test_event_request_controller.py`; R = repository (`tests/test_supabase_repository.py`); DB = the planned SCRUM-29 database cases (cross-references point at `database/verify_arrangement_review_flags.sql`, SCRUM-64's).

| ID | AC | Test scenario | Technique | Pre-conditions | Test steps | Test data | Expected result | Forbidden side effects | Layer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AC1-H1 | AC1 | An authorised organiser's edit updates the same record and can clear a field | Happy | Organiser owns a saved request with a name and purpose | PATCH `/event-requests/{id}` with a new name and an empty purpose | "Original" / "Initial purpose" → "Updated" / "" | 200; same id; name updated; purpose cleared to null | No second request row is created | API |
| AC1-P1 | AC1 | An edit is one PATCH scoped to id, owner and editable status | Partition | Mock-transport repository | `repository.update_for_organiser(...)`; capture the request | `{event_name: "Updated"}` | PATCH `/rest/v1/event_requests` filtered `id`, `organiser_id`, editable `status`; body is only the new values | No other table or call is touched | R |
| AC1-P2 | AC1 | A view is scoped to id and owner | Partition | Mock-transport repository | `repository.get_for_organiser("request-1", "organiser-1")` | — | Query carries `id eq request-1` and `organiser_id eq organiser-1`; the row is returned | No other organiser's row is readable | R |
| AC1-N1 | AC1 | Another organiser cannot edit someone else's event | Negative | Foreign owner's request; caller is `ORGANISER_ID` | GET, PATCH and DELETE the foreign id | `event_name: "Changed"` | All 404; the stored name is unchanged | No mutation of the foreign event (SCRUM-8's labelled test — named, not claimed) | API |
| AC1-N2 | AC1 | Direct editing is refused once the request has left its editable state | Negative | Submitted request | PATCH it, submit again, delete it; GET it | `complete_payload()` | 409 on all three mutations; GET 200 with the original values | Values unchanged by the refused calls (SCRUM-11's labelled test — named, not claimed) | API |
| AC2-P1 | AC2, AC3 | `proposed_date_times` is a significant field | Partition | Non-Draft event with live arrangements | Change only the date/times; save | one slot moved | The save is classified significant; the affected arrangements are flagged (AC3) | Ordinary fields untouched | DB |
| AC2-P2 | AC2, AC3 | `expected_attendance` is a significant field | Partition | As AC2-P1 | Change only the attendance | 50 → 80 | Significant; flagged | — | DB |
| AC2-P3 | AC2, AC3 | `venue_requirements` is a significant field | Partition | As AC2-P1; live venue booking | Change only the venue text | "Seminar room…" → "Accessible hall…" | Significant; the venue booking is flagged | — | DB |
| AC2-P4 | AC2, AC3 | `equipment_requirements` is a significant field | Partition | As AC2-P1; live reservation | Change only the equipment text | "Projector…" → "Projector and two microphones" | Significant; the reservation is flagged | — | DB |
| AC2-P5 | AC2 | Ordinary fields are never significant | Partition | Non-Draft event with live arrangements | Change only ordinary fields (event name, purpose, description, accessibility, registration) in separate saves | "Renamed event" | Save succeeds; no arrangement review is raised | No review row for any ordinary save | DB |
| AC2-B1 | AC2 | Blank-equivalent requirement text is not a change | Boundary | venue_requirements blank vs whitespace-only | Save between blank-equivalent values | `"  "` → `""` | Not classified significant; no flag | No review row | DB |
| AC3-H1 | AC3 | A significant edit flags the affected live arrangements | Happy | Non-Draft event; an approved future venue booking and a reservation | Make a significant save; inspect `arrangement_reviews` | attendance 50 → 80 | One flagged review per live affected arrangement, carrying the changed fields and a reason | No flag without live arrangements | DB |
| AC3-P1 | AC3, AC2 | One save flags each affected domain once under one trigger identity | Partition | Booking and reservation both live; save touches attendance and both requirement texts | Inspect the raised rows | — | A venue row and an equipment row share one trigger UUID; a later save gets a distinct one | No duplicate rows per arrangement | DB |
| AC3-N1 | AC3 | Expired or absent arrangements are not flagged | Negative | Arrangements ended before today | Significant save | — | No review rows | No stale flags | DB |
| AC3-X1 | AC3 | Only the database can raise flags | Cross-cutting | Migrated cluster with `0031` | Privilege checks on `arrangement_reviews` and the trigger function | `anon`, `authenticated`, `service_role` | Clients cannot insert reviews or execute the trigger; `service_role` is SELECT-only | No fabricated flags | DB |
| AC4-H1 | AC4 | An ordinary edit triggers no arrangement review | Happy | Non-Draft event with live arrangements | Change `event_name` only; save; count reviews | "Renamed event" | Save succeeds; the review count is unchanged | No review row | DB |
| AC4-P1 | AC4 | Each ordinary field saves without a flag | Partition | As AC4-H1; one save per ordinary field | Change each of the five ordinary fields in turn | — | No review row for any of them | — | DB |

## Latest execution record

This pass (1 November 2026) designed the matrix from the approved ACs and added label comments only; **no suite was run**, so every row is **Not executed** (`testing.md` §8). "Automated (label added in this pass)" marks tests labelled on this branch; "Automated (existing test)" marks tests that already carry another story's label and are named, not claimed; "Planned" rows are gaps — SCRUM-29 story owner to write.

| ID | Automation status | Actual result | Execution status | Build or commit | Executed by and date | Remarks and evidence |
| --- | --- | --- | --- | --- | --- | --- |
| AC1-H1 | Automated (label added in this pass) | Not run in this pass | Not executed | working tree, `docs/testcase-gap-sweep`, labels only | Claude for Yang Xue, 1 Nov 2026 | `backend/eventRequestService/tests/test_event_request_controller.py::test_patch_updates_the_same_draft_and_can_clear_a_field` |
| AC1-P1, AC1-P2 | Automated (label added in this pass) | Not run in this pass | Not executed | as above | Claude for Yang Xue, 1 Nov 2026 | `backend/eventRequestService/tests/test_supabase_repository.py::test_update_scopes_query_to_owner_and_draft_status` and `::test_get_scopes_query_to_organiser` |
| AC1-N1 | Automated (existing test) | Not run in this pass | Not executed | as above | Claude for Yang Xue, 1 Nov 2026 | `test_event_request_controller.py::test_other_organiser_cannot_read_update_or_delete`, already labelled `SCRUM-8 AC4-N1` — named, not claimed |
| AC1-N2 | Automated (existing test) | Not run in this pass | Not executed | as above | Claude for Yang Xue, 1 Nov 2026 | `test_event_request_controller.py::test_submitted_request_is_read_only`, already labelled `SCRUM-11 AC7-N1` — named, not claimed |
| AC2-P1…P5, AC2-B1, AC3-H1, AC3-P1, AC3-N1, AC3-X1, AC4-H1, AC4-P1 | Planned | — | Not executed | — | — | gap: no SCRUM-29-labelled automated test yet — story owner to write the DB cases through SCRUM-29's save path. The behaviour is implemented in `database/migrations/0031_arrangement_review_event_changes.sql` (significant field list, blank-equivalence, per-domain flags, one trigger UUID, privilege revocations) and is proven today only inside SCRUM-64's `database/verify_arrangement_review_flags.sql` under SCRUM-64's own matrix IDs (its AC1/AC2 rows) — named, not claimed. SCRUM-35 references this same list (tested once here, AC2-P1…P5) |
