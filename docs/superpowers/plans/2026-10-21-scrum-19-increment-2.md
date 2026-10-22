# SCRUM-19 Increment 2 Plan: Frontend, E2E and Shared-Dev Rollout

Drafted 21 October 2026 by Claude (Cowork) for Yang Xue. **Status: in execution — 21 October 2026, Yang Xue approved running the plan; §7's decisions are taken as recommended (G1 widen authService, G3 additive mock routes, G2/G4 skill-named notification with no link, and the new catalogue rows).**
Builds on `2026-10-19-scrum-19-assign-technical-support.md` (increment 1) and `docs/testcases/scrum_19_testcases.md` (approved contract). Branch: `feat/scrum-19-assign-technical-support` at `4e6e733` (dev merged in).

**Hard rule:** no existing test file is edited to make anything pass. That covers `backend/eventRequestService/tests/*`, `database/verify_technical_support_*`, and every existing `frontend/__tests__` and `frontend/e2e/*.spec.ts`. Increment 2 only **adds** new test files (Red first). Additive changes to shared e2e mock servers are called out in G3 for approval.

---

## 0. Where the story stands (checked 21 Oct)

| Item | State |
| --- | --- |
| Increment 1 (commits 1–9: DB, rules, API, repository, notification client) | Done on branch. Re-run 21 Oct in `backend/eventRequestService`: `pytest -q` **694 passed, 1 skipped**; `ruff check .` clean (Linux, Python 3.14, uv env outside the repo; no live Supabase) |
| Jira SCRUM-19 | Still **To Do**, 3 points, Sprint 3 ends **22 Oct**. Move to In Progress |
| Frontend (F layer: AC1-X3, AC2-X6, AC3-P6, AC4-X1) | Not started; no test files exist |
| E2E (AC5-H3) | Not started |
| Shared dev | `0052` + `seed_technical_support_skills.sql` not applied; `technical_support2@example.com` not created |
| SCRUM-64 | Done — it did not pick up support assignments. No action for this story |

## 1. Gaps found that the increment-1 plan did not cover

| # | Gap | Evidence | Recommendation |
| --- | --- | --- | --- |
| G1 | **Coordinators cannot list Technical Support Staff emails.** D11 says the panel gets labels from `GET /auth/users?role=technical_support`, but authService only lets `admin` list any role and `event_operations_manager` list `event_coordinator`. An `event_coordinator` gets 403, so AC4-X1 ("panel shows technical_support@example.com") fails | `backend/authService/app/main.py` `list_users_by_role` (`can_list_any` / `can_list_coordinators`) | Widen authService: `event_coordinator` may list `role=technical_support` only. New authService tests (new test cases, not edits). Needs approval as a permission change (`security-and-state.md`). Fallback if refused: show staff ids (AC4-X1 allows the id fallback, but the UI is then unusable with UUIDs) |
| G2 | **The inbox has no message for `technical_support_assigned`.** `describeNotification` falls to the default "There's an update on an event request." with no link, so AC5-H3 ("a notification naming the event and requirement") fails | `frontend/lib/notifications.ts` `default:` branch | Add a case: "You've been assigned as {Skill label} support for {event_name}." `href: null` (TSS cannot open `/coordination/requests/*`, and a TSS page is out of scope). Add a new catalogue row **AC5-H4 (F)** for it |
| G3 | **E2E runs against node mock servers, not a live stack.** `playwright.config.ts` starts `e2e/support/*.mjs`; CI has no Supabase. AC5-H3 as written (real accounts, password `12345678`) cannot run in CI | `playwright.config.ts`, `frontend-ci.yml` | Split AC5-H3: (a) Playwright against mocks — add technical-support routes to `e2e/support/event-request-api.mjs`, a `role=technical_support` branch to `auth-api.mjs`, and seed the notification via the existing notification mock `__seed`; (b) one manual live run on shared dev recorded as evidence. (a) adds routes to shared mock files — additive only, no existing route or spec changes. Needs your OK under the "don't modify tests" rule |
| G4 | **The requirement description is not in the notification payload** (`{event_request_id, event_name, requirement_id, skill_tag, assigned_by}`) | D9, `notification_client.py` | Name the requirement by its skill label (G2). Do **not** change the backend payload — it is locked by AC5-H1 tests |

## 2. Commit sequence (continues the increment-1 numbering)

| # | Commit | Files | Done when |
| --- | --- | --- | --- |
| 10a | `docs(scrum-19): record increment 2 gaps and new test rows` | this plan; `scrum_19_testcases.md` add AC5-H4 (F), AC5-H3 split into H3a (E, mock) / H3b (live manual), G1 note on AC4-X1 | Approved by you |
| 10b | `test(auth): coordinators may list technical support staff (SCRUM-19)` *(only if G1 approved)* | new `backend/authService/tests/test_list_technical_support_users.py`: coordinator + `technical_support` → 200; coordinator + any other role (e.g. `event_organiser`, `admin`) → 403; TSS/organiser → 403; ops manager still only coordinators | Red, failing on 403 |
| 10c | `feat(auth): let coordinators list technical support staff (SCRUM-19)` | `backend/authService/app/main.py`: `can_list_tss = "event_coordinator" in caller_roles and role == "technical_support"` | authService `pytest` + `ruff` green; existing auth tests untouched |
| 11 | `test(frontend): add Red tests for the technical support panel (SCRUM-19)` | new `__tests__/technical-support-panel.test.tsx`, `__tests__/technical-support-actions.test.ts`, extra cases in a **new** `__tests__/technical-support-notifications.test.ts` (not in `notifications.test.tsx`) | `npm test` Red only for missing modules/behaviour |
| 12 | `feat(frontend): technical support panel on the coordination request page (SCRUM-19)` | see §3 | `npm run lint`, `typecheck`, `test`, `build` clean |
| 13 | `test(e2e): assign technical support journey (SCRUM-19)` | new `e2e/assign-technical-support.spec.ts`; additive routes in `e2e/support/event-request-api.mjs` + `auth-api.mjs` (G3) | `npm run test:e2e` green locally, all existing specs still green |
| 14 | `docs(scrum-19): record increment 2 and shared-dev evidence` | execution record in `scrum_19_testcases.md`, service README if auth changed | §5 done |

Run Red before Green for 10b and 11; put the Red counts in the commit body; never push a red commit.

## 3. Frontend design

| File | Change |
| --- | --- |
| `frontend/lib/technical-support.ts` | **New.** Types mirroring `RequirementResponse`, `EventTechnicalSupportResponse`, `CandidateResponse`. `SKILL_TAGS` (4, fixed order) + `SKILL_TAG_LABELS` = Audio-visual, Lighting, IT and network, Livestream. `SUPPORT_STATUSES = ["Approved","Planning","Confirmed"]`. `listEventTechnicalSupport(id)`, `listCandidates(id, rid)` via `getJson` (`EVENT_REQUEST_API_URL`), `listTechnicalSupportStaff()` via `/auth/users?role=technical_support` (returns `[]` on 403 so labels fall back to ids). `staffLabel(id, staff)` same shape as `coordinatorLabel`. `validateDescription(text)` → trimmed 1–2000 |
| `frontend/lib/notifications.ts` | Add `case "technical_support_assigned"` (G2) |
| `frontend/app/coordination/requests/[id]/technical-support-actions.ts` | **New, `"use server"`.** `recordSupportRequirement(prev, formData)` and `assignSupportStaff(prev, formData)` using `sendJson`; 401 → `redirect("/auth")` outside the try; read `detail.code` (new small helper — `readDetail` only handles string details); map codes: `support_not_allowed` → "Technical support can only be arranged for approved, planning or confirmed events", `staff_not_suitable` → "This person doesn't hold the required skill", `already_assigned` → "Already assigned to this requirement"; 403/404/422/502 → existing-style messages; success → `revalidatePath("/coordination/requests/{id}")`. Pattern: `venue-booking-actions.ts` (per-feature file, not the 235-line `coordination/actions.ts`) |
| `frontend/app/coordination/requests/[id]/technical-support-panel.tsx` | **New async server component** `TechnicalSupportPanel({ eventRequestId, status })` + `TechnicalSupportLoading`. Loads requirements, staff labels, and candidates per requirement in parallel. A failed requirements load → `role="alert"` message, never an empty list. Renders `TechnicalSupportList` (pure, testable): per requirement — skill label, description, "Recorded by …", assigned staff (email, assigned by, time) or "Nobody assigned yet"; candidate select (excluding `already_assigned`) + Assign button, or "No suitable Technical Support Staff hold the {Label} skill" with no button |
| `.../requirement-form.tsx`, `.../assign-staff-form.tsx` | **New `"use client"`.** `useActionState` like `cancel-booking-button.tsx`. Requirement form: textarea with live `n/2000` counter (error style over 2000), submit disabled + "Describe the support needed" when blank, select with exactly the four tags. Assign form: hidden ids, select, pending-disabled button, `role="alert"` for the mapped message; list unchanged on refusal |
| `frontend/app/coordination/requests/[id]/page.tsx` | Render `<Suspense fallback={<TechnicalSupportLoading/>}><TechnicalSupportPanel …/></Suspense>` after Venue bookings, only when `SUPPORT_STATUSES` includes `request.status` (the API rechecks; this just hides dead controls) |

No backend eventRequestService change. No migration change.

## 4. New frontend test cases (labels per `AGENTS.md`)

| ID | File | What it asserts |
| --- | --- | --- |
| AC1-X3 | panel test | blank → submit disabled + message; 2001 chars → counter "2001/2000" in error style, no action call; select offers exactly the four labels |
| AC1-H1 (F) | actions test | `recordSupportRequirement` POSTs `{description, skill_tag}` (trimmed, nothing else) to `/event-requests/{id}/technical-support/requirements` with the bearer token; revalidates the page |
| AC2-X6 | actions + panel tests | each 409 code → its exact message; assigned list unchanged; 401 → redirect `/auth`; network error → retry message |
| AC3-P6 | panel test | `livestream` requirement with `[]` candidates → "No suitable Technical Support Staff hold the Livestream skill", no Assign button |
| AC4-X1 | panel test | `tss-av` → "technical_support@example.com"; unknown id falls back to the id; empty requirement → "Nobody assigned yet"; failed load → alert, not empty state |
| AC5-H4 (new) | notifications test | `technical_support_assigned` → "You've been assigned as Audio-visual support for Tech Summit 2030.", `href` null; missing `event_name` still gives a sentence |
| AC5-H3a (E) | e2e spec | coordinator opens a seeded Planning event, records an AV requirement, assigns `technical_support@example.com`, sees it listed; TSS session opens Notifications and sees the AC5-H4 message; reload keeps it |

## 5. Shared-dev rollout and live evidence

1. Confirm `0051` is the latest migration on shared dev, then apply `0052_technical_support_assignments.sql` and `seed_technical_support_skills.sql`.
2. Create `technical_support2@example.com` (role `technical_support`) through authService, add tag `lighting`.
3. Grant checks (AC2-X4 on shared dev): `anon`/`authenticated` cannot execute the 3 functions + private helper or read the 3 tables.
4. AC5-H3b manual run (steps in the catalogue) with screenshots; record separately from local and CI results.
5. PR into `dev`; backend-ci, frontend-ci (lint, typecheck, build, unit, e2e) and conventional-commits green.

## 6. Timeline (sprint ends 22 Oct)

- **21 Oct:** approve G1–G4; commits 10a–12.
- **22 Oct:** commit 13, §5 rollout, PR. If e2e or rollout slips, close the sprint with increment 1 + frontend merged and carry 13–14 into Sprint 4, as plan §8 already allows — say so at standup rather than marking Done.

## 7. Decisions needed from you

1. **G1:** widen authService for coordinators → `technical_support` (recommended) or accept id labels?
2. **G3:** OK to add routes to the shared e2e mock servers (`event-request-api.mjs`, `auth-api.mjs`)? No existing route or spec changes.
3. **G2/G4:** notification text names the skill, not the description; no link. OK?
4. Add catalogue rows AC5-H4 and the AC5-H3a/H3b split?
