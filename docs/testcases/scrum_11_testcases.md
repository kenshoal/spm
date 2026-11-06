# SCRUM-11 — Submit an Event Request

Source: [Jira SCRUM-11](https://is212g9t4.atlassian.net/browse/SCRUM-11) (title "Submit an Event Request"; the Jira user-story sentence is not recorded in the September catalogue and is not restated here).

Status (converted 1 Nov 2026): **AI-drafted conversion of the September catalogue to the `testing.md` matrix format; teammate review pending (`testing.md` §10).** The AC wording below follows the September catalogue's recorded AC table (AC summaries kept, restated as scenario rules); **Jira remains the source of truth.** Labels in the test files read `SCRUM-11 AC<n>-<L><k>` (story-prefixed, following the `SCRUM-38 AC4-X1` precedent) so they cannot be confused with SCRUM-8 or SCRUM-39 labels in the same files. Nothing was executed in this pass: the matrix and the labels were added; every execution row below is `Not executed`.

## Story contract

### Acceptance criteria

- **AC1:** Only the request's responsible organiser may submit, and only while the request is a `Draft` — another organiser's request and any non-Draft request cannot be submitted.
- **AC2:** A submission carries the nine-field minimum (event name, purpose, description, at least one timezone-aware date/time, positive attendance, and all four requirement fields); a requirement field may hold a real need or the placeholders `Not required` / `Not known yet`.
- **AC3:** Expected attendance is stored once, as one event-level value, for later venue checks — never duplicated into `venue_requirements`.
- **AC4:** A refused submission lists every missing item, creates nothing, and leaves the draft an editable `Draft`.
- **AC5:** A successful submission moves the existing Draft to `Submitted` under the same request ID, preserving the saved values.
- **AC6:** Submission assigns no Coordinator; responsibility begins only through SCRUM-14.
- **AC7:** After submission the responsible organiser can view the request, but edit, resubmission and deletion are refused and the original values remain.
- **AC8:** Each successful submission records exactly one durable `event_request.submitted` outbox event, committed together with the request change; failed or repeated attempts add no event, and a later notification consumer uses the outbox event UUID for idempotent delivery.

### Scope

| | Behaviour | Owner |
| --- | --- | --- |
| Included | Owner-only, Draft-only submission and the Draft → Submitted transition (AC1, AC5) | SCRUM-11 |
| Included | The nine-field submission minimum, placeholder wording and validation refusals (AC2, AC4) | SCRUM-11 |
| Included | One event-level attendance value (AC3, shared validation with SCRUM-8) | SCRUM-11 |
| Included | The Submitted read-only state and its UI (AC7) | SCRUM-11 |
| Included | Exactly one `event_request.submitted` outbox event per submission (AC8, migration `0008`/`0009` and `verify_event_request_submission_outbox.sql`) | SCRUM-11 |
| Excluded | Draft saving itself (SCRUM-8); the value hand-over rows are shared (SCRUM-8 AC7) | SCRUM-8 |
| Excluded | Coordinator assignment — a submission must not create one (AC6), but assignment itself is SCRUM-14's story | SCRUM-14 |
| Excluded | Outbox notification delivery: a later consumer reads the outbox; delivery is that workflow's concern and must be idempotent by event UUID | notification-consumer story |
| Excluded | `Completed` data (depends on an agreed `eventService` integration) and any `Submitted` → `Draft` reversal (the September catalogue deferred both to future stories) | future stories |

The September catalogue records that **submission of an existing Draft is the Jira-required story path**; direct submission of a complete new form (`POST /event-requests/submissions`) is supported behaviour on the branch and is kept as partition cases under AC5.

### Actors and permissions

- **Event Organiser (owner):** the only actor who can submit; the endpoint takes the request id and the verified organiser id, and the single PATCH filters on id + owner + `Draft` status (`AC1-P1`).
- **Another organiser:** 404, and the draft stays `Draft` (`AC1-N1`).
- **Authenticated non-organiser roles:** 403 `Insufficient permissions` before any data is accessed (`AC1-X1`).
- **Coordinator:** gains responsibility only through a SCRUM-14 assignment; submission creates none (`AC6`).

### Allowed state transitions

| From | To | Trigger |
| --- | --- | --- |
| `Draft` | `Submitted` | AC5, owner submits a complete request (also from no row via the direct path, AC5-P1) |
| `Submitted` | `Submitted` | refused repeat (409, AC7) |

Everything past `Submitted` (Under Review, …) is owned by the coordinator stories.

### Persistence and atomicity

- Submission is **one** owner-scoped PATCH: `id = request`, `organiser_id = caller`, `status = Draft`, writing the new values plus `Submitted` (`AC1-P1`). Nothing is written when the filters do not all match.
- The outbox row and the request change live in the same database transaction: a trigger (`private.enqueue_event_request_submitted`) inserts into `event_request_outbox`, guarded by `UNIQUE (event_request_id, event_type)` and `ON CONFLICT DO NOTHING`, so a repeated status write cannot duplicate the event (`AC8-H1`, `AC8-X1`). A Draft insert fires nothing (`AC8-N1`).
- The table is service-only: RLS enabled, all access revoked from `anon`/`authenticated`, granted to `service_role`, trigger function not executable by application roles (migration `0008`; checked manually in September — see gap `AC8-X2`).

### Assumptions and open questions

1. The 422 refusal body is FastAPI/Pydantic's field-level detail, which does name every missing field; no automated test asserts that body (gap `AC4-N2`).
2. No automated test asserts the *absence* of a coordinator assignment on submit (gap `AC6-N1`); the one-PATCH contract (`AC1-P1`) supports it indirectly because the captured request touches only `event_requests`.
3. The attendance boundary (`gt 0`) is proven through the draft-create endpoint (`AC3-B1`), where the same request model validates; no test posts attendance 0 to a submit endpoint itself.
4. The September suite counts (44 backend / 24 frontend / 4 e2e) are stale; run the suites for current numbers.

### How to run the suites (folded from the September catalogue)

| Area | Command |
| --- | --- |
| Event-request service | `cd backend/eventRequestService && uv run --extra dev --locked pytest` |
| Frontend components and actions | `cd frontend && npm test` |
| Frontend browser journeys | `cd frontend && npm run test:e2e` |
| Outbox database verification | `database/verify_event_request_submission_outbox.sql` after `0008_event_request_submission_outbox.sql`; every mutation rolled back, so it leaves no data behind |
| Gates | `ruff check .` (backend), `npm run lint` / `npm run typecheck` / `npm run build` (frontend) |

## Test case specification

Layers: API = `backend/eventRequestService/tests/test_event_request_controller.py`; R = repository (`tests/test_supabase_repository.py`); DB = `database/verify_event_request_submission_outbox.sql`; UI-A = server actions (`frontend/__tests__/event-request-actions.test.ts`); UI-C = components (`frontend/__tests__/page.test.tsx`); E2E = `frontend/e2e/home.spec.ts`. The API tests run the FastAPI app against a faked repository (`make_client`, `ORGANISER_ID = 11111111-…-111111111111`, `OTHER_ORGANISER_ID = 22222222-…-222222222222`); `complete_payload()` is the nine-field form (attendance 80, one `+08:00` date time).

| ID | AC | Test scenario | Technique | Pre-conditions | Test steps | Test data | Expected result | Forbidden side effects | Layer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AC1-N1 | AC1 | Another organiser cannot submit a draft | Negative | Repository seeded with `OTHER_ORGANISER_ID`'s complete Draft; caller is `ORGANISER_ID` | POST `/event-requests/{id}/submit` with the complete payload | `complete_payload()` | 404; the row still reads `Draft` | No status change; no new row | API |
| AC1-P1 | AC1, AC5, AC6 | Submission is one PATCH scoped to id, owner and Draft | Partition | Mock-transport repository | `repository.submit_for_organiser(...)`; capture the request | values `{event_name: "Complete request"}` | PATCH `/rest/v1/event_requests` filtered `id`, `organiser_id`, `status eq Draft`; body is exactly the new values plus `status: Submitted`; result Submitted | No other table or call touched — no assignment write | R |
| AC1-X1 | AC1 | Only authenticated event organisers reach submission | Cross-cutting | Session mocked with each non-organiser role set | POST `/event-requests/submissions`, once per role | roles attendee, admin, event_operations_manager | 403 `Insufficient permissions` for each | Nothing stored | API |
| AC2-P1 | AC2, AC4 | Omitting any one required field refuses submission and stores nothing | Partition | Repository empty; complete payload minus one field | POST `/event-requests/submissions` once per field (9 parametrized cases) | each of the nine fields popped in turn | 422 for every case; `repository.rows` stays empty | No request row for any incomplete variant | API |
| AC2-P2 | AC2, AC8 | `Not required` / `Not known yet` placeholders are valid requirement values | Partition | Migrated cluster, rollback-only script | INSERT a Submitted row whose four requirement fields are placeholders | "Not known yet" / "Not required" ×4, attendance 20 | Row stored; exactly one outbox event | — | DB |
| AC2-N1 | AC2, AC4 | Timezone-unaware dates are refused | Negative | Repository empty | POST `/event-requests/submissions` with a naive date string | `"2026-10-20T10:00:00"` (no offset) | 422; repository stays empty | No row | API |
| AC3-H1 | AC3; SCRUM-8 AC2 | Attendance is one top-level value, not duplicated into venue requirements | Partition | Organiser session | Save the complete payload; read it back | attendance 80; venue "Classroom with movable tables" | `expected_attendance` round-trips as its own column; `venue_requirements` holds only its own text | Attendance never copied into another field | API |
| AC3-B1 | AC3; SCRUM-8 AC2 | Attendance just below the minimum is refused | Boundary | Organiser session | POST with `expected_attendance: 0` (shared request model also guards the submit paths) | 0 (minimum is 1) | 422 | Nothing persisted | API |
| AC3-B2 | AC3; SCRUM-8 AC2 | Attendance below the minimum is stopped at the frontend | Boundary | Server action, fetch stubbed | `createEventRequest` with attendance "0" | `"0"` | Field error "Enter a whole number greater than zero."; fetch never called | No request sent | UI-A |
| AC4-N1 | AC4 | A refused submission leaves the draft editable | Negative | Organiser owns an incomplete Draft | POST `/event-requests/{id}/submit` with the incomplete body; GET the draft | `event_name: "Incomplete"` only | 422; the draft still reads `Draft` with its saved values | No status change; no outbox event or assignment | API |
| AC4-P2 | AC4, AC2 | The frontend names the missing fields and never calls the API | Partition | Server action, fetch stubbed | `submitNewEventRequest` with a name only | `event_name: "Incomplete request"` | Message "Complete all required fields before submitting."; errors for purpose, date/times and attendance; fetch not called | No API call | UI-A |
| AC4-N3 | AC4 | An unreachable API leaves a recoverable error | Negative | Server action; fetch rejects | `submitNewEventRequest` with the complete form | `completeFormData()` | Message "The request could not be submitted. Please try again."; no redirect; form values kept | No duplicate submission | UI-A |
| AC4-N2 | AC4 | The API refusal names every missing item | Negative | Organiser owns a draft missing 8 of 9 fields | POST to `/submit`; inspect the 422 detail body | draft with only `event_name` | The detail body lists each missing field | — | API |
| AC5-H1 | AC5, AC1, AC2; SCRUM-8 AC7 | The draft moves to Submitted under the same id | Happy | Organiser owns a Draft | POST the complete payload to `/event-requests/{id}/submit` | draft named "Initial title", then `complete_payload()` | 200; same id; `status: Submitted`; submitted event name equals the payload; exactly one row | No duplicate request row | API |
| AC5-H2 | AC5; SCRUM-8 AC7 | The submit action targets the existing draft | Happy | Server action, fetch stubbed | `submitDraftEventRequest` with the complete form | attendance "80"; date "2026-10-20T10:00" | POST to the draft's submit endpoint carrying the form values; redirect to `?status=submitted` | No create call alongside the submit | UI-A |
| AC5-P1 | AC5, AC2 | A complete new form can submit directly | Partition | Repository empty | POST `/event-requests/submissions` | `complete_payload()` | 201; `Submitted`; `organiser_id` = verified id; exactly one row | Never stored as a Draft first | API |
| AC5-P2 | AC5 | The direct-submission action posts to the submissions endpoint | Partition | Server action, fetch stubbed | `submitNewEventRequest` | `completeFormData()` | POST `/event-requests/submissions`; redirect to `?status=submitted` | — | UI-A |
| AC5-H3 | AC5, AC7 | Browser journey: submit then read-only detail | Happy | Playwright organiser logged in; disposable APIs | Fill all nine fields; confirm the dialog; open the detail from the submitted list | "Submitted Community Workshop", attendance 80 | Redirect to the submitted list; card shows Submitted; the detail shows the read-only notice; no Delete draft control | — | E2E |
| AC6-N1 | AC6 | Submission creates no Coordinator assignment | Negative | Organiser owns a complete Draft; assignment store inspectable | Submit; inspect assignment data afterwards | `complete_payload()` | Status `Submitted`; no `event_coordinator_assignments` row exists for the request | No assignment row (SCRUM-14 owns real assignments) | API |
| AC7-N1 | AC7, AC1 | A Submitted request refuses edit, resubmission and deletion | Negative | Direct-submitted request | PATCH it; POST `/submit` again; DELETE it; GET it | `complete_payload()` | 409 on all three mutations; GET 200 with `Submitted` and the original values | Stored values unchanged by the refused calls | API |
| AC7-N2 | AC7 | A repeated submission reports the read-only state | Negative | Server action; fetch returns 409 | `submitDraftEventRequest("submitted-1", …)` | `completeFormData()` | Message "This request has already been submitted and is now read-only."; no redirect | — | UI-A |
| AC7-P1 | AC7 | A Submitted row keeps only the view control | Partition | `RequestList` rendered with a Submitted request | Inspect the card's controls | `completeDraft` with `status: "Submitted"` | "Submitted" text and a View request link; no Delete draft button | — | UI-C |
| AC7-X1 | AC7 | Submission demands explicit read-only acknowledgement | Cross-cutting | Complete draft form rendered | Click Submit request | `completeDraft` | Alertdialog "Submit event request?" stating the request cannot be edited or deleted | No submission fires before confirmation | UI-C |
| AC8-H1 | AC8 | The Draft-to-Submitted write records exactly one event | Happy | Migrated cluster (`0008`); one Draft row, rollback-only script | UPDATE the row's status to Submitted; count its outbox rows | Draft row "AC9 draft verification" | Exactly 1 `event_request.submitted` row keyed by the request | No second event | DB |
| AC8-X1 | AC8 | A repeated status write records no second event | Cross-cutting | As AC8-H1, already submitted | UPDATE the status to Submitted again; count | — | Count still 1 (unique constraint + `ON CONFLICT DO NOTHING`) | No duplicate event | DB |
| AC8-P1 | AC8, AC2 | A direct submission records exactly one event | Partition | Migrated cluster, rollback-only script | INSERT a Submitted row directly (AC2-P2 data) | placeholders ×4, attendance 20 | Exactly 1 outbox event for the new id | — | DB |
| AC8-N1 | AC8; SCRUM-8 AC6 | A Draft records no submission event | Negative | Migrated cluster, rollback-only script | INSERT a Draft row; count its events | Draft row "AC9 draft verification" | 0 events | No outbox row | DB |
| AC8-X2 | AC8 | Browser roles cannot read the outbox | Cross-cutting | Migrated cluster | Check RLS, policies and privileges for `anon`, `authenticated`, `service_role`; check the trigger function's executability | — | RLS enabled; no client policies; reads revoked from `anon`/`authenticated`; service-only grant; trigger not directly executable by application roles | — | DB |

## Latest execution record

No suites were run for this conversion (label-and-matrix pass only). The label comments were added on the `docs/testcase-gap-sweep` working tree, 1 November 2026, by Claude for Yang Xue, and still need a teammate review of the test design (`testing.md` §10) plus a fresh run for any Done claim. The September catalogue's last full verification (21 September 2026: backend 76 passed, frontend 24 passed, 4 Playwright journeys, outbox SQL verifications passed, outbox security inspected) predates this branch state and is **not** current evidence.

| ID | Automation status | Actual result | Execution status | Build or commit | Executed by and date | Remarks and evidence |
| --- | --- | --- | --- | --- | --- | --- |
| AC1-N1, AC1-X1, AC2-P1, AC2-N1, AC3-H1, AC3-B1, AC4-N1, AC5-H1, AC5-P1, AC7-N1 | Automated (label added in this pass) | Not run in this pass | Not executed | working tree, `docs/testcase-gap-sweep`, labels only | Claude for Yang Xue, 1 Nov 2026 | `backend/eventRequestService/tests/test_event_request_controller.py` — labels `SCRUM-11 AC…` added above the tests; behaviour itself unchanged |
| AC1-P1 | Automated (label added in this pass) | Not run in this pass | Not executed | as above | Claude for Yang Xue, 1 Nov 2026 | `backend/eventRequestService/tests/test_supabase_repository.py::test_submit_atomically_scopes_and_changes_status` |
| AC3-B2, AC4-P2, AC4-N3, AC5-H2, AC5-P2, AC7-N2 | Automated (label added in this pass) | Not run in this pass | Not executed | as above | Claude for Yang Xue, 1 Nov 2026 | `frontend/__tests__/event-request-actions.test.ts` |
| AC7-P1, AC7-X1 | Automated (label added in this pass) | Not run in this pass | Not executed | as above | Claude for Yang Xue, 1 Nov 2026 | `frontend/__tests__/page.test.tsx` |
| AC5-H3 | Automated (label added in this pass) | Not run in this pass | Not executed | as above | Claude for Yang Xue, 1 Nov 2026 | `frontend/e2e/home.spec.ts` — "organiser can submit a complete new event request" |
| AC8-H1, AC8-X1, AC8-P1, AC8-N1 | Automated (label added in this pass) | Not run in this pass | Not executed | as above | Claude for Yang Xue, 1 Nov 2026 | `database/verify_event_request_submission_outbox.sql` (rollback-only); AC8-N1 shared with SCRUM-8 AC6-N1 |
| AC4-N2 | Automated (backfilled 6 Nov 2026 — behaviour had already shipped) | 422; detail body enumerates exactly the 8 missing fields | Pass | working tree, branch `test/backfill-planned-cases` | Claude for Yang Xue, 6 Nov 2026 | `backend/eventRequestService/tests/test_event_request_controller.py::test_refused_submission_names_every_missing_field` — asserted `set(complete_payload()) - {"event_name"}` |
| AC6-N1 | Automated (backfilled 6 Nov 2026 — behaviour had already shipped) | Status `Submitted`; `coordinator_assignment_rows` empty and no row for the request | Pass | working tree, branch `test/backfill-planned-cases` | Claude for Yang Xue, 6 Nov 2026 | `backend/eventRequestService/tests/test_event_request_controller.py::test_submit_creates_no_coordinator_assignment` — asserted against the fake's `FakeCoordinatorAssignmentRepository` store |
| AC8-X2 | Planned | — | Not executed | — | — | gap: no automated check in the repository — story owner to write; migration `0008` enforces the rules and the September catalogue recorded the manual inspection (21 September 2026) |
