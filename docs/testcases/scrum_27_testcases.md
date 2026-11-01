# SCRUM-27 — Authorise Access by Role

**Jira:** [SCRUM-27](https://is212g9t4.atlassian.net/browse/SCRUM-27)

**User story:** As a ConnectSphere system user, I want to see and do only the features my role permits, so that I act only within my responsibilities.

**How this document was made.** The story was built in Sprint 1 (done on 24 September 2026) and this record was written afterwards, on 1 November 2026. The acceptance criteria are the Jira text as it stands today (three bullets, numbered AC1 to AC3 here). The review below is a proposal that the story owner or Product Owner has not approved yet. Role checks were written inside every later story, so this story has no code of its own: the document gathers the cases that prove it across authService, eventRequestService, venueService, equipmentService and the frontend. Those tests keep the case IDs of the story that wrote them and are cited by file and name; a few are labelled for this story as well. The tests marked "new" were written for this document; they passed first time, so they found no defect.

## Story contract review

The acceptance criteria were checked against Week 4 core feature 1 (*User Authorisation and Authentication*), Week 7 Customer Changes #5 and #6, GitHub Discussions #129 (the Event Operations Manager is the Event Coordinator Lead, renamed), #132 (the Lead cannot cancel) and #136 (the Lead cannot change an event's essential arrangements and can only view active events), and against the role code in each service.

| Original criterion | Outcome | Reason |
| --- | --- | --- |
| AC1. Given an authenticated user, when they use the system, then the features available to them are determined by their role (Event Organiser, Event Coordinator, Event Operations Manager, Venue Staff, Technical Support Staff, Attendee). | Clarify | The role list is out of date: the Safety Officer (Week 7 #6) exists, and an Admin may assign roles. "Event Operations Manager" is shown as "Event Coordinator Lead" (#129) but its role id stays `event_operations_manager`. "Features" means three things: the links a person is offered, the pages they may open, and the API calls the services accept. Access to a particular event (an Organiser sees only their own client's events) is SCRUM-39, not this story. |
| AC2. An Event Operations Manager can assign or reassign Event Coordinators but cannot perform unrelated role-specific actions unless they also hold the corresponding role. | Clarify | Name the actions: the Lead assigns and reassigns, reads the awaiting-assignment queue and lists coordinators; the Lead cannot cancel or complete an event (#132), start planning, change arrangements (#136), record equipment, manage venues, search venues, or create event requests. |
| AC3. Given a person with multiple roles, when authorised functionality is evaluated, then the system recognises all assigned roles. | Keep | Testable as written. |

Approval of this review: **not recorded.** Replace this line with the approver and date once the story owner or Jaren (Product Owner) has approved it.

## Increment scope

- **Included:** reading a person's roles (`GET /auth/me`, from the staff roles table first, then the sign-up metadata, else Attendee); assigning roles (`PATCH /auth/users/{id}/role`, admin, and Lead for Event Coordinator only); the role guard on each service's routes; the frontend's role-based links, page guards and landing workspace.
- **Excluded:** which events a role may see (SCRUM-39); sign-in and sign-up themselves (SCRUM-26); the content of each role's own actions (their stories). Their tests are cited only where they prove a refusal.
- **Actors:** the seven roles Event Organiser, Event Coordinator, Event Coordinator Lead, Venue Staff, Technical Support, Safety Officer and Attendee, plus Admin for assigning roles.
- **State and persistence:** roles are rows in `staff_roles` (and the account's metadata). A refused call changes nothing.
- **Team proposals:** a person who holds no role is an Attendee; the first role returned is their main role (it decides the landing workspace through a fixed order).

## Acceptance criteria

- **AC1:** Given a signed-in user, when they use the system, then they are offered, may open and may call only what their role permits: other roles' links are absent, other roles' pages redirect to the unauthorised page, and other roles' API calls get 403 (401 with no session); a person with no role is an Attendee.
- **AC2:** Given an Event Coordinator Lead, when they work, then they can assign and reassign Event Coordinators, but a call that belongs to another role (cancelling, completing, planning, recording equipment, managing or searching venues, creating event requests, listing other roles) is refused unless they hold that role as well.
- **AC3:** Given a person with several roles, when their access is evaluated, then every role they hold counts: they are offered the links of all of them, each of their roles' calls is accepted, and the order the roles are listed in changes nothing except the landing workspace.

## Test-case specification

Cases cited from other stories keep their own IDs in the code (shown in the evidence column of the execution record).

| ID | AC | Test scenario | Technique | Pre-conditions | Test steps | Test data | Expected result | Forbidden side effects | Layer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AC1-H1 | AC1, AC3 | Roles come from the staff roles table | Happy | Account with sign-up role `event_coordinator`; two rows in `staff_roles` | `GET /auth/me` | rows event_operations_manager, technical_support | Both roles returned; the table wins over the metadata | — | API |
| AC1-H2 | AC1 | An admin assigns a role | Happy | Admin session | `PATCH /auth/users/user-id/role` | technical_support | 200; role stored | — | API |
| AC1-P1 | AC1 | Event Organiser is offered only its own workspace | Partition | Role `event_organiser` | Build the links | — | My event requests, Notifications | — | UI unit (new) |
| AC1-P2 | AC1 | Event Coordinator | Partition | Role `event_coordinator` | Build the links | — | Coordination, Venue search, Notifications | — | UI unit (new) |
| AC1-P3 | AC1 | Event Coordinator Lead | Partition | Role `event_operations_manager` | Build the links | — | Assignments, Notifications | — | UI unit (new) |
| AC1-P4 | AC1 | Venue Staff | Partition | Role `venue_staff` | Build the links | — | Venues, Booking requests, Venue blocks, Venue search, Arrangement reviews, Notifications | — | UI unit (new) |
| AC1-P5 | AC1 | Technical Support | Partition | Role `technical_support` | Build the links | — | Equipment, Equipment requests, Arrangement reviews, Notifications | — | UI unit (new) |
| AC1-P6 | AC1 | Safety Officer | Partition | Role `safety_officer` | Build the links | — | Safety checks, Notifications | — | UI unit (new) |
| AC1-P7 | AC1 | Attendee | Partition | Role `attendee` | Build the links | — | Events, Notifications | — | UI unit (new) |
| AC1-P8 | AC1 | A person with no role is an Attendee | Partition | Account with no role metadata (`{}` and `None`) | `GET /auth/me` | — | role `attendee`, roles `["attendee"]` | — | API |
| AC1-N1 | AC1 | An unknown role is offered nothing | Negative | Roles `admin`, `ghost` | Build the links | — | No links | — | UI unit (new) |
| AC1-N2 | AC1 | No roles at all is offered nothing | Negative | Roles `[]` | Build the links | — | No links | — | UI unit (new) |
| AC1-N3 | AC1 | An attendee, an admin and the Lead cannot create or change event requests | Negative | Each role | `POST /event-requests/submissions` | complete request | 403 | No request stored | API |
| AC1-N4 | AC1 | Only the Lead can assign a coordinator | Negative | A caller who is not the Lead | `POST /event-requests/{id}/coordinator` | — | 403 | No assignment | API |
| AC1-N5 | AC1 | Only the Lead can read the awaiting-assignment queue | Negative | A caller who is not the Lead | `GET /event-requests/awaiting-assignment` | — | 403 | — | API |
| AC1-N6 | AC1, AC2 | Only an admin can assign roles; the Lead may assign Event Coordinator only | Negative | Callers technical_support, Lead and attendee | `PATCH` another user's role | technical_support | 403 | No role written, no account updated | API |
| AC1-N7 | AC1 | Assigning a role needs a session | Negative | No token | `PATCH` role | — | 401 | — | API |
| AC1-N8 | AC1 | An unknown role cannot be assigned | Negative | Admin session | `PATCH` role | invalid role | 422 | No role written | API |
| AC1-N9 | AC1 | The two public pages are the only ones without a check | Negative | The `app` folder | List pages with no `require…` call | — | Exactly sign-in and the refusal page | — | UI unit (new) |
| AC1-X1 | AC1 | Venue routes admit only the permitted roles | Cross-cutting | Each role | Search, read, create, update venues | — | Permitted roles 200; every other role 403; no session 401 | Venue unchanged on refusal | API (SCRUM-9 AC6, SCRUM-30 AC1-X, AC2-N) |
| AC1-X2 | AC1 | Only the assigned Coordinator records equipment | Cross-cutting | Roles Technical Support, Organiser, Venue Staff, Lead, Attendee | `POST /equipment-requirements` | — | 403 for each | No requirement stored; eventRequestService not asked | API (SCRUM-33 AC6-X12 to X16) |
| AC1-X3 | AC1 | The browser turns away the wrong role | Cross-cutting | Organiser, then coordinator session | Open `/venues/search`; open `/venues/new`; open event-request pages as a non-organiser | — | Redirected to the unauthorised page | — | E2E |
| AC1-X4 | AC1 | A signed-in user without the Organiser role is turned away | Cross-cutting | Signed in, no `event_organiser` | Open the event-request workspace | — | Redirect to the unauthorised page | — | UI unit |
| AC1-X5 | AC1 | A coordinator lands in the coordination workspace | Cross-cutting | Coordinator account | Log in | — | `/coordination/requests` | — | UI unit |
| AC1-X6 | AC1 | Every page except the two public ones checks the session or role | Cross-cutting | The `app` folder | Read each `page.tsx` for a `require…` call | — | None without one | — | UI unit (new) |
| AC2-H1 | AC2 | The Lead gives someone the Event Coordinator role | Happy | Lead session | `PATCH /auth/users/{id}/role` | event_coordinator | 200 | — | API |
| AC2-H2 | AC2 | The Lead lists coordinators to choose from | Happy | Lead session | `GET /auth/users?role=event_coordinator` | — | The coordinators | — | API |
| AC2-H3 | AC2 | The Lead assigns a coordinator to a submitted request | Happy | Submitted request | `POST /event-requests/{id}/coordinator` | — | 201; the coordinator is current | Status unchanged | API |
| AC2-H4 | AC2 | The Lead reassigns, and the history is kept | Happy | Assigned request | Assign a second coordinator | — | The latest is current; both rows kept | — | API |
| AC2-H5 | AC2 | The Lead assigns and reassigns in the browser | Happy | Lead session; mock API | Assign, then reassign | — | New coordinator shown | — | E2E |
| AC2-H6 | AC2 | The Lead role is recognised among a person's other roles | Happy | A caller with the Lead role and another | Assign | — | Allowed | — | API |
| AC2-N1 | AC2 | The Lead cannot list the holders of another role | Negative | Lead session | `GET /auth/users?role=venue_staff` | — | 403 | — | API |
| AC2-N2 | AC2 | The Lead cannot list Technical Support staff | Negative | Lead session | List Technical Support users | — | 403 | — | API |
| AC2-N3 | AC2 | The Lead and an Organiser cannot cancel or complete an event | Negative | Event assigned to the caller's id | `POST .../cancellation` and `.../completion` | roles event_organiser, event_operations_manager | 403 on each | Status unchanged | API |
| AC2-N4 | AC2 | The Lead cannot start planning | Negative | Approved event | `POST .../planning` | role event_operations_manager | 403 | Status unchanged | API (SCRUM-58 AC4-N6) |
| AC2-N5 | AC2 | The Lead cannot record equipment | Negative | Lead session | `POST /equipment-requirements` | — | 403 | Nothing stored | API (SCRUM-33 AC6-X15) |
| AC2-N6 | AC2 | The Lead cannot create, read or search venues | Negative | Lead session | Create, read and search a venue | — | 403 on each | Nothing stored | API (SCRUM-30 AC1-X6, AC2-N3; SCRUM-9 AC6-N4) |
| AC2-N7 | AC2 | The Lead cannot assign Technical Support or any role but Event Coordinator | Negative | Lead session | `PATCH` role | technical_support | 403 | No role written | API |
| AC2-N8 | AC2 | The Lead cannot read an event's decision history | Negative | Event under review | `GET /event-requests/{id}/decisions` | role event_operations_manager | 403 | — | API |
| AC2-X1 | AC2 | The Lead's own workspace has no other role's links | Cross-cutting | Lead roles | Build the links | — | None of coordination, venues, bookings, equipment, safety, event requests | — | UI unit (new) |
| AC3-H1 | AC3 | A Lead who is also an Organiser is offered both workspaces | Happy | Roles Lead and Organiser | Build the links | — | My event requests, Assignments, Notifications | — | UI unit (new) |
| AC3-H2 | AC3 | A Lead who is also an Organiser acts as the Organiser | Happy | Roles Lead and Organiser; a spoofed header | `POST /event-requests` | `X-Organiser-Id: attacker` | 201; the organiser is the verified id | The header ignored | API |
| AC3-H3 | AC3 | Every role a person holds is returned, the first as the main role | Happy | Metadata roles Lead and Technical Support | `GET /auth/me` | — | `role` is the first; `roles` lists both | — | API |
| AC3-H4 | AC3 | Roles from the staff roles table are all returned | Happy | Two rows | `GET /auth/me` | — | Both | — | API (same case as AC1-H1) |
| AC3-H5 | AC3 | A person with Lead and Technical Support roles can use Technical Support's calls | Happy | Roles Lead and Technical Support | Update an equipment arrangement | — | 200 | — | API (SCRUM-33 AC5-P8) |
| AC3-H6 | AC3 | One permitted role is enough to search venues | Happy | Roles attendee and event_coordinator | `GET /venues/search` | — | 200 | — | API (SCRUM-9 AC6-P1) |
| AC3-P1 | AC3 | The order roles are listed in does not change the links | Partition | Three roles, forward and reversed | Build the links | coordinator, venue staff, safety officer | Same links | — | UI unit (new) |
| AC3-P2 | AC3 | Several roles land in a fixed workspace | Partition | Role pairs | Choose the landing workspace | organiser+coordinator, Lead+venue staff, attendee+tech support, attendee+safety, unknown | `/event-requests`, `/operations/assignments`, `/equipment`, `/safety`, `/unauthorised` | — | UI unit (new) |
| AC3-P3 | AC3 | The default workspace for verified roles is deterministic | Partition | Verified roles | Select the workspace | — | The same workspace each time | — | UI unit |

## Latest execution record

Build: `b5b53b0` (`dev` after PR #123) plus this branch's working tree (`docs/testcases-scrum-9-27-30`), run on Kennedy's machine on 1 November 2026 with Claude Code, pending human review. Backend tests ran against fakes of Supabase and of the other services; the browser tests ran against the Node mock services. "Red first" was not observed for any case.

| ID | Automation status | Actual result | Execution status | Build or commit | Executed by and date | Remarks and evidence |
| --- | --- | --- | --- | --- | --- | --- |
| AC1-H1, AC1-H2, AC1-P8, AC1-N6, AC1-N7, AC1-N8, AC2-H1, AC2-H2, AC2-N1, AC2-N7, AC3-H3, AC3-H4 | Green | Roles read from the table, all returned, default Attendee; admin assigns; Lead limited to Event Coordinator and its list; unknown role and no session refused | Pass | b5b53b0 + working tree, local | Claude Code, 1 Nov 2026 | `backend/authService/tests/test_registration.py`; authService suite 60 passed |
| AC2-N2 | Green | The Lead cannot list Technical Support staff | Pass | same | same | `backend/authService/tests/test_list_technical_support_users.py` |
| AC1-N3, AC1-N4, AC1-N5, AC2-H3, AC2-H4, AC2-H6, AC2-N3, AC2-N4, AC2-N8, AC3-H2 | Green | Organiser operations refused to attendee, admin and Lead; only the Lead assigns and reads the queue; the Lead cannot cancel, complete or start planning; a Lead who is an Organiser acts as one | Pass | same | same | `test_event_request_controller.py`, `test_coordinator_assignment_controller.py`, `test_event_transition_controller.py`, `test_event_planning.py` (SCRUM-58 AC4-N5, N6), `test_event_review_decision.py`; eventRequestService suite 1194 passed, 1 skipped |
| AC1-X2, AC2-N5, AC3-H5 | Green | Only the assigned Coordinator records equipment; the Lead is refused; a Lead with Technical Support can update | Pass | same | same | `backend/equipmentService/tests/test_requirements_record.py` (SCRUM-33 AC6-X12 to X16) and `test_requirements_arrangement.py` (AC5-P8); equipmentService suite 354 passed |
| AC1-X1, AC2-N6, AC3-H6 | Green | Venue routes admit the permitted roles only; the Lead is refused; one permitted role is enough | Pass | same | same | `backend/venueService/tests/test_venues_search_contract.py` and `test_venues_catalogue_contract.py` (new) and `test_venues_catalogue.py`; venueService suite 790 passed, 10 skipped |
| AC1-P1 to AC1-P7, AC1-N1, AC1-N2, AC1-N9, AC1-X6, AC2-X1, AC3-H1, AC3-P1, AC3-P2 | Green | Each role's links; unknown and no roles offered nothing; the only unguarded pages are sign-in and the refusal page; the Lead's workspace is its own; two roles give two workspaces in a fixed order | Pass | same | same | New: `frontend/__tests__/role-access.test.ts` (20 passed). AC1-X6 and AC1-N9 were also run against a page with its guard removed: both failed as they should, then the page was restored |
| AC1-X4, AC1-X5, AC3-P3 | Green | Non-organiser turned away; coordinator lands in coordination; default workspace deterministic | Pass | same | same | `frontend/__tests__/auth.test.tsx` (10 passed) |
| AC1-X3, AC2-H5 | Green | Wrong-role page access redirects; the Lead assigns and reassigns | Pass | same | same | `frontend/e2e/auth.spec.ts`, `venue-search.spec.ts`, `venue-catalogue.spec.ts`, `assign-coordinator.spec.ts` against the Node mock services (14 passed across the five specs run) |

### Local validation evidence

| Check | Command and environment | Result | Remarks |
| --- | --- | --- | --- |
| authService | `pytest`; `ruff check .` | 60 passed; clean | Supabase and the admin client are mocks |
| eventRequestService | `pytest`; `ruff check .` | 1194 passed, 1 skipped; clean | Fake repositories; the identity service is a stub |
| equipmentService | `pytest`; `ruff check .` | 354 passed; clean | Fake Data API and fake event service |
| venueService | `pytest`; `ruff check .` | 790 passed, 10 skipped; clean | In-memory store |
| Frontend unit | `npx vitest run` (whole frontend suite) | 80 files, 762 passed | jsdom |
| Frontend static checks | `npm run typecheck`; `npm run lint` | Clean | — |
| End-to-end | `playwright test venue-search venue-catalogue assign-coordinator auth.spec equipment-catalogue` with the cached Chromium 1148 headless shell | 14 passed | The pinned browser build is not installed and was not downloaded |

Not run: a real sign-in against Supabase and the real role table in this pass (the earlier whole-stack run in the hotfix record used them for the hotfix flows), pull-request CI, reviewer approval.

## Open questions

1. **Role list.** The story names six roles; the system has Safety Officer and an Admin who assigns roles. Reword AC1 or accept the list in this document.
2. **Lead may view active events (#136).** The customer said the Lead can view the current status of active events but change nothing. The Lead's page lists assignments and active events grouped by coordinator (SCRUM-62); whether the Lead can open an individual event's detail is covered there, not here, and the Lead is refused an event's decision history (AC2-N8). Confirm that is intended.
3. **Pages are guarded one by one.** Each page calls its own check; there is no central route table. AC1-X6 catches a page that has no check but not one that has the wrong one, so a role mistake in a single page would pass. A route-to-roles table with one test per row would close this; it is a design change and not part of this story.
4. **Safety Officer on the venue search page.** The service admits the Safety Officer; the page does not (SCRUM-9, *Open questions*).
