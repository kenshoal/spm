# Testing standard

Read this before writing, changing or reviewing tests, deriving test cases from a Jira story, or reporting test results. The always-apply rules are in `AGENTS.md`; this file holds the detail.

## 1. Establish the story contract

Before detailed test design or implementation, fetch the Jira story and review every acceptance criterion (AC). Do not assume the existing wording is ready for development.

### AC review gate

Check each AC for:

- **Relevance:** it supports the user story's outcome.
- **Scope:** it fits in one story without absorbing another backlog item.
- **Specificity:** the actor, action, conditions and observable result are clear.
- **Testability:** a reviewer can decide pass or fail from observable evidence.
- **Independence:** it does not bundle unrelated behaviours.
- **Consistency:** it agrees with the domain model, roles and lifecycle rules.
- **Non-duplication:** it does not restate another AC.
- **Dependency ownership:** notifications, later workflow stages and other teams' work are named, not claimed.
- **Proportionality:** the work is reasonable for the story's value and estimate.
- **Outcome focus:** it describes behaviour, not unnecessary implementation detail.

Give each AC one outcome: **Keep**, **Clarify** (intent valid, wording ambiguous), **Narrow** (too much behaviour), **Split** (independently testable parts), **Merge** (overlaps another AC), **Move** (belongs to another story) or **Remove** (redundant or no longer needed).

Present the review before any production code, with: the original AC, the outcome and reason, the proposed wording, affected stories or dependencies, and the expected change in scope and testing effort. Get explicit approval from the Product Owner, story owner or requesting user, even when no changes are proposed. Research and repository inspection may continue while approval is pending, but stay read-only.

### Approved story contract

Record in `docs/testcases/scrum_<n>_testcases.md`:

- Jira key, story title and user story;
- numbered ACs (`AC1`, `AC2`, …);
- included and excluded behaviour, with related Jira stories;
- actors and relationship permissions;
- allowed state transitions;
- persistence and atomicity requirements;
- assumptions and open questions.

Write each AC in one or two sentences with an observable outcome:

```text
AC<n>: Given <precondition>, when <actor action>, then <observable result>.
```

Each part maps onto the test case: **Given** → pre-conditions, **When** → test steps and data, **Then** → expected result. Refine checklist-style ACs into scenario ACs first; one checklist item usually yields several test cases.

## 2. Design test cases (5-step method)

Derive test cases from the approved ACs before implementation, in this order:

1. **Visualise the workflow.** Walk the feature as the user would, including what they might do wrongly (a name typed into a numeric field). Use existing screens, the design or the team when the feature is unfamiliar.
2. **Happy path.** The case that completes the story without errors. Run it first: if it fails, the other cases are not yet meaningful.
3. **Cross-cutting expectations.** Authentication, authorisation, accessibility, responsive UI, consistent error handling. Generic checks belong in the Definition of Done; write a dedicated case only when the concern produces story-specific behaviour (a role that sees a different control on this screen).
4. **Negative testing.** Erroneous input (wrong type, unsupported value, missing or blank field), business-rule exceptions (state changed after the user acted, stale or repeated action), and unavailable systems (Supabase, other services). Each case states the expected handling: error, refusal, unchanged state. An empty result for a valid query is a valid outcome, not an error; test that it is presented correctly.
5. **Partitions and boundaries.**
   - **Partition:** group inputs that should behave alike and test one representative from each group (one per status, role or enumerated value).
   - **Boundary:** wherever expected behaviour changes, test just below, exactly at and just above (19.99 / 20.00 / 20.01 for a 20.00 minimum), at both minimum and maximum.
   - Include implicit domain boundaries: dates, lengths, counts, time windows.

For security- and state-related categories (wrong role, unrelated owner, concurrent change, no-write side effects), also apply `security-and-state.md`.

Test cases must be concrete enough to run without interpretation: "log in as `staff01@test.local` with password `Test#1234`", not "log in". Each pre-condition names the seed or setup script, and test data is reset between runs.

For each high-risk rule, ask: **what plausible one-line bug should make this test fail?** If the answer is unclear, strengthen the assertion.

New cases that emerge during the sprint get a new ID in the matrix. If a new case changes the agreed scope or behaviour, return to the AC review gate first.

## 3. Test-case IDs and labels

### IDs

Format: `AC<n>-<letter><k>`.

| Letter | Technique | Example |
| --- | --- | --- |
| `H` | Happy path | `AC1-H1` |
| `P` | Equivalence partition | `AC2-P3` |
| `B` | Boundary | `AC3-B2` |
| `N` | Negative (input, business-rule exception, unavailable system) | `AC4-N1` |
| `X` | Cross-cutting, story-specific | `AC5-X1` |

When a case proves several ACs, the ID uses the primary AC and the matrix's `AC` column lists all of them. IDs are never reused or renumbered; a removed case stays in the matrix as retired.

### Labels in the code

Put a one-line comment directly above each automated test with the ID, the technique and the risk it proves, so a reader can trace the test to its AC without opening the matrix:

```python
# AC4-N1 (negative): rejects an unknown status and leaves the request unchanged
def test_rejects_unknown_status(client):
    ...
```

```ts
// AC3-B2 (boundary): accepts a booking of exactly 20 attendees
it("accepts a booking at the attendee limit", () => { ... });
```

- One comment per test, with exactly one technique: `happy`, `partition`, `boundary`, `negative` or `cross-cutting`.
- When a test proves several ACs, list them all: `# AC4-N2, AC5 (negative): ...`.
- For partitions written as one parametrized test, put the comment above the test and give each case its ID: `@pytest.mark.parametrize(..., ids=["AC2-P1", "AC2-P2", "AC2-P3"])`.
- Find tests by technique or ID with a search, e.g. `grep -rn "(negative)" backend frontend` or `grep -rn "AC4-" backend frontend`.

## 4. Traceability matrix

Every behaviour follows the chain: Jira story → AC → test-case ID → failing test → implementation → passing local evidence → pull-request evidence.

The story's test-case document holds the matrix in two parts.

**Specification** (written once; changes only when the requirement changes):

| ID | AC | Test scenario | Technique | Pre-conditions | Test steps | Test data | Expected result | Forbidden side effects | Layer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AC1-H1 | AC1 | The distinct risk this case proves | Happy / Partition / Boundary / Negative / Cross-cutting | State, actor and setup script | Numbered steps | Exact inputs | Observable output and stored state | What must not happen | Unit / API / DB / UI / E2E |

**Latest execution record** (updated on every run):

| ID | Automation status | Actual result | Execution status | Build or commit | Executed by and date | Remarks and evidence |
| --- | --- | --- | --- | --- | --- | --- |
| AC1-H1 | Planned / Red / Green | What happened | Pass / Fail / Blocked / Not executed | Commit SHA and environment | Name, date | Test path, CI link, defect link |

The scenario says **why the case exists**; it does not repeat the test name or steps. A result is only "passing as of that build": a new commit, environment or browser needs a new execution record.

## 5. TDD workflow

**Red.** Choose the smallest unimplemented behaviour. Write the lowest-level meaningful test, including at least one prohibited outcome when state, security or authorisation is involved. Run it and confirm it fails for the expected missing behaviour (a compile error, broken fixture or unavailable service is not a valid Red). Record `Red` in the matrix. Do not push the red commit (`commits.md`).

**Green.** Make the smallest production change that passes. Preserve behaviour outside the AC; no speculative abstractions or future-story behaviour. Run the focused test, then the related tests. Record `Green` with the command and result.

**Refactor.** Remove duplication and improve naming, keeping validation, authorisation and transaction boundaries visible. Re-run the focused and related suites.

**Integrate.** After rule-level tests pass, verify the boundaries: frontend action to API contract, controller to service and repository, repository to Supabase, database commit and rollback, and one critical browser journey. Mocks prove frontend behaviour but not the real API or database contract; say so, and keep at least one real integration check.

## 6. Test layers and unit-test rules

Use the lowest layer that proves the behaviour, without repeating identical assertions at every layer.

- **Unit and component:** validation and parsing, status rules and business invariants, role-specific rendering, empty/loading/success/error states, accessible names and keyboard operation.
- **API and service:** authentication and role, ownership or assignment, valid and invalid transitions, request and response contracts, error mapping, refused operations leaving state unchanged.
- **Database:** constraints and foreign keys, row locks and concurrency, atomic writes and rollback, immutable history, server-only functions and revoked browser-role access, deterministic ordering for "latest" records. Scripts against shared infrastructure run in a transaction and roll back unless committed fixture data is required.
- **End-to-end (Playwright):** one critical journey across frontend and API, role switching, persistence across reload, visible recovery from an unavailable dependency. Keep it focused; validation permutations belong in lower layers.

Rules for unit tests:

- **Assert every output and side effect:** each returned field, the stored state that changed, and the state that must not change.
- **Test helpers and rules directly when the full path hides a fault.** If two values are always equal by the time they reach a function, a bug that mixes them up passes every end-to-end test. Call the function directly with values that differ, and with non-default settings so hardcoded constants are caught.
- **Negative tests assert the specific failure** (exception type or HTTP status, and error code), then assert the state is unchanged.
- **Only assert refusals the requirement demands.** If the agreed rules do not say an input is invalid, raise it at the AC review gate instead of assuming the code rejects it.
- **Keep tests independent and deterministic:** no shared mutable state, no reliance on test order, and a frozen clock for time-based boundaries.

Performance, load and availability tests are added only when the Product Owner confirms such a requirement. Exploratory and usability findings become new test cases or defects.

## 7. Coverage and mutation testing

- Coverage shows which lines ran, not whether a test would notice them being wrong. A suite can reach 100% coverage and still miss many faults. Treat uncovered lines in business rules as missing test cases.
- For high-risk modules (status transitions, permission checks, calculations), run a mutation tool before marking the story Done. Each surviving mutant is either a missing test case (add it with a new ID) or an equivalent mutant (record why in the execution remarks).

> **Tooling status: not yet installed.** Backend coverage needs `pytest-cov` (`pytest --cov --cov-report=term-missing`), frontend coverage needs `@vitest/coverage-v8` (`npx vitest run --coverage`), and mutation testing needs `mutmut` (Python) or Stryker (TypeScript). Adding these dependencies is a separate team change, not part of a story.

## 8. Evidence

Never write only "tests passed". Record:

- the exact command or CI check;
- the date or commit;
- the number of tests passed, failed and skipped;
- the environment, and whether dependencies were mocked or real;
- warnings or limitations;
- a link or path to the evidence.

Classify each result as **Pass** (ran successfully on the current code), **Fail** (ran and missed the expected result), **Blocked** (could not run; name the missing dependency or permission) or **Not executed**. Earlier branch results, another developer's machine and a previous commit are not current evidence. Keep local, shared-database, browser and pull-request CI results separate; one does not substitute for another.

**Regression.** Automated tests from earlier stories run in CI on every pull request. Manual cases for features the change touches are re-run before the story is marked Done and recorded as new execution records.

## 9. Story test checklist

Before handing a story to the Definition of Done check (`definition-of-done.md`), confirm:

- [ ] The approved story contract and numbered ACs are recorded in `docs/testcases/scrum_<n>_testcases.md`.
- [ ] Every AC maps to one or more test cases covering the happy path, partitions, boundaries, negatives and any story-specific cross-cutting behaviour.
- [ ] Every test case has a scenario, pre-conditions, concrete steps and data, an observable expected result and its forbidden side effects.
- [ ] Every automated test has its label comment (§3).
- [ ] Required tests were seen failing for the intended reason before implementation (§5).
- [ ] AI-drafted test cases were reviewed by a team member (§10).
- [ ] The latest execution record is filled in with current evidence (§8).

## 10. AI-drafted test cases: generate, then curate

AI may draft test cases from the story and its ACs; every draft is reviewed against the 5-step method before it is accepted.

1. **Agree tests before code.** Never generate the implementation first and derive tests from it.
2. **Expect gaps where rules are implicit.** Drafts are strongest on happy paths and weakest on domain boundaries and business-rule negatives; check those by hand against Jira.
3. **Reject coverage theatre.** Each case proves a distinct risk; merge or delete duplicates.
4. **Check each expected result against the requirement,** not against what the code returns.
5. **Avoid shared blind spots.** When AI writes both code and tests, a human confirms the tests check the right behaviour. Record who reviewed the test design.
