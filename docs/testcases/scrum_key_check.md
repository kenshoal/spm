# Jira key check: SCRUM-42, 43, 44, 46, 47, 49 (and SCRUM-6)

Checked 1 November 2026, read-only, branch `docs/testcase-gap-sweep`. Jira was not available to this sweep, so this is the repo side only: `git log --all --oneline --grep="<key>"` per key, `git branch -a` name checks, merge-commit title checks, and a recursive word-boundary grep for `SCRUM-<key>` (plus `scrum-<key>`, `scrum_<key>` variants) across `docs/`, `backend/`, `frontend/`, `database/` and `Claude outputs/` in `.md`, `.py`, `.ts`, `.tsx`, `.sql`, `.mjs` and `.json`.

## Findings

| Key | Repo evidence found | What scrum_10 says (SCRUM-49 only) | Likely explanation |
| --- | --- | --- | --- |
| SCRUM-42 | None. No commit on any branch, no branch name, no file reference in any naming variant | — | Not determinable from the repo. Deleted, merged into another key, or never worked on here; only Jira can say |
| SCRUM-43 | None (same search) | — | As SCRUM-42 |
| SCRUM-44 | None (same search) | — | As SCRUM-42 |
| SCRUM-46 | None (same search) | — | As SCRUM-42 |
| SCRUM-47 | None (same search) | — | As SCRUM-42 |
| SCRUM-49 | Referenced in exactly one file: `docs/testcases/scrum_10_testcases.md`, lines 13 and 41 (also mirrored in `.claude/work/*` copies of that file). No code, no commits, no branch, no test-case doc of its own | Line 13: listed among SCRUM-10's "Related" stories ("Related: SCRUM-33, SCRUM-49, SCRUM-16"). Line 41: named under Excluded, "named, not claimed": "flagging reservations when an event is rescheduled or equipment is marked damaged (SCRUM-49)" | A real follow-up story known to SCRUM-10's design (equipment-reservation flags on reschedule or damage) that was never started in this repo. It may equally have been renumbered or deleted; only Jira can say |

**For the record: SCRUM-6.** Jira reports it as not found and the project's lowest issue is SCRUM-8. The repo has no standalone `SCRUM-6` reference either — an unbounded grep only matches `SCRUM-63/64/67` as substrings. That is consistent with SCRUM-1 to SCRUM-7 never existing or being cleared before this repo's work began, which the repo cannot confirm.

## Recommended action

Before removing any of these keys from the tracking sheet, ask the Product Owner or Jira admin whether each was **deleted, merged/duplicated, or renumbered**. Two specifics:

1. **SCRUM-49** is not an empty slot: SCRUM-10's approved contract names its behaviour (flag reservations when an event is rescheduled or equipment is marked damaged) as excluded, owned elsewhere. Ask where that behaviour lives now — if the story was dropped rather than renumbered, that is a scope decision to record, not a silent cleanup.
2. **SCRUM-42/43/44/46/47** leave no trace here, so nothing in the repo depends on their fate; the sheet row and the Jira answer are the only records.

If a key turns out to be a duplicate of one already tracked, treat the sheet row as a duplicate reference rather than a missing story.
