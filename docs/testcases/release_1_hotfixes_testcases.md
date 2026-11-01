# Release 1 hotfixes: test cases and evidence

Last reviewed: 1 November 2026

Status: **built and verified on 1 November 2026 by Kennedy.** The scope is the 25 gaps found when the whole app was run against the Week 1 brief, the Week 4 and Week 7 documents and the GitHub discussions. Hotfixes 20 to 25 are customer rulings from the discussions that had an answer and were not built. Product Owner (Jaren) confirmation of the few open points in the last section is still needed.

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
| 19 | A venue could not be blocked for "equipment failure" or "other" | Week 7 change 2 | SCRUM-23 | DB (0078), API, UI |
| 20 | A change request could only be approved or rejected whole | Q&A #104 | SCRUM-35 | DB (0079), API, UI |
| 21 | A request under review could not be recorded as withdrawn | Q&A #103 | SCRUM-17, SCRUM-28 | DB (0080), API, UI |
| 22 | An event could not be postponed without a new date | Q&A #69, #121 | none (backlog E1-2) | DB (0080, 0081), API, UI |
| 23 | A VIP could not be added once normal registration was full | Q&A #99 | SCRUM-41 | DB (0082), API, UI |
| 24 | Nothing could change an event's Event Organiser | Q&A #59, #61 | none | DB (0083), API, UI |
| 25 | Every unreserved equipment requirement blocked confirmation | Q&A #80, #106 | SCRUM-33, SCRUM-58 | DB (0084), API, UI |

## Rules chosen where the customer left room (team design proposals)

- **Confirmed events (9).** The assigned Coordinator may reject or approve a change on a Confirmed event. If applying it flags an existing arrangement, the event returns to Planning in the same transaction, goes through the safety check again, and the Organiser (Q&A #105) and registered Attendees are told. A change that flags nothing leaves it Confirmed.
- **Capacity per layout (12).** Judged by the chosen layout's capacity when it has one, otherwise `max_capacity`. Events record no layout, so venue flagging (13) uses the venue's maximum capacity only.
- **Releasing (11).** A release moves the row to an audit table, so every existing reader stops counting it. A replacement is a release followed by a normal reservation, which reruns every check.
- **Cancelling (10).** Pending and approved bookings become `cancelled`; reservations are released with reason `Event cancelled`; requirements are kept.
- **Block reasons (19).** Week 7 change 2 names the reasons, so equipment failure and other are added beside the existing four. `internal_use` stays (removing an enum value breaks stored rows) and counts as one of the "other operational reasons". A detail is not forced for "other"; that is the Venue Staff's call.

- **Partial approval (20).** The Coordinator picks the fields to accept and gives a reason for each field not accepted. The request is narrowed to the accepted fields and goes through the same approval as a whole request, so every existing check, flag and booking-plan rule applies. It ends `Partially Approved`; the refused fields, their values and reasons are kept and shown to the Organiser. All-accepted is the ordinary approval and none-accepted the rejection.
- **Withdrawn (21).** Only the assigned Coordinator records it, from Submitted, Under Review or Changes Requested (the customer said "while under review"). It is a status of its own, closed like Cancelled, and the Organiser is told.
- **Postponed (22).** From Approved, Planning, Safety Review or Confirmed, with a reason. Bookings, tentative holds and equipment reservations are released (reservation reason `Event postponed`); the event, its requirements and its registrations are kept. A postponed event cannot take a venue booking or an equipment requirement. Giving it a new date returns it to Planning, so it is booked and confirmed again. The Organiser, registered Attendees and the staff whose bookings were released are told. The same migration now also refuses a venue booking request for any Draft, Completed, Cancelled, Rejected, Withdrawn or Postponed event; before, the database checked no status at all.
- **VIPs (23).** A manual add is refused only when the places taken have reached both the registration capacity and the seats of the event's approved venues (each venue counted once). Self-registration and the waiting list still stop at the registration capacity. An event with no approved venue has no room above its capacity.
- **Change of Organiser (24).** The customer did not say who does it; the team's proposal is the Coordinator assigned to the event. The new Organiser must already hold the Event Organiser role and, when the event belongs to a client organisation, be a member of it. Not for Draft, Completed, Cancelled, Rejected or Withdrawn events. A pending change request moves to the new Organiser; the change, who made it and why are kept; both people are told.
- **Essential requirements (25).** Essential by default, so nothing changes until the assigned Coordinator marks one not essential with a note of what was agreed with Technical Support. The readiness check then leaves it out, so the event can go to its safety review and be confirmed; it can still be reserved later, and marking it essential again puts it back. Technical Support sees the flag and the note.

## Not claimed here (the customer's answers do not settle these)


- Whether the safety check must also require a Technical Support Staff assignment. The system does not record that an event needs technical support (backlog E4-2, beyond Release 1), so only equipment can be checked (25). Q&A #80 and #106 are met for equipment.
- Manual check-in only, by the assigned Coordinator. Q&A #38 allows "QR code or manual" at the counter by authorised internal staff, so manual meets it; a QR scan is not built.
- Lifting a block early, venue operating hours (SCRUM-30), hiding Cancel on Completed events, and recording the final end of a Confirmed event. These come from the team's own review, not from a customer answer.

## Superseded: earlier "not claimed" list

An earlier version of this section listed partly accepted change requests (#104), a Withdrawn status (#103), postponement without a date (#69, #121), changing the Organiser (#59, #61), VIPs above capacity (#99) and technical support in the safety check (#80, #106) as Product Owner decisions. They were not: the customer had answered each, and they are hotfixes 20 to 25.

## Latest execution record (1 November 2026, Kennedy's machine, branch `fix/release-1-hotfixes`)

| Check | Command | Result | Environment |
| --- | --- | --- | --- |
| eventRequestService | `pytest -q`; `ruff check .` | 1194 passed, 1 skipped; clean | local, fakes for Supabase |
| venueService | `pytest -q`; `ruff check .` | 747 passed, 10 skipped; clean | local |
| equipmentService | `pytest -q`; `ruff check .` | 354 passed; clean | local |
| authService | `pytest -q` | 60 passed | local |
| notificationService | `pytest -q`; `ruff check .` | 85 passed; clean | local |
| frontend | `npx vitest run`; `npm run lint`; `npm run typecheck`; `npm run build` | 742 passed; clean; clean; builds | local, jsdom |
| Playwright | `playwright test` against the mock APIs in `e2e/support`, with the cached Chromium 1148 headless shell (the pinned build was not installed and was not downloaded) | 59 passed | local; a first run found 20 failures, all from the mocks not knowing coordinator sessions, and one duplicated-text clash that moved the edit form behind a button |
| Database | `database/verify_release_1_hotfixes.sql` after all 90 migration files on vanilla PostgreSQL 16 with `database/tests/ci_platform_stub.sql` | ALL RELEASE 1 HOTFIX VERIFICATIONS PASSED | Docker, disposable |
| Database mutation check | eight one-line faults in 0069 to 0077, the verifier run without 0078, and ten more in 0079 to 0084 | all caught (one needed AC13-N3 added); AC19-H1 fails without 0078 | Docker, disposable |
| Existing database verifiers | the CI paths for SCRUM-35, 40 and 18; and all 57 `verify_*.sql` scripts on a database before and after 0079 to 0084 | pass with the new migrations; no script that passed before fails now (12 need the CI bootstrap and fail the same way on both) | Docker, disposable |
| Whole stack | five services, Next.js, GoTrue, PostgREST and Postgres in Docker; a scripted lifecycle with every role, then clicks in the browser | each hotfix behaved as specified, including 20 to 25 (details in the pull request) | local, disposable |

**Not run:** the shared Supabase database, real email delivery, Playwright on the pinned browser build, and the pull-request CI.

**Found and fixed while verifying hotfixes 20 to 25:** a postponed (and a cancelled) event could still take a venue booking, because the booking function checked no event status; the CI platform stub had no `raw_app_meta_data` column, so manual registration could not run on it; forms cleared what the Coordinator had typed after a refusal, so the new ones keep it; the new coordinator forms added text boxes that two existing browser checks did not expect, so the postpone and organiser forms sit behind disclosures. Opening the app at `127.0.0.1` in the Next dev server blocks its client scripts (a dev-server setting, not the code); `localhost` works.

**Found and fixed while verifying hotfixes 1 to 19:** the new venue-change trigger first used the lowest layout capacity and so missed a real capacity drop; the coordinator update returned the row from before the review trigger reopened the event; a client component imported a server-only module (unit tests mock it, only the running app failed); the cancel trigger cast a text coordinator id to a uuid.
