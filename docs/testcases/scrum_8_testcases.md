# SCRUM-8 Test Cases: Save a Draft Event Request

Last reviewed: 15 September 2026

This catalogue explains the automated tests for SCRUM-8 and the supporting
event-request infrastructure. Authentication-service tests, tests owned by other
stories, dependency tests and generated output are excluded. Every test has one
distinct purpose so that passing counts can be traced to observable behaviour
rather than treated as proof by themselves.

## How to run the suites

| Area | Command | Current automated cases |
| --- | --- | ---: |
| Event-request service | `cd backend/eventRequestService && pytest` | 18 |
| Frontend components and actions | `cd frontend && npm test` | 9 |
| Frontend browser journey | `cd frontend && npm run test:e2e` | 1 |
| **SCRUM-8 and supporting total** |  | **28** |

The Playwright test uses a disposable in-memory API on port `8103` and a test
frontend on port `3100`. It does not read or mutate the shared Supabase project.

## SCRUM-8 acceptance-criterion coverage

The criterion IDs below are local references for the seven acceptance criteria
in Jira story **SCRUM-8: Save a Draft Event Request**.

| ID | Acceptance criterion | Automated evidence | Status and limitation |
| --- | --- | --- | --- |
| AC1 | An authenticated organiser can save incomplete information with `Draft` status. | `test_create_and_get_incomplete_draft`; Playwright draft journey | Draft behaviour passes. Authentication is represented by the temporary organiser header until the authentication story is integrated. |
| AC2 | A draft records all ten listed fields and permits them to remain incomplete. | `test_all_draft_fields_round_trip_unchanged`; `allows an incomplete event request to be saved as a draft` | Covered. |
| AC3 | The responsible organiser can return later, recover all values and continue editing. | `test_draft_persists_when_the_application_restarts`; `prefills the form when an organiser continues a draft`; Playwright draft journey | Persistence and editability pass. A real authenticated-session boundary remains dependent on authentication integration. |
| AC4 | Only the responsible organiser can modify the draft. | `test_other_organiser_cannot_read_update_or_delete`; Supabase GET, PATCH and DELETE scoping tests | Covered for the temporary organiser identity. A client-supplied header is not production authentication. |
| AC5 | Drafts are absent from coordinator review and assignment work. | None | Pending because the coordinator review/assignment interface belongs to its separate story. It must receive a negative integration test when that interface exists. |
| AC6 | Saving a draft does not submit, assign or notify. | Create tests assert `Draft`; frontend tests assert no submission action; repository create contract contains no assignment or notification operation. | Covered inside the current service boundary. Recheck when assignment and notification integrations are introduced. |
| AC7 | Submission receives the saved values unchanged. | The all-fields round-trip test proves the stored draft can be retrieved unchanged. | Final hand-off verification remains pending SCRUM-11 because submission does not exist yet. |

SCRUM-8 should be closed only after the team accepts the authentication,
coordinator-visibility and submission items as explicit cross-story dependencies,
or after those integration checks exist. The delete-draft behaviour is useful
CRUD coverage but is not part of the current SCRUM-8 acceptance criteria.

## Event-request configuration tests

Source: `backend/eventRequestService/tests/test_config.py`

| Test | Purpose | Layer |
| --- | --- | --- |
| `test_settings_load_supabase_environment` | Confirms Supabase URL and secret configuration are loaded from server environment variables. | Unit |
| `test_settings_require_supabase_secret` | Prevents database operations from starting silently without the required server secret. | Unit |

## Event-request API tests

Source: `backend/eventRequestService/tests/test_event_request_controller.py`

| Test | Purpose | Layer |
| --- | --- | --- |
| `test_health` | Confirms the event-request service exposes a readiness signal. | API component |
| `test_create_and_get_incomplete_draft` | Proves incomplete information is accepted, stored as `Draft` and retrievable. | API component |
| `test_all_draft_fields_round_trip_unchanged` | Proves every SCRUM-8 field can be saved and retrieved without value loss. | API component |
| `test_list_returns_only_the_current_organisers_requests` | Keeps one organiser's list isolated from another organiser's drafts. | API authorization |
| `test_patch_updates_the_same_draft_and_can_clear_a_field` | Ensures editing changes the existing draft and supports intentionally clearing a field. | API component |
| `test_delete_removes_the_draft` | Confirms a discarded draft is no longer retrievable. | API component |
| `test_other_organiser_cannot_read_update_or_delete` | Prevents a different temporary organiser from reading or mutating the owner's draft. | API authorization |
| `test_requires_non_blank_organiser_header` | Rejects requests without a usable temporary organiser identity. | API validation |
| `test_rejects_unsupported_organiser_header_characters` | Prevents temporary identity text from altering Supabase filter expressions. | API security |
| `test_rejects_invalid_expected_attendance` | Prevents a non-positive attendance value from being persisted. | API validation |
| `test_draft_persists_when_the_application_restarts` | Proves stored work remains available through a new application instance using the same repository. | API persistence |

## Supabase repository tests

Source: `backend/eventRequestService/tests/test_supabase_repository.py`

| Test | Purpose | Layer |
| --- | --- | --- |
| `test_create_sends_expected_supabase_request` | Verifies draft creation sends the expected table payload using the server-only key. | Repository contract |
| `test_get_scopes_query_to_temporary_organiser` | Ensures retrieval matches both request ID and temporary organiser identity. | Repository contract |
| `test_update_scopes_query_to_owner_and_draft_status` | Prevents updates from escaping the request ID, owner and `Draft` filters. | Repository contract |
| `test_delete_scopes_query_to_owner_and_draft_status` | Prevents deletion unless request ID, owner and `Draft` status all match. | Repository contract |
| `test_supabase_failure_raises_repository_error` | Converts an upstream Supabase failure into the service's stable error boundary. | Repository failure handling |

## Frontend server-action tests

Source: `frontend/__tests__/event-request-actions.test.ts`

| Test | Purpose | Layer |
| --- | --- | --- |
| `creates an incomplete draft through the event request API` | Proves the form sends optional values to the create endpoint and returns to the request list. | Server-action unit |
| `updates the same draft through the event request API` | Ensures continuing a draft targets the existing identifier rather than creating a duplicate. | Server-action unit |
| `rejects non-positive attendance without calling the API` | Prevents invalid attendance from crossing the frontend-to-API boundary. | Server-action validation |
| `deletes the selected draft through the event request API` | Confirms deletion targets the selected record under the current temporary identity. | Server-action unit |
| `returns an actionable error when the API rejects draft deletion` | Keeps a failed deletion visible and avoids presenting it as successful. | Server-action failure handling |

## Frontend component tests

Source: `frontend/__tests__/page.test.tsx`

| Test | Purpose | Layer |
| --- | --- | --- |
| `routes a saved draft to the editable form` | Gives the organiser a direct route back to the selected draft. | Component |
| `requires confirmation before deleting a draft` | Prevents an accidental click from permanently removing unfinished work. | Component interaction |
| `allows an incomplete event request to be saved as a draft` | Confirms draft fields are optional and submission is not exposed in SCRUM-8. | Component |
| `prefills the form when an organiser continues a draft` | Confirms previously saved values appear when editing resumes. | Component |

## Playwright browser test

Source: `frontend/e2e/home.spec.ts`

| Test | Purpose | Layer |
| --- | --- | --- |
| `organiser can save, reopen, update, and delete a draft` | Proves unfinished work survives navigation and reload, remains editable and can be discarded only after confirmation. | Browser end-to-end |

## Quality gates that are not individual test cases

The following checks complement the 28 SCRUM-8 and supporting behavioural cases:

- `npm run lint` checks frontend code quality rules.
- `npm run typecheck` checks TypeScript and generated Next.js route types.
- `npm run build` proves the production frontend compiles.
- `ruff check .` checks Python formatting and static rules.
- Docker builds verify that each backend service can be packaged.
- Dependency-audit jobs report known high-severity package vulnerabilities.

## Adding or changing a test

1. Add a one-line `Purpose:` comment explaining the distinct risk or behaviour.
2. Update the relevant table in this document.
3. Link the test to a Jira acceptance criterion when applicable.
4. Run the narrow suite, then the relevant lint, type, build and integration gates.
5. Record failures honestly; a planned or skipped case is not passing evidence.
