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

None. Each owner adds a row for the file they own: either the test that closes the gap, or why it cannot be closed (for example "only reachable against a live Supabase project; checked by `verify_x.sql`"). Rows to fill in:

| Area | File or group | Owner | Closed by test, or reason it stays uncovered |
| --- | --- | --- | --- |
| | | | |

## Not yet done

- No threshold in CI. A threshold set below today's numbers would only stop things getting worse, and one at 100% would fail every build.
- No mutation testing (`docs/standards/testing.md` §7).
- The Playwright suite is not combined with the unit figure.
