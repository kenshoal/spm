# SCRUM-26 — Authenticate to the System

Source: [Jira SCRUM-26](https://is212g9t4.atlassian.net/browse/SCRUM-26). The
story asks that users sign in securely before accessing protected information
or functionality. The currently implemented protected area is the event-request
workspace.

Status (1 November 2026): this document was converted to the standard two-matrix
format (`testing.md` §4) from the 16 September 2026 revision. **AI-drafted test
design, teammate review pending (`testing.md` §10); Jira remains the source of
truth.** The labelled-test pass added comments only to files owned by this
sweep; execution evidence below is not re-claimed — every row is **Not
executed** in this pass, and the 16 September results are preserved as
provenance, not as current evidence (`testing.md` §8).

## Story contract

- AC1: A user must authenticate before accessing any protected information or functionality.
- AC2: Given valid credentials, when a user signs in, then a session is established for that user.
- AC3: Given invalid credentials, when a user attempts to sign in, then access is refused.
- AC4: Unauthenticated requests to protected functionality are refused.

### Scope

- **Included:** the authService endpoints (`/auth/register`, `/auth/login`,
  `/auth/me` and the authentication gates of the role endpoints), the frontend
  auth server actions and page guards, and the protected event-request
  workspace journey in the browser.
- **Excluded:** account registration as product behaviour (useful supporting
  functionality, not an acceptance criterion of this story); refresh-token
  rotation (future work — a session lasts until the access token expires);
  live development-project checks (manual, recorded in the 16 September
  revision and in the git history of this file); unauthenticated-refusal checks
  owned by other services (cross-referenced below, named not claimed).
- **Related stories:** SCRUM-27 (which features an authenticated user may use,
  by role), SCRUM-39 (data access restricted by relationship).

### Actors and permissions

- **Unauthenticated visitor:** only `/` , `/health` and `/auth` are reachable; every protected page redirects to `/auth`.
- **Authenticated user:** holds the session tokens issued by Supabase via authService; which features they may use is SCRUM-27's concern.
- authService verifies every bearer token against Supabase and reads roles only
  from `app_metadata` / the `staff_roles` table; identity is never taken from a
  client-supplied header or `user_metadata`.

### Assumptions and open questions

1. A session is valid until its access token expires; there is no automatic refresh.
2. Drafts created before Supabase identities existed are keyed to temporary
   organiser names and are not auto-associated with Supabase user IDs; a
   migration with an explicit ownership mapping would be needed.
3. Email confirmation was disabled on the development Supabase project for the
   16 September checks; re-enable it and verify the confirmation journey before
   any production deployment.
4. The 16 September browser suite used local auth and event-request stubs, not
   the shared Supabase database.

## Cross-references (named, not claimed)

Refusals of unauthenticated requests are also enforced inside each consuming
service. Those checks belong to those services' stories; they are listed here
so a reader can find them, but they are not rows of this story's matrix and
their labels cite their own stories:

- `backend/eventRequestService/tests/test_event_request_controller.py`:
  `test_every_operation_rejects_unauthenticated_requests` (the 16 September
  revision named this test as
  `test_every_draft_operation_rejects_unauthenticated_requests`; the draft
  wording is out of date), `test_organiser_header_cannot_bypass_authentication`,
  `test_verified_identity_overrides_spoofed_header`,
  `test_other_organiser_cannot_read_update_or_delete`.
- `backend/venueService/tests/test_booking_requests_by_event.py` (`AC3-X1`),
  `backend/venueService/tests/test_venue_calendar.py` (`AC1-X1`),
  `backend/venueService/tests/test_booking_requests_cancel.py` (`AC4-X2`) — each
  carries a "a request without a token is refused" case for the venue story.
- `frontend/e2e/organisation-access.spec.ts` — SCRUM-39's `AC2-X2` shared-request journey under a valid session.

## Supporting infrastructure (not AC-mapped)

These automated tests exist and are recorded by the 16 September revision
(AUTH-01–03, AUTH-11, AUTH-14, AUTH-15) but prove no acceptance criterion of
this story, so they are deliberately left unlabelled and out of the matrix:

- Registration behaviour: `test_register_uses_supabase_auth`,
  `test_register_rejects_short_password` (backend/authService/tests/test_registration.py);
  the server-action registration test in `frontend/__tests__/auth.test.tsx`.
- Configuration and service bootstrap:
  `test_supabase_client_uses_configured_publishable_key` (tests/test_supabase.py),
  `test_settings_load_supabase_environment`,
  `test_settings_require_supabase_credentials` (tests/test_config.py),
  `test_hello` and `test_health` (tests/test_main.py).

## Test case specification

Layers: A = API (authService pytest), UI = frontend Vitest, E2E = Playwright.

| ID | AC | Test scenario | Technique | Pre-conditions | Test steps | Test data | Expected result | Forbidden side effects | Layer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AC1-H1 | AC1 | An authenticated Organiser passes the protected workspace guard | Happy | Session cookie holds a valid token; the verified roles include `event_organiser` | Resolve the `/event-requests` page guard with the session | Token `valid-token`; roles `["attendee", "event_organiser"]` | Guard resolves with the verified user (id, email, both roles); no redirect | — | UI |
| AC1-X1 | AC1, AC3, AC4 | The protected browser journey refuses missing and expired sessions and admits a valid login | Cross-cutting | Playwright app against the local auth/event-request stubs; a valid account exists in the stub | Visit `/event-requests` signed out; retry with an `expired` cookie; submit a wrong then the right password; log out and revisit | `playwright@example.com`; `wrong-password`, then `test-password-123` | Signed out and expired: URL `/auth`; wrong password: the invalid-credentials message and URL stays `/auth`; valid: `/event-requests` with the workspace heading; after logout the page redirects to `/auth` again | No protected content renders without a valid session | E2E |
| AC1-X2 | AC1, AC2 | Roles come only from server-trusted sources; a client-supplied role claim is ignored | Cross-cutting | Supabase stub returns a user whose `app_metadata` and `user_metadata` disagree | `GET /auth/me` with a valid bearer token | `app_metadata.role = event_organiser`, `user_metadata.role = admin` | 200; `role`/`roles` reflect `event_organiser`; the `user_metadata` claim is ignored; `Cache-Control: no-store` | No elevated role is returned | A |
| AC2-H1 | AC2 | Valid credentials return Supabase session tokens | Happy | Supabase stub accepts the sign-in | `POST /auth/login` | Valid email and password | 200 with `access_token`, `refresh_token`, `expires_in`, `token_type`; `Cache-Control: no-store` | — | A |
| AC2-H2 | AC2 | The UI verifies the login and stores it in an HTTP-only cookie | Happy | authService stub reachable | Submit the login server action; inspect the cookie, the `/auth/me` call and the redirect | `person@example.com` / `long-password-123` | `cs_access_token` set `httpOnly`, `sameSite: lax`, `maxAge: 3600`; `/auth/me` called with `Bearer`; redirect to `/event-requests` | — | UI |
| AC2-H3 | AC2 | `/auth/me` verifies the token and returns the identity and roles | Happy | Valid Supabase session | `GET /auth/me` with `Bearer access-token` | — | 200 with the verified `id`, `email`, `role`, `roles`; `Cache-Control: no-store` | — | A |
| AC2-H4 | AC2 | The sign-in screen presents accessible log in and sign up forms | Happy | — | Render `/auth`; switch between Log in and Sign up | — | Labelled Email and Password fields and the mode's submit action in both modes | — | UI |
| AC2-H5 | AC2, AC1 | A valid login lands on the protected workspace | Happy | As AC1-X1 | Log in with the valid account | `playwright@example.com` | `/event-requests`; the "Your event requests" heading is visible | — | E2E (same test as AC1-X1) |
| AC2-N1 | AC2 | An empty login password is rejected before the provider is called | Negative | — | `POST /auth/login` with an empty password | Password `""` | 422; Supabase is not called | No tokens issued | A |
| AC2-B1 | AC2 | A password just below the minimum length is refused at validation | Boundary | — | `POST /auth/login` with a 0-character password (below the 1-character minimum) | Password `""` | 422; provider not called | No tokens issued | A (same test as AC2-N1) |
| AC2-B2 | AC2 | A password of exactly the minimum length passes validation and reaches the provider | Boundary | Supabase stub running | `POST /auth/login` with a 1-character password | Password `x` | Not 422 — the request reaches Supabase (the stub's 401 is the refusal path, not a validation failure) | — | A |
| AC2-N2 | AC2 | A failed role verification leaves no session | Negative | authService `/auth/me` returns 503 after the token is issued | Submit the login server action | Valid credentials | Message "The authentication service could not verify your workspace access."; no cookie stored; no redirect | No `cs_access_token` cookie exists | UI |
| AC2-X1 | AC2 | Logout removes the session | Cross-cutting | Signed in | Submit the logout server action | — | `cs_access_token` deleted; redirect to `/auth` | No session cookie remains | UI |
| AC3-N1 | AC3 | Invalid credentials are refused with a generic message | Negative | Supabase rejects the sign-in with a 4xx error | `POST /auth/login` | Wrong password | 401 "Invalid email or password"; no tokens; the wrong credential is not revealed | — | A |
| AC3-N2 | AC3 | An unconfirmed email is refused with the confirmation error | Negative | Supabase error `email_not_confirmed` | `POST /auth/login` | Valid-shaped credentials, unconfirmed email | 403 "Email confirmation required"; no tokens | — | A |
| AC3-N3 | AC3 | A rate-limited login is refused with 429 | Negative | Supabase returns 429 | `POST /auth/login` | — | 429 "Too many login attempts"; no tokens | — | A |
| AC3-N4 | AC3 | A provider outage or session-less response is a 502 with no token | Negative | Supabase network failure, or sign-in returns no session | `POST /auth/login` | — | 502; no token in the response | — | A |
| AC3-N5 | AC3 | The UI shows invalid credentials without a success state | Negative | authService returns 401 | Submit the login server action | `person@example.com` / wrong password | The result is not a success; the error is visible | No session cookie exists | UI |
| AC3-N6 | AC3 | The browser stays on `/auth` after a failed login | Negative | As AC1-X1 | Log in with a wrong password | `wrong-password` | The invalid-credentials message is visible; URL still `/auth` | — | E2E (same test as AC1-X1) |
| AC4-N1 | AC4 | `/auth/me` refuses a missing or malformed bearer header before the provider is called | Negative | — | `GET /auth/me` with no header, `Basic abc`, `Bearer ` and `Bearer a b` | The four header shapes | 401 "Authentication required" for each; `supabase.auth.get_user` never called | — | A |
| AC4-N2 | AC4 | An invalid or expired token is refused | Negative | Supabase rejects the JWT with 401 | `GET /auth/me` with `Bearer expired` | — | 401 "Invalid session" | — | A |
| AC4-N3 | AC4 | A provider outage while verifying fails closed with 502 | Negative | Supabase unreachable | `GET /auth/me` with a syntactically valid bearer header | — | 502; no user returned | — | A |
| AC4-N4 | AC4, AC2 | The role-assignment endpoint refuses a caller with no session | Negative | — | `PATCH /auth/users/{user_id}/role` without an Authorization header | — | 401; no role write attempted | `staff_roles` unchanged | A |
| AC4-N5 | AC4 | The staff listing endpoint refuses a caller with no session | Negative | — | `GET /auth/users?role=event_coordinator` without a token | — | 401 | — | A |

## Cross-reference note on AC1 and AC4 for other services

AC1 and AC4 also hold for every protected route of every service (event
requests, registrations, venues, equipment, …). This matrix claims only the
authService's own checks plus the frontend auth client; the per-service
refusals are listed under **Cross-references** above, named not claimed.

## Conversion notes (16 September → 1 November)

| Old ID | New ID | Note |
| --- | --- | --- |
| AUTH-01, AUTH-02, AUTH-03, AUTH-11 | — | Registration is supporting functionality, not an AC; tests exist, unlabelled (see Supporting infrastructure) |
| AUTH-04 | AC2-H1 | |
| AUTH-05 | AC3-N1 | |
| AUTH-06 | AC3-N2 | |
| AUTH-07 | AC3-N3 | |
| AUTH-08 | AC3-N4 | |
| AUTH-09 | AC2-N1, AC2-B1 | The empty password sits just below login's 1-character minimum; the at-minimum case is new row AC2-B2 |
| AUTH-10 | AC2-H4 | |
| AUTH-12 | AC2-H2, AC2-H5 | |
| AUTH-13 | AC3-N5, AC3-N6 | |
| AUTH-14, AUTH-15 | — | Configuration and health checks are not AC-mapped; tests exist, unlabelled |
| AUTH-16 | AC2-H3, AC4-N1, AC4-N2 | AC1-X2 adds the role-source check the old file described only in prose |
| AUTH-17 | — | Cross-reference only; the test was renamed to `test_every_operation_rejects_unauthenticated_requests` and lives in eventRequestService |
| AUTH-18 | AC1-X2 (authService half) | The eventRequestService header-spoof tests are cross-referenced, not claimed |
| AUTH-19 | AC2-X1, AC1-X1 | |

## Latest execution record

This pass (1 November 2026) added label comments only; **no suite was run**, so
every row is **Not executed**. The 16 September 2026 results recorded by the
previous revision (authService 22 passed, event-request service 25 passed,
frontend unit 14 passed, browser 2 passed, lint/typecheck/build clean) are
historical provenance for a different commit and are not re-claimed here
(`testing.md` §8). "Automated (label added in this pass)" marks tests whose
label comment was added on this branch; "Automated (existing test)" marks tests
that exist but sit in files outside this sweep's file list, so their labels
remain to be added by the story owner.

| ID | Automation status | Actual result | Execution status | Build or commit | Executed by and date | Remarks and evidence |
| --- | --- | --- | --- | --- | --- | --- |
| AC1-H1, AC2-H2, AC2-H4, AC2-N2, AC2-X1, AC3-N5 | Automated (label added in this pass) | Not run in this pass | Not executed | docs/testcase-gap-sweep, 1 Nov 2026 | Claude for Yang Xue, 1 Nov 2026 | `frontend/__tests__/auth.test.tsx`. Registration and config assertions inside two of these tests are supporting behaviour, not AC-mapped (see Conversion notes) |
| AC1-X1, AC2-H5, AC3-N6 | Automated (label added in this pass) | Not run in this pass | Not executed | docs/testcase-gap-sweep, 1 Nov 2026 | Claude for Yang Xue, 1 Nov 2026 | `frontend/e2e/auth.spec.ts`, first test. One test proves the three IDs; one label, three ACs |
| AC1-X2, AC2-H1, AC2-H3, AC2-N1, AC2-B1, AC3-N1, AC3-N2, AC3-N3, AC3-N4, AC4-N1, AC4-N2, AC4-N3, AC4-N4 | Automated (label added in this pass) | Not run in this pass | Not executed | docs/testcase-gap-sweep, 1 Nov 2026 | Claude for Yang Xue, 1 Nov 2026 | `backend/authService/tests/test_registration.py` — labels added in the follow-through pass. AC1-X2 and AC2-H3 share `test_current_user_verifies_supabase_access_token`; AC2-H1 is `test_login_returns_supabase_tokens`; AC2-N1 and AC2-B1 share `test_login_rejects_empty_password`; AC3-N1–N3 share the parametrized `test_login_maps_provider_errors` (whose fourth case is AC3-N4's provider 500, also proven by `test_login_requires_session` and `test_login_maps_network_failure_to_bad_gateway`); AC4-N1 is the parametrized `test_current_user_requires_bearer_token`; AC4-N2 is `test_current_user_rejects_invalid_token`; AC4-N3 is `test_current_user_maps_provider_failure`; AC4-N4 is `test_admin_endpoint_requires_authentication` (one shared label with SCRUM-27 AC2-N5) |
| AC4-N5 | Automated (existing test) | Not run in this pass | Not executed | docs/testcase-gap-sweep, 1 Nov 2026 | Claude for Yang Xue, 1 Nov 2026 | `backend/authService/tests/test_registration.py::test_list_users_requires_authentication` — the test already carries SCRUM-14's AC2-N13 label and a test takes one label, so it is named here, not re-labelled |
| AC2-B2 | Automated (backfilled 6 Nov 2026 — behaviour had already shipped) | 1-char password passes validation and reaches the provider (stub 401, not 422); `sign_in_with_password` called once with it | Pass | working tree, branch `test/backfill-planned-cases` | Claude for Yang Xue, 6 Nov 2026 | `backend/authService/tests/test_registration.py::test_login_minimum_length_password_reaches_provider` — `LoginRequest.password` is `min_length=1`, so 1 character is exactly at the minimum; authService suite 85 passed |
