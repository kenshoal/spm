# Test coverage

The Week 4 rubric asks for 100% coverage unless the team states why that is not possible. This page records what is measured and where the gaps are. **It does not yet justify them.** A gap is justified only when its owner has written the reason against it below; until then it is an open gap.

## How it is measured

| Layer | Command (run from the folder shown) | Reported in CI |
| --- | --- | --- |
| Backend, one service | `backend/<service>/`: `pytest --cov=app --cov-branch --cov-report=term-missing:skip-covered` (needs `pip install "pytest-cov>=6,<8"`) | Every backend test job prints it. No threshold, so nothing fails below a number |
| Frontend unit tests | `frontend/`: `npm run test:coverage` (Vitest with `@vitest/coverage-v8`) | The Unit tests job prints a summary. No threshold |

What the numbers do not include:

- **Playwright** end-to-end tests are not measured. Pages that only the browser tests drive show as uncovered in the frontend figure.
- **SQL**: the migrations and functions are checked by the `database/verify_*.sql` scripts, which have no coverage measure.
- Coverage shows which lines ran, not whether a test would notice a fault (`docs/standards/testing.md` §7).

## Measured on `dev` (3 November 2026)

Local runs, branch coverage on. Python 3.13 and Node 24 on a developer machine, not CI.

| Service | Tests | Covered (lines and branches) | Missed lines | Partly covered branches |
| --- | --- | --- | --- | --- |
| authService | 60 passed | 84% | 27 | 9 |
| equipmentService | 359 passed | 96% | 26 | 8 |
| eventRequestService | 1,222 passed, 1 skipped | 88% | 406 | 114 |
| notificationService | 85 passed | 96% | 9 | 3 |
| venueService | 858 passed, 10 skipped | 92% | 162 | 41 |

The percentage is `coverage.py`'s combined figure (lines and branches together). A branch is partly covered when a test takes one way through an `if` but never the other.

| Frontend (Vitest, jsdom) | Covered |
| --- | --- |
| Lines | 77.76% (2,085 of 2,681) |
| Branches | 69.70% (2,306 of 3,308) |
| Statements | 75.69% |
| Functions | 64.82% |

## Where the gaps are

**Backend.** Of the 630 missed lines, 289 are in files that talk to Supabase or another service (repositories, stores, HTTP clients, adapters, lookups). The other 341 are not, so "needs a real database" does not explain them. The largest are in `eventRequestService`: `event_request_service.py` (64), `event_request_controller.py` (49), `event_request_repository.py` (41), `registration_repository.py` (32), `arrangement_review_notification_relay.py` (28), `waitlist_repository.py` (28). In `venueService`: `hold_store.py` (34), `supabase_block_repository.py` (23), `dependencies.py` (19), `supabase_booking_repository.py` (17).

**Frontend.** 42 files have no unit coverage at all (361 of the 596 missed lines). 25 of them are `page.tsx` or `layout.tsx` server components, which have no render test and are driven only by Playwright. The rest are mostly client form components and server actions. The largest: `coordination/requests/[id]/page.tsx` (38 lines), `safety/page.tsx` (36), `coordination/actions.ts` (31 missed of 189), `equipment/requests/page.tsx` (21).

## Reasons written so far

Filled in on 6 November 2026, against the fourteen cases the test-case documents marked Planned: seven were closed by backfilled tests (each verifying behaviour that had already shipped, recorded as such), seven stay uncovered for the stated reasons.

| Area | File or group | Owner | Closed by test, or reason it stays uncovered |
| --- | --- | --- | --- |
| SCRUM-8 | `tests/test_event_request_controller.py` AC2-H1 | story owner | Closed by test: `test_create_completely_empty_draft` (backfilled 6 Nov 2026; behaviour predated the test, recorded as a characterization backfill) |
| SCRUM-8 | AC3-N1 (restart persistence) | story owner | Uncovered pending a design decision (scrum_8 open question 2): a dedicated restart test, or the E2E reload journey (`AC3-H1`) as the agreed evidence |
| SCRUM-8 | AC5-N1 (drafts absent from review/assignment listings) | story owner | Uncovered: the listing surfaces belong to the review/assignment stories; the submit-side half (no assignment row on submit) is now automated as SCRUM-11 AC6-N1; the listing-absence assertion remains to be written against those listing endpoints |
| SCRUM-11 | `tests/test_event_request_controller.py` AC4-N2 | story owner | Closed by test: `test_refused_submission_names_every_missing_field` (backfilled 6 Nov 2026) |
| SCRUM-11 | `tests/test_event_request_controller.py` AC6-N1 | story owner | Closed by test: `test_submit_creates_no_coordinator_assignment` (backfilled 6 Nov 2026) |
| SCRUM-11 | `database/verify_event_request_submission_outbox.sql` AC8-X2 | story owner | Uncovered: browser-role RLS on the outbox is enforced by migration `0008`; an automated check needs a disposable migrated PostgreSQL (CI's bootstrap database). Manual inspection recorded 21 September 2026; to be added as a verifier block |
| SCRUM-26 | `tests/test_registration.py` AC2-B2 | story owner | Closed by test: `test_login_minimum_length_password_reaches_provider` (backfilled 6 Nov 2026; `min_length=1`, so 1 character is exactly at the minimum) |
| SCRUM-27 | `tests/test_registration.py` AC3-N1 | story owner | Closed by test: `test_mid_session_role_change_applies_on_the_next_request` (backfilled 6 Nov 2026). `/auth/me`'s 30-second verified-token cache is a documented trade-off and is not the role path |
| SCRUM-28 | `tests/test_event_transition_controller.py` AC1-N1 | story owner | Closed by test at the API/enum layer: `test_unknown_status_value_is_refused_without_storage` (backfilled 6 Nov 2026). The database CHECK path stays asserted only by the migrations |
| SCRUM-28 | AC4-X3 (real-Postgres assignment-vs-transition race) | story owner | Uncovered: needs the disposable-Postgres concurrency harness (`database/tests/`); SCRUM-48's AC4-X1 covers the transition-vs-transition half |
| SCRUM-48 | AC1-X4 (shared row-lock contention) | story owner | Uncovered: observing the primary's held row-lock phase needs a direct PostgreSQL observer session (credentials unavailable); the 12 October attempt and its artifacts are recorded in scrum_48 |
| SCRUM-48 | AC5-N17 (natural token expiry) | story owner | Uncovered: needs a real authService/Supabase Auth round-trip holding a token past actual expiry (about an hour of wall-clock); lifetime metadata was measured on 12 October 2026 |
| SCRUM-64 | AC5-X4 (workflow consistency across staff-clearing and coordinator reload) | story owner | Uncovered: live cross-cutting check needing a real coordinator session against a real stack; only manual verification so far |
| SCRUM-67 | `tests/test_booking_clash_warning.py` AC1-B4 | story owner | Closed by test: `test_a_touching_padded_end_is_clear_but_one_step_more_clashes` (backfilled 6 Nov 2026, both boundary cases) |

## Not yet done

- No threshold in CI. A threshold set below today's numbers would only stop things getting worse, and one at 100% would fail every build.
- No mutation testing (`docs/standards/testing.md` §7).
- The Playwright suite is not combined with the unit figure.
