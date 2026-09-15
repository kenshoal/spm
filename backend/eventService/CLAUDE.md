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

## Original schedule (superseded below — see Revised schedule)

Blocking: Story B's cancel/complete role checks were initially only
exercised with `coordinator_id` set directly in the DB in tests — there was
no real assignment path yet. Days 1–3 closed that gap.

- ✅ **Day 1–2**: `POST /events/{id}/coordinator` — assign one Coordinator to
  a Submitted event. Reject if the event isn't Submitted yet. Assignment
  does not change status (stays Submitted). Tests.
- ✅ **Day 3**: Reassignment — same endpoint allows changing the assigned
  Coordinator. Tests for reassign, and for the previous Coordinator losing
  cancel/complete rights once reassigned (this caught a real bug: the
  Completed check only verified role, not the specific assigned Coordinator).
- **Day 4**: Restrict the Submitted→Under Review transition so only the
  *assigned* Coordinator can trigger it via `POST /events/{id}/status` —
  confirms "assignment alone does not move it to Under Review." Tests.
- **Day 5**: Notification on assign/reassign — minimal notifier interface
  (stub/outbox-record, per plan for a future Notification System) fired on
  assignment. Tests.
- **Day 6–7**: Role-appropriate status visibility — relationship-based
  access (Organiser/Coordinator/etc. per their relationship to *that* event)
  plus field shaping (an Attendee sees less than an Organiser). Tests.
- **Day 8**: Replace remaining test-only shortcuts with real authorization
  checks consistent across all endpoints — including `GET /events/{id}`,
  which currently has no auth check at all.
- **Day 9**: End-to-end lifecycle tests using real assignment (not
  DB-injected `coordinator_id`): create → submit → assign → review start →
  approve → plan → confirm → complete; plus cancel and discard paths.
- **Day 10**: Buffer — review fixes, README/API docs update, demo prep.

(Unplanned but done along the way: migrated the DB from local Postgres to
the shared Supabase project, `event_service` schema — see 2026-09-15.)

## Revised schedule — 3 working days left (today, Thu, Sun)

Days 1–3 above are done. What's left (original Days 4–10, one detour spent
on the Supabase migration instead of Day 4) is compressed into 3 sessions,
grouped by what belongs together rather than split evenly line-by-line:

- **Today**: finish Story A — Day 4 (restrict review-start to the assigned
  Coordinator) + Day 5 (notification stub). Small, both Coordinator-
  assignment-adjacent, closes Story A entirely.
- **Thursday**: Story B's remaining gaps — Day 6–7 (role-appropriate
  visibility) + Day 8 (real authorization everywhere, incl. the
  `GET /events/{id}` gap). The largest remaining chunk; grouped because
  visibility and authorization are the same underlying question of "who
  can see/do what."
- **Sunday**: Day 9 (end-to-end lifecycle tests with real assignment) +
  Day 10 (buffer, docs, demo prep). Last pass before submission — testing
  and polish, not new endpoints.

## Open questions to resolve early (Week 1, Day 1)

- Does "notified" require a real notification channel this sprint, or is a
  stub acceptable? (Plan above assumes stub.)
- What does "appropriate to role" mean for visibility — hidden fields, or
  just read/no-read access to the event at all?
