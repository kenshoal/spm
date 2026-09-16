# eventService — Sprint Plan

## Scope change (2026-09-16)

Originally two stories: Coordinator Assignment (SCRUM-14) and Event Status
(SCRUM-28). Discovered both stories described one continuous event
lifecycle, split across this service and Heng Rui's `eventRequestService`
with no connection between them — his story even names SCRUM-14 directly
("after assignment through SCRUM-14, the assigned Coordinator can access
it for review").

Resolved: **one shared Supabase database, two tables, clean split**.
- His `event_requests` table: event creation, drafting, submission,
  and now **status** too (SCRUM-28 handed to him — whoever owns event
  creation should own its lifecycle).
- This service's `event_coordinator_assignments` table: who's assigned,
  and the full history of assignments. Nothing else.

This service was rebuilt around that on 2026-09-16 (see `app/models.py`,
`app/routers/assignments.py`). Days 1–3 below (original Coordinator
Assignment build) mostly still stands conceptually; the code itself was
reworked to point at his table instead of a local `Event` row.

## Story (current scope)

**Coordinator Assignment** (Event Operations Manager, SCRUM-14)
Assign an Event Coordinator to a submitted event request; assignment alone
doesn't change status; only the assigned Coordinator starting review moves
it to Under Review (his logic, gated on data from this service); Coordinator
is notified; reassignment is supported.

## Done

- ✅ `POST /event-requests/{id}/coordinator` — assign/reassign, Operations-
  Manager-only, refused before submission and once the request is terminal.
- ✅ `GET /event-requests/{id}/coordinator` — current assignment. This is
  the integration point his status logic needs to call for the cancel/
  complete permission check ("only the assigned Coordinator").
- ✅ Full assignment history preserved (new row per assignment, not an
  overwrite) — caught and fixed a real ordering bug (timestamp resolution
  isn't reliable for "which assignment is latest"; fixed to order by an
  autoincrementing id instead).
- ✅ 10/10 tests passing, `ruff check .` clean, table created on the real
  Supabase project, confirmed reading his live `event_requests` table works.

## Remaining — 2 working days left (Thursday, Sunday)

- **Thursday**:
  - Confirm the full status value set with Heng Rui and update
    `_DRAFT_STATUS` / `_TERMINAL_STATUSES` in `app/routers/assignments.py`
    to match exactly — currently a guess (`Completed`, `Cancelled`,
    `Rejected`), since his table so far only has Draft/Submitted defined.
  - Confirm with him that his review-start and cancel/complete logic
    actually calls this service's `GET /event-requests/{id}/coordinator`
    — pair on wiring this if it isn't done on his side yet.
  - Build the notification stub for "Coordinator is notified of
    assignment" — still not built. Outbox-record pattern (per the team's
    planned future Notification System), fired from `assign_coordinator`.
  - If real Supabase Auth users exist by then, do a real live
    create → submit → assign round trip (blocked today — his
    `event_requests.organiser_id` has a foreign key to `auth.users`, and
    none exist yet).

- **Sunday**:
  - Full lifecycle integration test with Heng Rui together: create →
    submit → assign → his review-start check → cancel/complete gated on
    assignment.
  - Polish: error messages, edge cases surfaced by the integration test.
  - Open the PR: `feat/coordinator-assignment` → `dev`. Coordinate merge
    order with his branch — separate files/tables, low conflict risk, but
    decide who merges first.
  - Buffer for whatever the end-to-end pass turns up.

## Resolved questions

- Notification: stub/outbox-record, not a real channel this sprint.
- Role-appropriate status visibility: no longer this service's concern —
  moved to Heng Rui with SCRUM-28.
