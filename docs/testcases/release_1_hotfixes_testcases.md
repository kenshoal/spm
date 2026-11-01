# Release 1 hotfixes: test cases and evidence

Last reviewed: 1 November 2026

Status: **built and verified on 1 November 2026 by Kennedy.** The scope is the 18 gaps found when the whole app was run against the Week 1 brief, the Week 4 and Week 7 documents and the GitHub discussions. Product Owner (Jaren) confirmation of the open decisions in the last section is still needed.

These are corrections, not new stories. Each one traces to a customer source, and to the Jira story whose criteria it completes where there is one. IDs follow `AC<n>-<technique><k>`, where `<n>` is the hotfix number below. Every automated test carries its ID in a comment.

## Hotfixes

| # | Gap | Customer source | Story it completes | Layer |
| --- | --- | --- | --- | --- |
| 1 | The served registration service had no notifier, so no registration notice was ever sent | SCRUM-38 AC1, AC2 | SCRUM-22, SCRUM-38 | API wiring |
| 2 | The waiting-list timer called repository methods only the test fake had, and Compose never switched it on | Q&A #44 | SCRUM-24 | API wiring, Compose |
| 3 | The Safety Officer could not reject | Week 7 change 6, Q&A #130 | SCRUM-60 | DB (0069), API, UI |
| 4 | Nobody could set the registration period or capacity | Q&A #30, #42, #127 | SCRUM-21 | DB (0070), API, UI |
| 5 | Attendees had no screens; the public view had no venue | Feature 18, Q&A #49, #97 | SCRUM-21, 22, 24 | API, UI |
| 6 | No form to request a venue for an event | Feature 12 | SCRUM-32, 61, 67 | UI |
| 7 | No equipment screens (record, check, reserve, review) and no waiting-list override screen | Features 15 to 17, Q&A #26 | SCRUM-10, 13, 33, 24 | API, UI |
| 8 | The Coordinator could not update event details | Feature 7, Q&A #102 | SCRUM-29 | DB (0077), API, UI |
| 9 | Change requests were refused once an event was Confirmed | Week 1 brief, Q&A #8, #105 | SCRUM-35 | DB (0071), API, UI |
| 10 | Cancelling an event left its bookings and reservations committed | Week 1 brief, Q&A #60 | SCRUM-57 | DB (0073) |
| 11 | Reservations could not be released or replaced | Q&A #114 | SCRUM-13, 64 | DB (0072), API, UI |
| 12 | Suitability ignored the capacity of the chosen layout | Q&A #112 | SCRUM-12, 30 | DB (0074), API, UI |
| 13 | Venue edits did not flag the bookings they affect | Q&A #120, #122 | SCRUM-23, 63 | DB (0075) |
| 14 | The Organiser could not see what was booked or reserved | Week 1 brief step 10 | SCRUM-34 | API, UI |
| 15 | Cancellation notices did not reach venue and equipment staff | SCRUM-57 AC1b | SCRUM-57 | API |
| 16 | Registration lists showed account ids only | SCRUM-25 manual lookup, Q&A #32 | SCRUM-25, 34 | DB (0076), API, UI |
| 17 | `POST /notifications/events` accepted anyone | Q&A #91 | SCRUM-57 | API |
| 18 | Workspace links were hidden on phones | Week 1 brief section 7 | none | UI |

## Rules chosen where the customer left room (team design proposals)

- **Confirmed events (9).** The assigned Coordinator may reject or approve a change on a Confirmed event. If applying it flags an existing arrangement, the event returns to Planning in the same transaction, goes through the safety check again, and the Organiser (Q&A #105) and registered Attendees are told. A change that flags nothing leaves it Confirmed.
- **Capacity per layout (12).** Judged by the chosen layout's capacity when it has one, otherwise `max_capacity`. Events record no layout, so venue flagging (13) uses the venue's maximum capacity only.
- **Releasing (11).** A release moves the row to an audit table, so every existing reader stops counting it. A replacement is a release followed by a normal reservation, which reruns every check.
- **Cancelling (10).** Pending and approved bookings become `cancelled`; reservations are released with reason `Event cancelled`; requirements are kept.

## Not claimed here (decisions for the Product Owner)

Manual check-in only, QR withdrawn; partly accepted change requests (#104); a `Withdrawn` event status (#103); postponement without a date (#69, #121); changing an event's Organiser (#59, #61); VIPs above normal capacity (#99); technical support in the safety readiness check (#80, #106); block reasons "equipment failure" and "other"; lifting a block early; venue operating hours (SCRUM-30); hiding Cancel on Completed events; recording the final end of a Confirmed event.

## Latest execution record (1 November 2026, Kennedy's machine, branch `fix/release-1-hotfixes`)

| Check | Command | Result | Environment |
| --- | --- | --- | --- |
| eventRequestService | `pytest -q`; `ruff check .` | 1133 passed, 1 skipped; clean | local, fakes for Supabase |
| venueService | `pytest -q`; `ruff check .` | 743 passed, 10 skipped; clean | local |
| equipmentService | `pytest -q`; `ruff check .` | 337 passed; clean | local |
| notificationService | `pytest -q`; `ruff check .` | 85 passed; clean | local |
| frontend | `npx vitest run`; `npm run lint`; `npm run typecheck` | 676+ passed; clean; clean | local, jsdom |
| Database | `database/verify_release_1_hotfixes.sql` after all 83 migrations on vanilla PostgreSQL 16 with `database/tests/ci_platform_stub.sql` | ALL RELEASE 1 HOTFIX VERIFICATIONS PASSED | Docker, disposable |
| Database mutation check | eight one-line faults in 0069 to 0077 | all eight caught (one needed AC13-N3 added) | Docker, disposable |
| Existing database verifiers | the CI paths for SCRUM-35, 40 and 18 | pass with the new migrations | Docker, disposable |
| Whole stack | five services, Next.js, GoTrue, PostgREST and Postgres in Docker; a scripted lifecycle with every role, then clicks in the browser | each hotfix behaved as specified (details in the pull request) | local, disposable |

**Not run:** the shared Supabase database, real email delivery, Playwright, and the pull-request CI.

**Found and fixed while verifying:** the new venue-change trigger first used the lowest layout capacity and so missed a real capacity drop; the coordinator update returned the row from before the review trigger reopened the event; a client component imported a server-only module (unit tests mock it, only the running app failed); the cancel trigger cast a text coordinator id to a uuid.
