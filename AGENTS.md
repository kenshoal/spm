# ConnectSphere (spm): agent guide

Shared rules for every agent and contributor in this repository. Codex reads this file directly; Claude Code reads it through `CLAUDE.md`. Keep it short: the detail lives in `docs/standards/`.

## Read before you start

| If the task involves… | Read this first |
| --- | --- |
| Writing, changing or reviewing tests; deriving test cases from a Jira story or its acceptance criteria; editing `docs/testcases/`; reporting test results or evidence | `docs/standards/testing.md` |
| Committing, branching, merging or opening a pull request | `docs/standards/commits.md` |
| Status changes, roles, permissions, ownership, database writes, RLS, or error responses for protected resources | `docs/standards/security-and-state.md` |
| Deciding whether a story is Done | `docs/standards/definition-of-done.md` |

Read the file even when the task looks small. If a detail file conflicts with this one, follow this file and report the conflict.

## Core principles

1. **Requirements are the test oracle.** Expected behaviour comes from the Jira story, its approved acceptance criteria (ACs) and agreed domain rules, not from what the code currently does. When requirements and code disagree, stop and resolve it through Jira or the team before changing either.
2. **Approve the ACs before building.** Review every AC and get explicit approval of the scope before detailed test design, production code or database changes. Until then, work read-only.
3. **Small vertical increments, Red → Green → Refactor.** One reviewable behaviour at a time, through every layer it touches.
4. **Stay inside the story.** Do not implement adjacent backlog stories or claim their behaviour.
5. **Report evidence honestly.** Never write only "tests passed". Give the command, the counts and the environment, and keep local, shared-database, browser and CI results separate.

## Testing rules that always apply

- Every test case maps to at least one AC and is recorded in `docs/testcases/scrum_<n>_testcases.md`.
- Test-case IDs are `AC<n>-<letter><k>`: `H` happy path, `P` partition, `B` boundary, `N` negative, `X` cross-cutting (for example `AC2-N1`). Put a comment directly above each automated test with its ID, technique and purpose: `# AC2-N1 (negative): rejects an unknown status`.
- Cover the happy path, one representative per equivalence partition, just below / at / just above each boundary, and the negative cases.
- Assert every output and side effect, including the state that must stay unchanged when an operation is refused.
- Negative tests assert the specific failure: exception type or HTTP status, and the error code.
- Never push a failing (red) commit to a shared branch.
- **Before finishing any task that added or changed tests,** check that every new or changed test has its label comment.

## Commit rules that always apply

- Subject format: `<type>(<scope>): <description>`. Types: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`, `revert`. The `.githooks/commit-msg` hook and CI reject anything else.
- Enable the hook once per clone: `git config core.hooksPath .githooks`.
- Merge `dev` into a branch with the message `chore: merge dev into <branch>`. Git's default merge message fails CI.
- Branch from `dev` and open pull requests into `dev`.

## Iteration sequence

1. Fetch the Jira story, review every AC and get the scope approved (`testing.md` §1).
2. Record the approved story contract and design the test cases in `docs/testcases/` (`testing.md` §2–4).
3. Pick one behaviour, starting with the happy path. Write a test and watch it fail for the intended reason.
4. Make the smallest change that passes, refactor, and run the related tests.
5. Repeat for the next behaviour, then run the integration and end-to-end checks.
6. Commit (`commits.md`), push, and confirm pull-request CI before marking the story Done (`definition-of-done.md`).

## Commands

- Backend, from `backend/<service>/`: `ruff check .` and `pytest`
- Frontend, from `frontend/`: `npm run lint`, `npm run typecheck`, `npm test`, `npm run test:e2e`, `npm run build`
