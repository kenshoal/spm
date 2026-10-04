# Definition of Done

Read this before deciding whether a story is Done.

The Definition of Done (DoD) is the Scrum Team's shared quality standard for the Increment. It applies to every story. Story-specific checks (test-case design, labelling, evidence) live in `testing.md`.

**How it changes:** the team inspects the DoD at every Sprint Retrospective. Agreed changes are committed as `docs(standards): …` after the retrospective and apply from the next sprint, never mid-sprint. The git history of this file records when and why each change was made.

## Checklist

A story is **Done** only when every applicable item is met for the current code:

- [ ] Every applicable acceptance criterion has implementation evidence.
- [ ] Acceptance criteria map to meaningful test cases, and each test is labelled with its test-case ID and technique.
- [ ] Required unit, API, integration and browser tests pass, and tests from earlier stories still pass.
- [ ] Authentication, authorisation and forbidden side effects are tested where applicable.
- [ ] Accessibility and UI behaviour are checked where applicable.
- [ ] Lint, type checking, build and database verification pass where applicable.
- [ ] Affected documentation and diagrams are updated.
- [ ] AI-generated code and tests were reviewed and understood by a human team member.
- [ ] The pull request is reviewed, all required CI checks pass, and the work is merged into `dev` and runs in the integrated stack.

A story that does not meet the DoD does not count toward velocity and returns to the Product Backlog for re-planning. Product Owner feedback from the Sprint Review is recorded in the review notes or Jira, not as a DoD item.
