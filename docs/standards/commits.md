# Commit, branch and pull-request standard

Read this before committing, branching, merging or opening a pull request. These rules mirror what the repository enforces: `.githooks/commit-msg` checks each commit locally, and `.github/workflows/conventional-commits.yml` runs the same script on every push and every commit in a pull request. A non-conforming commit fails CI.

## 1. Enable the local hook (once per clone)

```bash
git config core.hooksPath .githooks
```

## 2. Subject line

### Enforced

```text
<type>(<scope>)<!>: <description>
```

- **Types:** `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`, `revert`.
- **Scope** is optional and may contain only letters, digits, `_`, `.` and `-`. No spaces, slashes or commas.
- **`!`** before the colon marks a breaking change, e.g. `feat(event-request)!: remove the legacy status endpoint`. Explain the break in the body.
- **Exactly one space** after the colon, then a non-empty description.
- **Only exemption:** GitHub's own `Merge pull request #<n> from <branch>`. Git's default local message (`Merge branch 'dev' into …`) is rejected, so write local merges as `chore: merge dev into <branch>`.

### Team practice

- **Scope names the service or area:** `auth`, `event-request`, `equipment`, `venue`, `notification`, `frontend`, `e2e`, `database`, `ci`, `deps`, `env`, `compose`, `security`. Use `docs(scrum-<n>)` for a story's test-case and evidence document. History also contains `event`, `db` and `event_request_submission`; use `event-request` and `database` for new commits.
- **Append the Jira key** when the commit delivers a story's behaviour: `feat(frontend): coordinators search and filter venues (SCRUM-9)`.
- **Lower case, present tense**, describing what the change does: `list users holding a role for assignment pickers`, not `added some endpoints`.
- **72 characters or fewer** (not enforced by the hook).

## 3. Body

- One blank line after the subject; wrap at about 72 characters.
- Say **why** the change was needed, then **what** changed. Use bullets when a commit touches several things.
- Name migrations by number and whether they were applied to the shared database, list the tests added (count and file), and note any verification done.
- If the commit fixes a test that its own change legitimately broke, say so.

## 4. Commit granularity and TDD

- **One behaviour per commit**, reviewable on its own and matching one group of rows in the test matrix.
- **Never push a red commit to a shared branch.** Record the Red result in the matrix, then commit the test together with the change that makes it pass. Commit a test-only change as `test(<scope>): …` only when it passes on its own (new coverage for existing behaviour, or an end-to-end journey).
- **Commit evidence documents separately** as `docs(scrum-<n>): …`, so implementation and evidence can be reviewed independently.
- **Do not commit generated output:** Playwright reports and snapshots (`output/`, `.playwright-cli/`), coverage files, `.pytest_cache/`, virtual environments, `.env` or any secret. Add new generated paths to `.gitignore` in the same pull request that creates them.

## 5. Branches

- Branch from `dev`. Name it `<type>/<short-kebab-topic>`, with the story number when it delivers one story: `feat/scrum-28-status-follow-up`, `fix/equipment-review-findings`.
- To pick up new `dev` changes, merge `dev` into the branch with `chore: merge dev into <branch>` and re-run the focused tests before pushing.

## 6. Pull requests

Open pull requests into `dev`; `dev` is promoted to `main` by pull request. Backend and frontend CI run on pull requests and pushes to `dev` and `main`; the commit-message check runs on every push and pull request.

Each pull request contains:

1. the Jira link;
2. the problem and the resulting behaviour;
3. the scoped changes;
4. the path to the story's test-case and evidence document;
5. validation commands and results;
6. dependencies and excluded stories;
7. migration or rollback notes;
8. risks and remaining unverified work;
9. a reviewer checklist derived from the ACs.
