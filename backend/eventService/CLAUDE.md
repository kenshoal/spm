# eventService — Sprint Plan

Two-week sprint, two user stories. Status logic (state machine + role-gated
cancel/complete/discard) is already scaffolded — see `app/status.py` and
`app/routers/events.py`. What's below is the remaining work, split evenly
across the two weeks.

## Stories

**A — Coordinator Assignment** (Event Operations Manager)
Assign an Event Coordinator to a Submitted event; assignment alone doesn't
change status; only the assigned Coordinator starting review moves it to
Under Review; Coordinator is notified; reassignment is supported.

**B — Event Status** (Event Coordinator)
Exactly one current status at a time, moved only along allowed transitions;
Coordinator-only cancel/complete once assigned; Organiser-only discard of an
unsubmitted Draft; status visible to users with access, appropriate to role.

## Week 1 — Coordinator Assignment (Story A)

Blocking: Story B's cancel/complete role checks are currently only
exercised with `coordinator_id` set directly in the DB in tests — there's no
real assignment path yet. This week closes that gap.

- **Day 1–2**: `POST /events/{id}/coordinator` — assign one Coordinator to a
  Submitted event. Reject if the event isn't Submitted yet. Assignment does
  not change status (stays Submitted). Tests.
- **Day 3**: Reassignment — same endpoint allows changing the assigned
  Coordinator. Tests for reassign, and for the previous Coordinator losing
  cancel/complete rights once reassigned.
- **Day 4**: Restrict the Submitted→Under Review transition so only the
  *assigned* Coordinator can trigger it via `POST /events/{id}/status` —
  confirms "assignment alone does not move it to Under Review." Tests.
- **Day 5**: Notification on assign/reassign — minimal notifier interface
  (stub/log-based is fine for this sprint, swappable later) fired on
  assignment. Tests. Mid-sprint check-in.

## Week 2 — Status Visibility & Integration (Story B gaps + hardening)

- **Day 6–7**: Role-appropriate status visibility — define what each role
  should see on an event (e.g. Organiser vs Coordinator vs uninvolved
  viewer) and implement the scoping on read endpoints. Tests.
- **Day 8**: Replace remaining test-only shortcuts with real authorization
  checks consistent across all endpoints (audit `dependencies.py` usage in
  every route).
- **Day 9**: End-to-end lifecycle tests using real assignment (not
  DB-injected `coordinator_id`): create → submit → assign → review start →
  approve → plan → confirm → complete; plus cancel and discard paths.
- **Day 10**: Buffer — review fixes, README/API docs update, demo prep.

## Open questions to resolve early (Week 1, Day 1)

- Does "notified" require a real notification channel this sprint, or is a
  stub acceptable? (Plan above assumes stub.)
- What does "appropriate to role" mean for visibility — hidden fields, or
  just read/no-read access to the event at all?
