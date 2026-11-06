# SCRUM-39 Test Cases: Restrict Data Access by Relationship

Last reviewed: 5 October 2026

Status: **AC review approved by the story owner (Jaren) on 5 October 2026**, including the `403` response for same-organisation writes. Q1 (Drafts) was settled from the backlog: card E5-1 says "Drafts appear only to their owner", and M1-1 says a request becomes visible once submitted. The Jira ACs were revised the same day to apply customer clarification #81. The other role scopes (attendee, coordinator, venue, technical support) were implemented on this branch before this document existed; see [Disclosures](#disclosures).

## Story

| Field | Value |
| --- | --- |
| Jira key | SCRUM-39 |
| Title | Restrict Data Access by Relationship |
| Sprint | Sprint 2 |
| User story | As a ConnectSphere system user, I want access to be limited to event and organisation data related to my role and relationship, so that unrelated clients' and attendees' information stays protected. |

## Story contract

The live Jira ACs (revised 5 October 2026) are a role checklist. Following `testing.md` §1, each checklist item is rewritten below as a Given / When / Then scenario.

| ID | Criterion | Review outcome | Reason |
| --- | --- | --- | --- |
| AC1 | Given an Event Organiser is responsible for an event request, when they view, edit, submit or delete it, then the action is allowed, subject to the request's current workflow state (SCRUM-8, SCRUM-11). | **Keep** | Existing behaviour; restated so the organisation rules below cannot weaken it. |
| AC2 | Given an Event Organiser belongs to the same client organisation as the request's responsible Organiser, when they list or open the request, then they can view it, and when they try to edit, submit, delete or answer a clarification on it, then the action is refused with `403` and nothing changes. | **Clarify** | #81 says "view but not edit or update". `403` rather than `404` because the viewer already knows the request exists (`security-and-state.md` §2). Drafts: see Q1. |
| AC3 | Given an Event Organiser belongs to an unrelated client organisation, or to none, when they try to list, open or change another Organiser's request, then it is absent from their list and every direct access returns `404`, so its existence is not disclosed. | **Clarify** | "Blocks access and does not expose restricted details" made observable: `404`, identical to a missing request. |
| AC4 | Given an Attendee, when they view events, then they receive only the public projection of **Confirmed** or **Completed** events, and planning fields are never returned. | **Keep** | Implemented in `6859656` / `c1afeff`. |
| AC5 | Given an Event Coordinator, when they open a request, then they can read it only while they are its currently assigned Coordinator; otherwise `404`. | **Keep** | Implemented; "otherwise permitted by internal workflow rules" has no further rule in R1 (Event Operations Manager access is SCRUM-14). |
| AC6 | Given Venue Staff, when they read venue booking requests, then they receive SCRUM-32's booking record (venue, event reference, date range, slots, and the event snapshot taken at submission) needed to approve or reject it, and no other planning fields. | **Keep** | Delivered by SCRUM-32's `GET /booking-requests` endpoints, which this story reuses (see Disclosures). |
| AC7 | Given Technical Support Staff, when they read equipment reservations, then they receive the reservation record (event, equipment, quantity, requirements) and no other planning fields. | **Move (dependency)** | The reservation record is created by SCRUM-13 (Reserve Equipment for an Event, Tan Yang Xue), which owns its table. Agreed with Yang Xue on 6 Oct 2026: SCRUM-39 does not define it, and AC7 is verified when SCRUM-13 lands. |
| AC8 | Given any user without the relationships above, when they request event data, then access is refused without exposing restricted details. | **Merge** | Covered by the negative cases of AC2–AC7; kept as an ID for the cross-cutting matrix rows. |

Expected change to scope: adds a client-organisation model (AC2, AC3). Expected change to testing effort: about 20 new cases, mainly negative ones.

### Included and excluded behaviour

| | Behaviour | Jira |
| --- | --- | --- |
| Included | Client organisations and organisation membership as seeded data | SCRUM-39 |
| Included | Organiser list and detail including same-organisation requests, read-only | SCRUM-39 |
| Included | `organisation_id` recorded on each event request when it is created | SCRUM-39 |
| Excluded | Creating, editing or listing client organisations; linking Organisers to them | E3-4 (SCRUM-52) |
| Excluded | Event Coordinator Lead and Safety Officer access | Week 7 #5, #6 (stories not yet created) |
| Excluded | Registration information access | SCRUM-34 |
| Excluded | Status-history visibility | SCRUM-48 |

### Actors and relationship permissions

| Actor | Relationship | Read | Write |
| --- | --- | --- | --- |
| Event Organiser | Responsible (`organiser_id` = caller) | Yes | Yes, subject to workflow state |
| Event Organiser | Same client organisation | Yes (non-Draft only, Q1) | No: `403` |
| Event Organiser | Unrelated organisation, or no membership | No: `404` | No: `404` |
| Attendee | Any | Public projection of Confirmed or Completed events | No |
| Event Coordinator | Currently assigned | Full request | Transitions per SCRUM-28 and SCRUM-17 |
| Event Coordinator | Not assigned | No: `404` | No |
| Venue Staff | Role-wide | Booking records | Booking decisions (SCRUM-15) |
| Technical Support Staff | Role-wide | Reservation records | Per equipment stories |

### State transitions, persistence and atomicity

- **State transitions:** none added.
- **Persistence:** venue booking requests use SCRUM-32's `0018_venue_booking_requests.sql` and are only read here (AC6). Equipment reservations belong to SCRUM-13 (AC7). New migration `0019_client_organisations.sql`:
  - `client_organisations (id, name unique)`;
  - `organisation_members (user_id primary key, organisation_id)`: one organisation per Organiser;
  - nullable `event_requests.organisation_id`, foreign key to `client_organisations`.
  - RLS on both new tables, service-role access only, like `0010`.
- **Atomicity:** a `BEFORE INSERT OR UPDATE OF organisation_id` trigger (`private.stamp_event_request_organisation`) sets `organisation_id` from the Organiser's membership in the same statement as the insert. It ignores any value the caller supplies and reverts any later change (A2).

### Assumptions and open questions

| ID | Assumption or question | Used by |
| --- | --- | --- |
| A1 | Each Organiser belongs to at most one client organisation. Team Design Proposal, backlog card E3-4. | AC2-P1, AC3-P2 |
| A2 | A request keeps the organisation recorded when it was created, even if its Organiser later changes organisation. | AC2-X1 |
| A3 | Existing requests created before `0019` have `organisation_id = NULL`. They stay visible to their own Organiser only. No backfill. | AC3-P3 |
| A4 | An Organiser with no membership sees only their own requests. | AC3-P2 |
| A5 | A same-organisation viewer may also read the review-decision history (`GET /{id}/decisions`), because it is part of viewing the request. | AC2-P3 |
| Q1 | ~~Should same-organisation Organisers see a colleague's Draft?~~ **Resolved: no.** spm-brain card E5-1 says "Drafts appear only to their owner", and M1-1 says a request becomes visible once submitted. | AC2-B1, AC2-B2 |
| Q2 | Test accounts: a second organiser in the same organisation and a third in a different organisation must exist in the shared Supabase project. The seed script only assigns roles to existing users. | All AC2/AC3 DB and E2E cases |

## Test design

### Specification

Fixtures for the API and unit layers: organisation **Acme** has Organisers `org-a1` (responsible) and `org-a2`; organisation **Globex** has `org-b1`; `org-none` has no membership. Seed and E2E accounts: `event_organiser@example.com` (Acme), `event_organiser2@example.com` (Acme), `event_organiser3@example.com` (Globex), to be created (Q2).

| ID | AC | Test scenario | Technique | Pre-conditions | Test steps | Test data | Expected result | Forbidden side effects | Layer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AC1-H1 | AC1 | The responsible Organiser still reads and edits their own request after organisation scoping is added | Happy | `org-a1` owns Draft R1 in Acme | 1. `GET /event-requests/R1` as `org-a1`. 2. `PATCH` the name. | name `"Launch v2"` | `200` both; name updated | — | API |
| AC1-H2 | AC1 | A new request records its Organiser's organisation, ignoring a supplied value | Happy | User A in `verify-acme` | Insert an `event_requests` row for A with `organisation_id` = `verify-globex` | `verify_client_organisations.sql` | Stored `organisation_id` = `verify-acme` | — | DB |
| AC2-H1 | AC2 | A same-organisation colleague can open a submitted request | Happy | R2 Submitted, owner `org-a1`, Acme | `GET /event-requests/R2` as `org-a2` | — | `200`, full request, `organiser_id` = `org-a1` | — | API |
| AC2-H2 | AC2 | The colleague's list includes the shared request alongside their own | Happy | R2 as above; `org-a2` owns R3 | `GET /event-requests` as `org-a2` | — | Contains R2 and R3, newest first | Globex requests absent | API |
| AC2-P1 | AC2 | One representative per refused write by a same-organisation viewer | Partition | R2 Changes Requested, Acme, with an open clarification | As `org-a2` on R2: `PATCH`, `POST /submit` (complete body), `DELETE`, `POST /clarification-response` | parametrized `ids=["AC2-P1a".."AC2-P1d"]` | `403` `"Insufficient permissions"` each | R2 unchanged (all fields, status); decision rows unchanged | API |
| AC2-P2 | AC2 | One shared request per non-Draft status is visible | Partition | One Acme request per status except Draft | `GET /event-requests` as `org-a2` | 9 statuses | All 9 listed | — | API |
| AC2-P3 | AC2 | The colleague can read the review-decision history (A5) | Partition | R2 has one clarification decision | `GET /event-requests/R2/decisions` as `org-a2` | — | `200`, 1 decision | — | API |
| AC2-P4 | AC2 | The colleague can see whether a Coordinator is assigned (the detail page shows it) | Partition | R2 assigned to a Coordinator | `GET /event-requests/R2/coordinator` as `org-a2` and as `org-b1` | — | `org-a2` `200` with the assignment; `org-b1` `404` | — | API |
| AC2-B1 | AC2, Q1 | A colleague's Draft is not shared | Boundary | R4 Draft, Acme | `GET /event-requests` and `GET /event-requests/R4` as `org-a2` | — | R4 absent from the list; `404` on direct read | — | API |
| AC2-B2 | AC2, Q1 | Once R4 moves Draft → Submitted, it becomes visible | Boundary | R4 submitted by `org-a1` | `GET /event-requests/R4` as `org-a2` | — | `200` | — | API |
| AC2-X1 | AC2, A2 | The recorded organisation, not current membership, decides sharing | Cross-cutting | R2 created while `org-a1` in Acme; then `org-a1` moved to Globex | `GET R2` as `org-a2` and as `org-b1`; in the DB, try `UPDATE … SET organisation_id` | — | `org-a2` `200`; `org-b1` `404`; the DB update is reverted | Row's `organisation_id` unchanged | API, DB |
| AC2-X2 | AC2 | The UI shows a colleague's request read-only | Cross-cutting | R2 Changes Requested with a clarification, seeded through the stub `/__seed`, owner `playwright-user` | Colleague session (`colleague-session`): open the All tab, then the request | — | Request and clarification reason visible; the "Shared by another organiser…" notice is shown; no textbox and no send, save, submit or delete button | — | E2E |
| AC3-H1 | AC3 | An unrelated-organisation Organiser cannot read the request | Happy (refusal) | R2 Acme | `GET /event-requests/R2` as `org-b1` | — | `404` `"Event request not found"`, same body as a random UUID | — | API |
| AC3-P1 | AC3 | One representative per refused write by an unrelated Organiser | Partition | R2, R4 Acme | As `org-b1`: `PATCH`, `submit`, `DELETE`, `clarification-response`, `GET decisions` | parametrized `ids=["AC3-P1a".."AC3-P1e"]` | `404` each | Rows unchanged | API |
| AC3-P2 | AC3, A4 | An Organiser with no membership sees only their own requests | Partition | `org-none` owns R5 | `GET /event-requests` as `org-none`; `GET R2` | — | List = [R5]; R2 `404` | — | API |
| AC3-P3 | AC3, A3 | A legacy request with no organisation is shared with nobody | Partition | R6 `organisation_id = NULL`, owner `org-a1` | `GET R6` as `org-a2` and as `org-a1` | — | `org-a2` `404`; `org-a1` `200` | — | API |
| AC3-N1 | AC3 | Organisation membership cannot be read or written by browser roles | Negative | `0019` applied | As `anon` and `authenticated`: select and insert on `organisation_members`, `client_organisations` | — | Permission denied | No row written | DB |
| AC3-N2 | AC3 | An unknown organisation id is refused | Negative | — | Insert `organisation_members` with a random `organisation_id` (service role) | random UUID | Foreign-key violation | No row | DB |
| AC3-N3 | AC3 | Membership is unique per user (A1) | Negative | `org-a1` in Acme | Insert `org-a1` into Globex | — | Primary-key violation | Acme membership unchanged | DB |
| AC4-H1 | AC4 | Attendees see only Confirmed or Completed events, with public fields only | Happy | Requests in every status | `GET /event-requests/public-events` as an Attendee | — | Only Confirmed and Completed listed; planning fields absent | — | API |
| AC4-N1 | AC4 | Other roles are refused the public projection | Negative | Organiser or Coordinator caller | `GET /event-requests/public-events` | — | `403` | — | API |
| AC5-H1 | AC5 | Details are visible only to the owner or the assigned Coordinator | Happy | Request with an assigned Coordinator | `GET /event-requests/{id}` per caller (parametrized) | — | Owner and assigned Coordinator `200`; related but unauthorised `404`; unrelated roles `403` | — | API |
| AC5-N1 | AC5 | An unassigned Coordinator cannot confirm a request exists | Negative | Request assigned to another Coordinator | `GET /event-requests/{id}` | — | `404` | — | API |
| AC6-H1 | AC6 | Venue Staff read the pending booking queue with the event snapshot | Happy | SCRUM-32 booking requests | `GET /booking-requests` as Venue Staff | — | `200`, SCRUM-32 records | — | API (reused: SCRUM-32 `AC3-H2`, `AC3-P1`) |
| AC6-N1 | AC6 | Other roles cannot read the booking queue | Negative | Coordinator or Organiser caller | `GET /booking-requests` | — | `403` | — | API (reused: SCRUM-32 `AC3-N2`, `AC3-N3`) |
| AC6-N2 | AC6 | Reads need a signed-in user | Negative | No token | Every booking read | — | `401` | — | API (reused: SCRUM-32 `AC3-X2`) |
| AC6-X1 | AC6 | A Coordinator cannot see another Coordinator's booking request | Cross-cutting | Booking by another Coordinator | `GET /booking-requests/{id}` | — | `404`, same as an unknown id | — | API (reused: SCRUM-32 `AC5-N14`) |
| AC7-H1 | AC7 | Technical Support Staff read equipment reservations | Happy | SCRUM-13 reservation records | — | — | Deferred to SCRUM-13 | — | — |
| AC8-X1 | AC2–AC3 | An Organiser who is also an assigned Coordinator keeps coordinator access to an unrelated organisation's request | Cross-cutting | `org-b1` also holds `event_coordinator` and is assigned R2 | `GET R2` as `org-b1` | — | `200` through the coordinator relationship | — | API |

AC4–AC7 rows point at tests written before this document. Labelling those tests with these IDs is part of this story (see [Disclosures](#disclosures)).

### Latest execution record

Working tree on top of `e3a3ca4` (uncommitted), Windows 11, 5 October 2026, executed by Claude for Jaren. API tests use in-memory fakes and E2E uses the Node stub APIs; **no real Supabase was used**.

| ID | Automation status | Actual result | Execution status | Build or commit | Executed by and date | Remarks and evidence |
| --- | --- | --- | --- | --- | --- | --- |
| AC1-H1, AC2-H1, AC2-H2, AC2-P1a–d, AC2-P2 (9), AC2-P3, AC2-B1, AC2-B2, AC2-X1 (API), AC3-H1, AC3-P1a–e, AC3-P2, AC3-P3, AC8-X1 | Green | As expected | Pass | `e3a3ca4` + working tree, mocked repository | Claude, 5 Oct 2026 | `backend/eventRequestService/tests/test_organisation_access.py`. Red first: 18 failed for the intended reason (404 instead of 200 or 403, shared rows absent); AC3-P1b first failed with 422 (empty submit body) and was fixed to send a complete body before implementing |
| AC2-P4 | Green | As expected | Pass | as above | Claude, 5 Oct 2026 | Red first: `404 == 200`; fixed in `coordinator_assignment_controller.get_coordinator` |
| Repository queries (AC2-H1, AC2-H2, AC3-P2) | Green | As expected | Pass | as above, `httpx.MockTransport` | Claude, 5 Oct 2026 | `tests/test_supabase_repository.py`; written **after** the implementation, so no Red was seen |
| AC2-X2 | Green | As expected | Pass | as above, Chromium, stub APIs | Claude, 5 Oct 2026 | `frontend/e2e/organisation-access.spec.ts`. Red first: the shared notice was missing |
| AC1-H2, AC2-X1 (DB), AC3-P2 (DB), AC3-N2, AC3-N3 | Green | Block ended with `VERIFY PASSED: AC1-H2, AC2-X1, AC3-P2, AC3-N2, AC3-N3`; follow-up query found 0 leftover rows | Pass | `0019` + `0020` applied to shared Supabase `eizzwhejdudmmslowvql` on 5 Oct 2026 | Claude, 5 Oct 2026 | The checks from `verify_client_organisations.sql`, run in the Supabase SQL Editor inside one block that ends with an exception so every change rolls back |
| AC3-N1 | Green | `anon`/`authenticated` have no SELECT/INSERT on `client_organisations` or `organisation_members`, and no EXECUTE on the trigger function | Pass | as above | Claude, 5 Oct 2026 | `has_table_privilege` / `has_function_privilege` query through Supabase MCP |
| AC6-H1, AC6-N1, AC6-N2, AC6-X1 | Green (SCRUM-32 tests) | As expected | Pass | rebased onto `dev` `6673a21` | Claude, 5 Oct 2026 | `venueService/tests/test_booking_requests_read.py`, referenced in this pass to its already-labelled reused tests (no new labels stacked): AC6-H1 → the `AC3-H2` label (a submitted request appears in the pending queue with status pending), AC6-N1 → the `AC3-N2, AC3-N3` label (coordinators and organisers cannot read the queue), AC6-N2 → the `AC3-X2, AC5-X2` label (an unauthenticated caller is refused on every read), AC6-X1 → the `AC5-N14` label (another Coordinator's request returns the same 404 as an unknown id). This branch's duplicate `GET /venue-booking-requests` was removed (see Disclosures) |
| AC4-N2, AC4-N3 | Green (pre-existing, now labelled) | As expected | Pass | `equipmentService` 150 passed | Claude, 6 Oct 2026 | `equipmentService/tests/test_equipment.py`, `test_status.py` (Attendees refused equipment and status reads) |
| AC7-H1 | Not automated here | — | Not executed | — | — | Deferred to SCRUM-13; `GET /equipment/reservations`, its tests and table were removed on 6 Oct 2026 |
| AC4-H1, AC4-N1, AC5-H1, AC5-N1 | Green (pre-existing, now labelled) | As expected | Pass | as above | Claude, 5 Oct 2026 | `eventRequestService/tests/test_event_request_controller.py` |

Suite-level results after rebasing onto `dev` (`6673a21`, which includes SCRUM-10 and SCRUM-32), 6 Oct 2026:

- Backend `pytest`: eventRequestService **272 passed**, venueService **147 passed**, equipmentService **150 passed**, authService **45 passed**, notificationService **53 passed**; 0 failed, 0 skipped; `ruff check .` clean in all five.
- `frontend`: `npm run lint` clean; `npm run typecheck` clean; `npm test` **21 files, 180 tests passed**; `npm run test:e2e` **24 passed** (Chromium, stub APIs); `npm run build` compiled successfully.
- Shared Supabase: Security Advisor reports only INFO `rls_enabled_no_policy` for the new tables (intended: service-role only, the same as every other table) and INFO `unused_index` (tables are new). No new WARN.
- Seed: `seed_test_accounts.sql` run on the shared project on 5 Oct 2026. `event_organiser@example.com` and `event_organiser2@example.com` are in Acme Events and `event_organiser3@example.com` is in Globex Corporation, each with the `event_organiser` role (checked with a read query through Supabase MCP).
- Pull-request CI: see the pull request.

## Disclosures

- The role scopes for Attendees, Coordinators, Venue Staff and Technical Support (`6859656`, `c1afeff`, `e3a3ca4`) were implemented before this story contract existed, so the standard's order (approve the ACs, write the cases, watch them fail) was not followed for AC4–AC7.
- Claude (AI) drafted this AC review, the test design, the tests and the implementation. A team member still has to review the test design (`testing.md` §10).
- The three repository query tests were written after the implementation.
- `e3a3ca4` also created an `equipment_reservations` table and `GET /equipment/reservations`. The table belongs to SCRUM-13, so on 6 Oct 2026, with Yang Xue's agreement, the migration, endpoint and tests were removed and the empty table was dropped from the shared project. Yang Xue's SCRUM-10 work has since added its own `equipment_reservations` table (`dev` `6673a21`). AC7 is verified once a Technical Support read of reservations exists (SCRUM-13).
- After `dev` was brought in, SCRUM-32's `GET /booking-requests` endpoints were already there and cover AC6, including restricting Coordinators to their own bookings. This branch's duplicate `GET /venue-booking-requests`, its `VenueBookingRequest` model and its tests were removed, and AC6 now reuses SCRUM-32's tests.
- `e3a3ca4` originally created its own `venue_booking_requests` table in a second `0018` migration. That clashed with SCRUM-32's table, which is already live in the shared project, and venueService would have failed to read real rows. On 5 Oct 2026 the table was dropped from this branch, and `VenueBookingRequest` aligned to SCRUM-32's columns; both were later removed in favour of SCRUM-32's own code. The `0020_equipment_reservations.sql` now in the repository is Yang Xue's SCRUM-10 migration, not this branch's.
