# SCRUM-26 Test Cases: Authenticate to the System

Last reviewed: 16 September 2026

[SCRUM-26: Authenticate to the System](https://is212g9t4.atlassian.net/browse/SCRUM-26)
asks that users sign in securely before accessing protected information or
functionality. The currently implemented protected area is event requests.

## How to run

| Area | Command | Result on 16 September 2026 |
| --- | --- | --- |
| Auth service | `cd backend/authService && uv run pytest -q` | 22 passed |
| Event-request service | `cd backend/eventRequestService && uv run --python 3.14 --extra dev pytest -q` | 25 passed |
| Frontend unit | `cd frontend && npm test` | 14 passed |
| Frontend browser | `cd frontend && npm run test:e2e` | 2 passed |
| Frontend lint, typecheck, build | `cd frontend && npm run lint && npm run typecheck && npm run build` | Passed |

The browser suite uses local auth and event-request stubs, not the shared
Supabase database. The old missing event-request helper was restored as part
of the protected frontend integration.

## Jira acceptance-criterion coverage

The criteria below follow the wording of SCRUM-26. The authService verifies
tokens with Supabase; eventRequestService takes the organiser ID only from that
verified response.

| ID | Acceptance criterion | Evidence | Status / missing test |
| --- | --- | --- | --- |
| AC1 | A user must authenticate before accessing any protected information or functionality. | `test_every_draft_operation_rejects_unauthenticated_requests`; protected frontend layout; browser redirect test. | Covered for the current event-request routes. |
| AC2 | Given valid credentials, when a user signs in, then a session is established for that user. | `test_login_returns_supabase_tokens`; `stores a verified login in an HTTP-only cookie`; browser login, protected-page access and logout journey; live `/auth/me` check. | Covered. Session lasts until the access token expires; automatic refresh is not implemented. |
| AC3 | Given invalid credentials, when a user attempts to sign in, then access is refused. | `test_login_maps_provider_errors` (401); frontend invalid-credential test; browser journey. | Covered. |
| AC4 | Unauthenticated requests to protected functionality are refused. | Missing/malformed/expired-token API tests, all five draft methods, browser redirect after logout, spoofed-header test. | Covered for the current event-request routes. |

Account registration is useful supporting functionality, but is not an
acceptance criterion in this story.

## Test cases

| ID | Scenario and steps | Expected result | Evidence |
| --- | --- | --- | --- |
| AUTH-01 | Register a new email with a password of at least 8 characters via `POST /auth/register`. | HTTP 201; user ID and email returned; no session token exposed. | `test_register_uses_supabase_auth` |
| AUTH-02 | Register while Supabase email confirmation is enabled. | Response says `email_confirmation_required: true`; user must confirm before first login. | `test_register_uses_supabase_auth` (mocked session absent) |
| AUTH-03 | Register with a password shorter than 8 characters. | HTTP 422; Supabase is not called. | `test_register_rejects_short_password` |
| AUTH-04 | Log in with valid email and password. | HTTP 200; Supabase access/refresh tokens and expiry returned; `Cache-Control: no-store`. | `test_login_returns_supabase_tokens` |
| AUTH-05 | Log in with invalid credentials. | HTTP 401; generic error does not reveal which credential was wrong. | `test_login_maps_provider_errors` |
| AUTH-06 | Log in with an unconfirmed email. | HTTP 403 with a confirmation-required error. | `test_login_maps_provider_errors` |
| AUTH-07 | Exceed provider login rate limit. | HTTP 429; UI does not claim success. | `test_login_maps_provider_errors` (API); UI rate-limit message not separately tested |
| AUTH-08 | Provider returns an internal/network error or no session. | HTTP 502; no token is returned. | `test_login_maps_provider_errors`, `test_login_maps_network_failure_to_bad_gateway`, `test_login_requires_session` |
| AUTH-09 | Submit an empty login password. | HTTP 422; Supabase is not called. | `test_login_rejects_empty_password` |
| AUTH-10 | Open `/auth`, switch between Log in and Sign up. | Both forms show labelled email/password fields and the correct submit action. | `shows accessible login and sign-up forms` |
| AUTH-11 | Submit sign-up through the frontend server action. | Request reaches authService; UI distinguishes immediate registration from email-confirmation-required registration. | `registers through authService and handles confirmation` (immediate path automated; confirmation message branch not separately asserted) |
| AUTH-12 | Submit login through the frontend server action. | HTTP-only, same-site access-token cookie is set; browser opens protected event requests. | `stores a verified login in an HTTP-only cookie`; `protected pages require a valid session` |
| AUTH-13 | Submit invalid credentials or use an unavailable authService from the UI. | Error is visible; no success state is shown. | `reports invalid credentials and an unavailable service`; live browser invalid-login check |
| AUTH-14 | Configure the service with a publishable key, then remove required settings. | Key is used server-side, omitted from settings representation; missing settings fail validation. | `test_supabase_client_uses_configured_publishable_key`, `test_settings_load_supabase_environment`, `test_settings_require_supabase_credentials` |
| AUTH-15 | Call service root and health endpoints. | Both return expected service/readiness payloads. | `test_hello`, `test_health` |
| AUTH-16 | Call `/auth/me` with a valid, missing, malformed or expired bearer token. | Valid token returns the verified user ID; all invalid cases receive 401. | `test_current_user_verifies_supabase_access_token`, `test_current_user_requires_bearer_token`, `test_current_user_rejects_invalid_token` |
| AUTH-17 | Call every draft API method without a bearer token. | All receive 401 before reading or changing a draft. | `test_every_draft_operation_rejects_unauthenticated_requests` |
| AUTH-18 | Add a spoofed `X-Organiser-Id` while presenting no or another user's bearer token. | Header cannot grant access or change the verified organiser ID. | `test_organiser_header_cannot_bypass_authentication`, `test_verified_identity_overrides_spoofed_header`, `test_other_organiser_cannot_read_update_or_delete` |
| AUTH-19 | Log out and revisit a protected page. | Browser cookie is removed and route redirects to `/auth`. | `logout clears the session cookie`; browser protected-page journey |

## Live development-project checks

On the SPM G9T4 **development** Supabase project, `Confirm email` was disabled
and `/auth/v1/settings` reported confirmation not required. A synthetic account
registered through authService (HTTP 201, confirmation not required) and then
logged in (HTTP 200, access token present). A second synthetic account also
passed `/auth/me` verification with the same user ID after login. An anonymous
request to the Supabase event-request Data API returned 401. The browser `/auth` page loaded,
switched modes, and showed an error for an invalid login against the live
service. These are manual checks, not repeatable CI tests; the synthetic user
remains in the development project. No password or token is recorded here.

## Boundaries and follow-up

- The current browser cookie contains only the access token. Once it expires,
  the user signs in again; refresh-token rotation is future work.
- Existing drafts keyed to older temporary organiser names remain stored but
  are not automatically associated with new Supabase user IDs. A separate
  migration would need an explicit ownership mapping.
- A full live browser-to-event-request-DB journey was not run because the local
  event-request service does not have the shared project's server secret.
- Re-enable email confirmation and verify the confirmation journey before any
  production deployment.
