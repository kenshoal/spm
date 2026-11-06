# SCRUM-8 — Save a Draft Event Request

Source: issue tracker SCRUM-8 (title "Save a Draft Event Request"; the issue tracker user-story sentence is not recorded in the September catalogue and is not restated here).

Status (converted 1 Nov 2026): **AI-drafted conversion of the September catalogue to the `testing.md` matrix format; teammate review pending (`testing.md` §10).** The AC wording below is as recorded in the converted catalogue (the old catalogue's AC table, kept verbatim); **Issue tracker remains the source of truth.** Labels in the test files read `SCRUM-8 AC<n>-<L><k>` (story-prefixed, following the `SCRUM-38 AC4-X1` precedent) because `test_event_request_controller.py` also carries SCRUM-39 labels with overlapping `AC4`/`AC5` numbering. Nothing was executed in this pass: the matrix and the labels were added; every execution row below is `Not executed`.

## Story contract

### Acceptance criteria

- **AC1:** An authenticated organiser can save incomplete information with `Draft` status.
- **AC2:** A draft records all ten listed fields and permits them to remain incomplete.
- **AC3:** The responsible organiser can return later, recover all values and continue editing.
- **AC4:** Only the responsible organiser can modify the draft.
- **AC5:** Drafts are absent from coordinator review and assignment work.
- **AC6:** Saving a draft does not submit, assign or notify.
- **AC7:** Submission receives the saved values unchanged.

### Scope

| | Behaviour | Owner |
| --- | --- | --- |
| Included | Saving an incomplete request as a `Draft` and reading it back (AC1, AC2) | SCRUM-8 |
| Included | Returning to a draft: recovery of saved values and the editing journey at the UI/E2E layers (AC3) | SCRUM-8 |
| Included | Ownership protection of drafts against another organiser's modifications (AC4) | SCRUM-8 |
| Included | A draft save creating no submission, assignment or notification side effect (AC6) | SCRUM-8 |
| Included | The value hand-over from the saved draft into submission (AC7, joint with SCRUM-11) | SCRUM-8 + SCRUM-11 |
| Excluded | Draft **read access** by relationship (list isolation, 404/403 scoping, attendee projection) | SCRUM-39 (`tests/test_organisation_access.py`; the `AC4-H1`, `AC4-N1`, `AC5-H1`, `AC5-N1` labels in the controller file are SCRUM-39's) |
| Excluded | The edit/update endpoint contracts (`PATCH /event-requests/{id}`) — labelled under SCRUM-29 in a later pass; SCRUM-8 keeps only the AC3 editing journey | SCRUM-29 |
| Excluded | Submission itself, the Submitted read-only state and the outbox event | SCRUM-11 |
| Excluded | Coordinator review and assignment interfaces (AC5's negative integration test lands with that story, per the September catalogue) | review/assignment story |
| Excluded | Draft deletion as a capability (no AC claims it; the September catalogue called it useful CRUD coverage only) — the discard journey stays as E2E coverage of AC3 | — |
| Excluded | Authentication gates on the draft endpoints (401s, spoofed headers, role checks) | SCRUM-26 (`AUTH-17`, `AUTH-18`) |

### Actors and permissions

- **Event Organiser (owner):** the only actor who may create, read, modify or discard their draft; ownership binds to the authService-verified session id, never to a caller-supplied header (`SCRUM-8 AC4-X1`/`AC4-X2`).
- **Another authenticated organiser:** every direct access to a foreign draft returns 404 and the draft is unchanged (`AC4-N1`); read-side scoping rules live in SCRUM-39.
- **Unauthenticated callers:** 401 on every draft operation (SCRUM-26 `AUTH-17`; not relabelled here).

### Allowed state transitions

| From | To | Trigger |
| --- | --- | --- |
| — | `Draft` | AC1 save (any field subset) |
| `Draft` | `Draft` | AC3 continued editing (also SCRUM-29's update endpoint) |
| `Draft` | `Submitted` | AC7 hand-over, via SCRUM-11's submit endpoint only |

No transition out of `Draft` happens as a side effect of saving.

### Persistence and atomicity

- A save is one POST to `event_requests` through the **server-only** key (`AC1-H2`); the browser never holds the write credential.
- Saving writes no outbox row (`AC6-N1`), creates no coordinator assignment and sends no notification.
- Values survive across requests and sessions through the repository store; the process-restart case has no dedicated test any more (see open questions).

### Assumptions and open questions

1. AC2 says "all ten listed fields"; the request model exposes **nine** organiser-editable fields (event name, purpose, description, proposed date/times, expected attendance, venue, accessibility, equipment, registration). The tenth issue tracker field is presumably a system column (status or organiser). Confirm against the issue tracker at review.
2. The September catalogue cited `test_draft_persists_when_the_application_restarts` for AC3; that test no longer exists in `test_event_request_controller.py`. AC3-N1 is recorded as a planned gap — decide whether a dedicated restart case is needed or the E2E reload journey (`AC3-H1`) is the agreed evidence.
3. AC5 stays open exactly as the September catalogue left it: the coordinator review/assignment interface belongs to its own story; the negative integration test ("a draft never appears there") must be written when that interface exists.
4. The September suite counts (41 cases) are stale; the suites have grown with later stories. Counts are not restated here — run the suites for current numbers.
5. The old AC6 remark "frontend tests assert no submission action" is outdated: the form now exposes a Submit request control (SCRUM-11's direct submission). AC6 itself — a *save* never submits, assigns or notifies — is unaffected; the draft save posts only to `/event-requests`.

### How to run the suites (folded from the September catalogue)

| Area | Command |
| --- | --- |
| Event-request service | `cd backend/eventRequestService && uv run --python 3.14 --extra dev pytest` |
| Frontend components and actions | `cd frontend && npm test` |
| Frontend browser journeys | `cd frontend && npm run test:e2e` (disposable auth and event-request APIs on ports 8104 and 8103, test frontend on 3100; never touches the shared Supabase project) |
| Outbox database checks (SCRUM-11's script, shared with AC6-N1) | `database/verify_event_request_submission_outbox.sql`, after `0008`, rollback-only |
| Gates | `ruff check .` (backend), `npm run lint` / `npm run typecheck` / `npm run build` (frontend) |

## Test case specification

Layers: API = `backend/eventRequestService/tests/test_event_request_controller.py`; R = repository (`tests/test_supabase_repository.py`); DB = `database/verify_event_request_submission_outbox.sql`; UI-A = server actions (`frontend/__tests__/event-request-actions.test.ts`); UI-C = components (`frontend/__tests__/page.test.tsx`); E2E = `frontend/e2e/home.spec.ts`. The API tests run the FastAPI app against a faked repository with the verified organiser `ORGANISER_ID = 11111111-1111-4111-8111-111111111111` (`make_client`); `complete_payload()` is the nine-field form (attendance 80, one `+08:00` date time).

| ID | AC | Test scenario | Technique | Pre-conditions | Test steps | Test data | Expected result | Forbidden side effects | Layer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AC1-H1 | AC1, AC6 | An incomplete save is stored as a Draft and reads back unchanged | Happy | Organiser session verified | POST `/event-requests` with only a name; GET the returned id | `event_name: "Community Dinner"` | 201; `status: "Draft"`; `organiser_id` = verified id; unset fields null; GET body equals the created body | No Submitted row; no assignment or notification side effect | API |
| AC1-H2 | AC1, AC6 | Draft creation is a single server-key insert into `event_requests` | Happy | Mock-transport repository | `repository.create(...)`; capture every HTTP request | body `{organiser_id, status: Draft, event_name}` | Exactly one request: POST `/rest/v1/event_requests`, `apikey` = server secret, no bearer header, body carries Draft | Any second call (assignment/notification) would fail the capture | R |
| AC2-P1 | AC2; SCRUM-11 AC3 | Every saved field round-trips under its own column | Partition | Organiser session | POST the complete payload; GET it back | `complete_payload()` | 201 then 200; each field equals its input; attendance sits in `expected_attendance`, never inside `venue_requirements` | No field merged, dropped or duplicated | API |
| AC2-P2 | AC2, AC1 | Untouched fields reach the API empty and the save still succeeds | Partition | Server action with fetch stubbed | `createEventRequest` with a form holding only `event_name`; inspect the one fetch call | `event_name: "Community Dinner"` | Body sends `purpose: null`, `proposed_date_times: []`, `expected_attendance: null`; redirect to `/event-requests` | No call to a submission endpoint | UI-A |
| AC2-P3 | AC2 | Save draft bypasses HTML validation so fields may stay empty | Partition | Empty `EventRequestForm` rendered | Inspect the Save draft and Event name attributes | — | Save draft carries `formNoValidate`; a Submit request control exists with native validation | Saving never triggers browser validation errors | UI-C |
| AC2-B1 | AC2; SCRUM-11 AC3 | Attendance just below the minimum is refused at save | Boundary | Organiser session | POST with `expected_attendance: 0` | 0 (minimum is 1) | 422 | No draft persisted | API |
| AC2-B2 | AC2; SCRUM-11 AC3 | Attendance below the minimum is stopped before the API | Boundary | Server action, fetch stubbed | `createEventRequest` with attendance "0" | `"0"` | Field error "Enter a whole number greater than zero."; fetch never called | No draft created | UI-A |
| AC2-H1 | AC2 | A draft with no fields at all saves as a Draft | Happy | Organiser session | POST `/event-requests` with `{}` | empty object | 201; Draft row with null/empty fields | — | API |
| AC3-H1 | AC3 | Drafted work survives navigation and reload and reopens editable | Happy | Playwright organiser logged in; disposable APIs | Save a draft; reopen via Continue draft; edit; save; reload; check the text | "Playwright community dinner"; purpose "Updated after reopening the draft" | Values visible after reload; the draft reopens prefilled and saves again | The draft never becomes Submitted during the journey | E2E |
| AC3-P1 | AC3 | Reopening a draft restores its saved values | Partition | `EventRequestForm` rendered with a saved draft | Render and inspect the inputs | draft-1: "Technology Workshop" / "Teach practical skills" | Inputs prefill; the form shows Save changes | — | UI-C |
| AC3-P2 | AC3 | The list routes a saved draft back to its edit form | Partition | `RequestList` rendered with one draft | Inspect the Continue draft link | draft-1 | Link href `/event-requests/draft-1/edit` | — | UI-C |
| AC3-N1 | AC3 | Stored work survives a fresh application instance over the same store | Negative (restart) | One repository shared by two app instances | Create via instance 1; fetch via instance 2 | any draft | The draft is returned unchanged | — | API |
| AC4-N1 | AC4 | Another organiser cannot read, update or delete a draft | Negative | Repository seeded with `OTHER_ORGANISER_ID`'s Draft; caller is `ORGANISER_ID` | GET, PATCH and DELETE the foreign id | `event_name: "Private draft"` | All three return 404; the stored row still reads "Private draft" as Draft | No mutation of the foreign draft (read-side scoping detailed in SCRUM-39) | API |
| AC4-X1 | AC4 | Ownership binds to the verified session, not a caller header | Cross-cutting | Session mocked to the verified id; Supabase env set | POST with a bearer token and `X-Organiser-Id: attacker` | header value "attacker" | 201; stored `organiser_id` is the verified id, never the header | The header never changes ownership (SCRUM-26 AUTH-18 also cites this test) | API |
| AC4-X2 | AC4 | An organiser header without a session cannot reach drafts | Cross-cutting | No session | GET `/event-requests` with `X-Organiser-Id: attacker` | — | 401 | No rows returned (SCRUM-26 AUTH-18 also cites this test) | API |
| AC5-N1 | AC5 | Drafts never appear in coordinator review or assignment listings | Negative | One Draft owned by the organiser | List the coordinator review queue and the assignment candidates | the draft | Draft absent from both listings | Draft not mutated; no assignment created | API |
| AC6-N1 | AC6; SCRUM-11 AC8 | A Draft insert records no submission outbox event | Negative | Migrated cluster (`0008`), one auth user, rollback-only script | Insert a Draft row; count `event_request_outbox` rows for it | status Draft, name "AC9 draft verification" | Count is 0; the script raises otherwise | No outbox row; nothing to deliver | DB |
| AC7-H1 | AC7; SCRUM-11 AC1, AC5 | Submission receives the saved record and moves it to Submitted | Happy | Organiser owns a Draft | POST the complete payload to `/event-requests/{id}/submit` | draft named "Initial title", then `complete_payload()` | 200; same id; `status: Submitted`; exactly one row in the store | No duplicate request row | API |
| AC7-H2 | AC7; SCRUM-11 AC5 | The submit action hands the saved form values to the draft's endpoint | Happy | Server action, fetch stubbed | `submitDraftEventRequest` with the complete form | attendance "80"; date "2026-10-20T10:00" (+08:00) | POST to `/event-requests/draft%2F1/submit` carrying the form values (the date is normalised to UTC, meaning unchanged); redirect to the submitted list | No create call alongside the submit | UI-A |

## Latest execution record

No suites were run for this conversion (label-and-matrix pass only). Every automated row below is recorded honestly as not executed here; the label comments were added on the `docs/testcase-gap-sweep` working tree, 1 November 2026, by Claude for Yang Xue, and still need a teammate review of the test design (`testing.md` §10) plus a fresh run for any Done claim.

| ID | Automation status | Actual result | Execution status | Build or commit | Executed by and date | Remarks and evidence |
| --- | --- | --- | --- | --- | --- | --- |
| AC1-H1, AC2-P1, AC2-B1, AC4-N1, AC4-X1, AC4-X2, AC7-H1 | Automated (label added in this pass) | Not run in this pass | Not executed | working tree, `docs/testcase-gap-sweep`, labels only | Claude for Yang Xue, 1 Nov 2026 | `backend/eventRequestService/tests/test_event_request_controller.py` — labels `SCRUM-8 AC…` added above the tests; behaviour itself unchanged |
| AC1-H2 | Automated (label added in this pass) | Not run in this pass | Not executed | as above | Claude for Yang Xue, 1 Nov 2026 | `backend/eventRequestService/tests/test_supabase_repository.py::test_create_sends_expected_supabase_request` |
| AC2-P2, AC2-B2, AC7-H2 | Automated (label added in this pass) | Not run in this pass | Not executed | as above | Claude for Yang Xue, 1 Nov 2026 | `frontend/__tests__/event-request-actions.test.ts` |
| AC2-P3, AC3-P1, AC3-P2 | Automated (label added in this pass) | Not run in this pass | Not executed | as above | Claude for Yang Xue, 1 Nov 2026 | `frontend/__tests__/page.test.tsx` |
| AC3-H1 | Automated (label added in this pass) | Not run in this pass | Not executed | as above | Claude for Yang Xue, 1 Nov 2026 | `frontend/e2e/home.spec.ts` — "organiser can save, reopen, update, and delete a draft" |
| AC6-N1 | Automated (label added in this pass) | Not run in this pass | Not executed | as above | Claude for Yang Xue, 1 Nov 2026 | `database/verify_event_request_submission_outbox.sql` first section (Draft insert → zero events); shared with SCRUM-11 AC8-N1 |
| AC2-H1 | Planned | — | Not executed | — | — | gap: no automated test yet — story owner to write (a fully empty `{}` create is only exercised incidentally inside the delete test's setup) |
| AC3-N1 | Planned | — | Not executed | — | — | gap: no automated test yet — story owner to write (the September catalogue's `test_draft_persists_when_the_application_restarts` no longer exists; see open question 2) |
| AC5-N1 | Planned | — | Not executed | — | — | gap: no automated test yet — story owner to write (pending the coordinator review/assignment interface; the September catalogue recorded the same gap) |
