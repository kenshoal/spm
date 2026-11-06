# ConnectSphere TDD and Traceability Standard

This file defines the shared delivery standard for ConnectSphere backlog work. It applies to frontend, backend, database and integration changes. A story is complete only when its acceptance criteria are implemented, tested and traceable to observable evidence.

## 1. Core principles

1. **Requirements are the test oracle.** Derive expected behaviour from the issue tracker, project requirements and agreed domain rules before inspecting or changing the implementation.
2. **Work in small vertical increments.** Each increment should produce one reviewable behaviour through the relevant layers rather than a large collection of partially connected changes.
3. **Use Red, Green, Refactor.** Record a meaningful failing test, implement the smallest valid change, then improve the design while keeping the suite green.
4. **Test observable behaviour and business invariants.** Avoid tests that merely repeat implementation details or pass only because they mock the same logic as the code under test.
5. **Prove forbidden side effects.** When an operation is refused, verify that protected data, status, history and related records remain unchanged.
6. **Keep story boundaries explicit.** Do not silently implement adjacent backlog stories or claim their behaviour as part of the current increment.
7. **Report evidence honestly.** Separate local results, shared-database verification, browser checks and pull-request CI. One does not substitute for another.

## 2. Establish the story contract

Before implementation or detailed test design, fetch the authoritative issue tracker story and review every acceptance criterion. Do not treat the existing wording as automatically ready for development.

### Acceptance-criteria review gate

Assess each criterion for:

- **Relevance:** it directly supports the user story and intended outcome;
- **Scope:** it can be completed within one story without absorbing another backlog item;
- **Specificity:** the actor, action, conditions and observable result are clear;
- **Testability:** a reviewer can determine pass or fail from observable evidence;
- **Independence:** it does not combine unrelated behaviours that should be split;
- **Consistency:** it agrees with the domain model, permitted roles and lifecycle rules;
- **Non-duplication:** it does not repeat another criterion in different words;
- **Dependency ownership:** external notifications, later workflow stages and other teams' responsibilities are identified rather than claimed as part of the story;
- **Proportionality:** the required work is reasonable for the story's value and estimate;
- **Outcome focus:** it describes required behaviour rather than prescribing unnecessary implementation details.

Flag every questionable criterion using one of these outcomes:

- **Keep:** clear, necessary and testable as written;
- **Clarify:** intent is valid, but wording or expected outcome is ambiguous;
- **Narrow:** criterion includes more behaviour than the story needs;
- **Split:** criterion contains independently deliverable or testable behaviours;
- **Merge:** criterion duplicates or substantially overlaps another criterion;
- **Move:** behaviour belongs to another existing or proposed issue tracker story;
- **Remove:** behaviour is redundant, irrelevant or no longer required.

Present the review before writing production code. Include:

1. the original criterion;
2. the review outcome and reason;
3. the proposed replacement wording;
4. affected dependencies or related issue tracker stories;
5. the expected change to scope and testing effort.

Obtain explicit approval from the Product Owner, story owner or requesting user for the revised scope. Record the approved wording in the issue tracker or the story test-case document. Do not begin detailed test breakdown, production implementation or database mutation until approval is recorded.

If no changes are proposed, still present the reviewed criteria and obtain approval that they are ready for development. Research, repository inspection and feasibility analysis may continue while approval is pending, but they must remain read-only.

### Approved story contract

After approval, record the following in `docs/testcases/scrum_<number>_testcases.md`:

- issue tracker key and story title;
- user story;
- numbered acceptance criteria (`AC1`, `AC2`, and so on);
- included behaviour;
- excluded behaviour and related issue tracker stories;
- actor and relationship permissions;
- allowed state transitions;
- persistence and atomicity requirements;
- assumptions or unresolved requirement questions.

Acceptance criteria must be independently testable. Use one or two sentences per criterion and describe an observable outcome. Split criteria that combine unrelated behaviours.

### Acceptance-criterion format

```text
AC<n>: Given <precondition>, when <actor action>, then <observable result>.
```

Add authorization, validation, persistence or atomicity details when they materially affect the result.

## 3. Build the traceability chain

Every implemented behaviour must follow this chain:

```text
Issue tracker story
  -> Acceptance criterion
  -> Test-case ID
  -> Failing automated test or verification script
  -> Implementation files
  -> Passing local evidence
  -> Pull-request evidence
```

Use stable test-case IDs such as `AC2-T1`. Include the ID in the test name or a nearby one-line purpose comment when practical.

Maintain this matrix in the story test-case document:

| ID | AC | One-line purpose | Preconditions | Input | Action | Expected result | Forbidden side effects | Layer | Automation status | Evidence |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AC1-T1 | AC1 | Explains the distinct risk this case proves. | Required state and actor | Boundary or representative input | Operation performed | Observable output and stored state | Data or actions that must not occur | Unit/API/DB/UI/E2E | Planned/Red/Green/Blocked | Test path and latest result |

The purpose comment explains **why the case exists**. It should not repeat the test name or implementation steps.

## 4. TDD workflow

### Step 1: Red

1. Choose the smallest unimplemented acceptance behaviour.
2. Write the lowest-level meaningful test that proves it.
3. Add at least one prohibited outcome when state, security or authorization is involved.
4. Run the focused test and confirm it fails for the expected missing behaviour.
5. Record the failing result in the test matrix as `Red`.

A compilation error, incorrect fixture or unavailable service is not a valid Red result.

### Step 2: Green

1. Implement the smallest production change that satisfies the failing test.
2. Preserve existing behaviour outside the criterion.
3. Run the focused test until it passes.
4. Run directly related tests to detect local regressions.
5. Update the matrix to `Green` with the command and result.

Do not add speculative abstractions or future-story behaviour to make one test pass.

### Step 3: Refactor

1. Remove duplication and improve naming or separation of concerns.
2. Keep validation, authorization and transaction boundaries visible.
3. Run the focused and related suites again.
4. Stop when the increment is clear and reviewable.

### Step 4: Integrate

After rule-level tests pass, verify the relevant boundaries:

- frontend action to API contract;
- controller to service and repository;
- repository to Supabase function or table;
- database commit, rollback and concurrency behaviour;
- one critical browser journey across the layers.

Mocks may prove frontend behaviour, but they do not prove the real API or database contract. State that limitation and retain at least one appropriate integration check.

## 5. Test-layer responsibilities

Use the lowest effective layer and avoid duplicating identical assertions everywhere.

### Unit and component tests

- validation and parsing;
- status rules and business invariants;
- role-specific rendering and controls;
- empty, loading, success and error states;
- accessibility names and keyboard-operable controls.

### API and service tests

- authentication and actor role;
- ownership or assignment relationship;
- valid and invalid state transitions;
- request and response contracts;
- error mapping;
- refused operations leave state unchanged.

### Database verification

- constraints and foreign keys;
- row locks and concurrent operations;
- atomic writes and rollback behaviour;
- immutable history where required;
- server-only functions and revoked browser-role access;
- deterministic ordering when selecting the latest record.

Database verification scripts must run inside a transaction and roll back when they target shared infrastructure, unless the test specifically requires committed fixture data.

### End-to-end tests

- one critical user journey spanning the frontend and API contract;
- role switching when the workflow crosses actors;
- persistence across navigation or reload;
- visible recovery from an unavailable dependency;
- retained history or state after later workflow actions.

Keep E2E coverage focused. Do not move every validation permutation into Playwright.

## 6. Required test categories

Apply the categories relevant to the story:

- happy path;
- missing, blank and malformed values;
- minimum, maximum and just-outside boundaries;
- unauthenticated caller;
- wrong role;
- unrelated owner or assignee;
- stale or repeated action;
- invalid source status;
- concurrent action or changed state;
- upstream/database failure;
- no-write or no-disclosure side effects;
- persistence and reload;
- empty, loading and error UI;
- accessibility and responsive presentation.

For each high-risk rule, ask: **What plausible one-line bug should make this test fail?** If the answer is unclear, strengthen the assertion.

## 7. State and transaction rules

For workflows that change stored state:

1. Validate the current stored state inside the transaction.
2. Recheck ownership, assignment or role at mutation time.
3. Lock the authoritative row when concurrent decisions are possible.
4. Write the status, related record and required history atomically.
5. Reject stale, repeated and disallowed transitions without partial writes.
6. Return a deterministic conflict or authorization response.
7. Test both the successful mutation and the absence of side effects on failure.

Status history is distinct from detailed business records. For example, a review-decision record may retain a clarification exchange while a status-history record captures the transition itself.

## 8. Security and visibility rules

Do not rely on hidden buttons as authorization. Enforce access in the backend and database boundary.

For protected resources, test:

- missing or expired authentication;
- permitted role with the correct relationship;
- permitted role without the relationship;
- unrelated roles;
- reassignment between page load and mutation;
- direct access to underlying tables or functions;
- information disclosure through error messages or history endpoints.

Prefer `404` when revealing the existence of another user's resource would disclose protected information. Use `403` when the resource relationship is already established and the caller lacks the required capability.

## 9. Evidence standard

Never write only “tests passed.” Record:

- exact command or CI check;
- date or commit when useful;
- number of tests passed, failed or skipped;
- environment used;
- whether dependencies were mocked or real;
- warnings or limitations;
- link or path to evidence.

Classify evidence as:

- **Passed:** executed successfully for the current code state;
- **Failed:** executed and did not meet the expected result;
- **Blocked:** could not run because a named dependency or permission is unavailable;
- **Unverified:** not executed for the current code state.

Earlier branch results, another developer's machine and a previous commit are not current evidence.

## 10. Definition of Done

A story is **Done** only when every applicable item is satisfied:

- [ ] issue tracker user story and numbered acceptance criteria are current.
- [ ] Acceptance criteria were reviewed for breadth, duplication, ambiguity, dependencies and testability.
- [ ] Proposed acceptance-criteria changes were explicitly approved before detailed test design or implementation began.
- [ ] The approved acceptance-criteria wording and scope decision are recorded.
- [ ] Scope, exclusions, dependencies and assumptions are documented.
- [ ] Every acceptance criterion maps to one or more meaningful test cases.
- [ ] Each test case has a one-line purpose and observable expected result.
- [ ] Required tests were observed failing before implementation for the intended reason.
- [ ] Every acceptance criterion has reviewable implementation evidence.
- [ ] Authentication, authorization and relationship boundaries are tested.
- [ ] Validation, boundaries and forbidden side effects are tested.
- [ ] Persistence, state transitions and atomicity are verified where applicable.
- [ ] Loading, empty, error, success and accessibility states are checked where applicable.
- [ ] Migration, API, environment and setup documentation is updated.
- [ ] Focused tests and related regression tests pass.
- [ ] Lint, type checking, build and relevant service checks pass.
- [ ] One critical integration or E2E path passes.
- [ ] Shared-database verification is recorded separately when applicable.
- [ ] The exact pushed commit passes pull-request CI.
- [ ] Reviewer feedback is resolved or explicitly accepted.
- [ ] No unrelated story is claimed as completed.

Use these final classifications:

- **Done:** all applicable criteria and quality gates have current evidence.
- **Partially verified:** implementation appears complete, but named evidence or checks are missing.
- **Not done:** required behaviour is missing or a required check fails.

## 11. Pull-request traceability

Each pull request should contain:

1. The issue tracker task link;
2. problem and resulting behaviour;
3. scoped changes;
4. acceptance-criterion and test-evidence document path;
5. validation commands and results;
6. dependencies and excluded stories;
7. migration or rollback notes;
8. risks and remaining unverified work;
9. reviewer checklist derived from the acceptance criteria.

Keep implementation commits small and use the repository's Conventional Commit format.

## 12. Standard iteration sequence

Use this sequence for each backlog task:

```text
1. Fetch and confirm the issue tracker story.
2. Review every acceptance criterion for scope, clarity, duplication, dependencies and testability.
3. Flag each criterion as Keep, Clarify, Narrow, Split, Merge, Move or Remove.
4. Present the proposed scope and acceptance criteria for explicit approval.
5. Record the approved wording and scope decision.
6. Define exclusions, dependencies and assumptions.
7. Create the acceptance-criteria test matrix.
8. Select one vertical behaviour.
9. Write and observe a meaningful failing test.
10. Implement the smallest change.
11. Make the focused test pass.
12. Refactor and run related regressions.
13. Repeat for the next approved behaviour.
14. Run integration, E2E and quality gates.
15. Update evidence and documentation.
16. Push and verify PR CI before marking Done.
```

When requirements and implementation disagree, stop treating the implementation as correct by default. Resolve the requirement through the issue tracker or an explicit team decision, then update the acceptance criteria and tests before continuing.
