# SCRUM-57 — Notify Event Workflow Changes: cancellation and delivery options

**Issue tracker:** SCRUM-57

**User story:** As a user responsible for an event, I want to be notified when its workflow or important arrangements change, so that I can take the action required of my role.

**Status of this document (1 November 2026): test design approved for AC2 and AC3 (27 October 2026); AC1 split into AC1 (Organiser and Coordinator, designed 1 November 2026, build requested by Tate Lim) and AC1b (venue and equipment staff, on hold).** The test design was drafted with AI assistance. AC2/AC3 and assumptions A2–A5 were reviewed and approved by Tate Lim (story owner) on 27 October 2026. The AC1 cases below, and assumptions A6–A7, were drafted on 1 November 2026 and have **not** had a separate design review; Tate asked for AC1 to be built on that date. AC1b is not designed until the PO answers Q1.

## Story contract review

Issue tracker lists two bullets. Numbering follows them, with the second bullet split in two because it holds two independently testable rules.

| issue tracker bullet | Outcome | Reason | Proposed wording |
| --- | --- | --- | --- |
| 1. Cancellation notice to Organiser, Coordinator and venue/equipment staff | **Split** → **AC1** (Organiser, Coordinator) and **AC1b** (staff, **on hold**) | Intent is valid. The Organiser and the assigned Coordinator are known for every event. The staff recipients are not defined, because staff have no individual assignment to a booking. Asked the PO on 27 Oct 2026 (Telegram, message 2825). | AC1: Given an event is cancelled, when the cancellation is recorded, then the Organiser and the assigned Coordinator are each notified once. AC1b: …and the staff responsible for its committed venue or equipment arrangements are each notified once. _Staff rule to be confirmed by the PO._ |
| 2a. Per-type channel setting | **Split** from bullet 2 → **AC2** | Choosing a channel per type and delivering by email are separate behaviours with separate failure modes. | AC2: Given a notification of a given type is sent, when the channel setting for that type is in-app, email or both, then it is delivered by exactly the chosen channel(s). A type with no setting is delivered in-app only. |
| 2b. Email delivery | **Split** from bullet 2 → **AC3** | As above. The "failed email never fails the action" rule is observable and gets its own cases. | AC3: Given a notification is delivered by email, when it is sent, then the recipient receives one email for it, and a failed email never fails or rolls back the action that caused the notification. |

Scope effect: AC2 and AC3 are one shared change in notificationService (and one migration). AC1 reuses the existing `POST /notifications/events` and needs no change in notificationService; it is a change in eventRequestService plus the inbox wording in the frontend. AC1b adds the staff recipients later, so it can follow without reworking AC1, AC2 or AC3.

## Included and excluded behaviour

**Included:** channel setting per notification type; email delivery through SMTP; idempotent email (no second email for a retried event); email failure isolated from the caller; cancellation notices to the Organiser and the assigned Coordinator (AC1); to staff (AC1b, once the staff rule is agreed).

**Excluded (named, not claimed):**

- Approved and rejected notices: SCRUM-36 (done).
- Cancellation notices to registered attendees: SCRUM-38 (done, `event_cancelled`).
- Notices for approved significant changes to arrangements: SCRUM-64.
- Batching and per-user on/off switches: dropped by the PO on 23 Oct 2026 (clarifications #55 and #37).
- Authenticating `POST /notifications/events` and retrying the clarification notice through the outbox: engineering items in the issue tracker, not ACs.
- Editing the setting through the application: no admin screen or endpoint; the setting is changed in the database (decided with the story owner, 27 Oct 2026).

## Actors and relationship permissions

- **Callers** (eventRequestService, venueService, equipmentService) send events to `POST /notifications/events` and are unchanged. The endpoint is still unauthenticated (engineering item, excluded).
- **Recipients** are identified by `recipient_id`. A recipient receives an email only at their own address, and never sees another recipient's address.
- **Channel setting** is read and changed only by someone with database access. Browsers get no access to it (same rule as `public.notifications`, migration 0017).

## Allowed state transitions

None. The story reacts to transitions owned by other stories (cancellation: `POST /event-requests/{id}/cancellation`).

## Persistence and atomicity

- The notification row is stored first, exactly as today. The email is sent only when that insert created a **new** row, so the existing `(recipient_id, event_id)` uniqueness also prevents duplicate emails.
- A failure to look up the setting, find the address or send the email is logged and swallowed. The row stays stored and the endpoint still answers `202`.
- New table `public.notification_channel_settings (event_type, channel)` with `channel` limited to `in_app`, `email`, `both` (migration 0065, not yet written).

## Assumptions and open questions

| # | Item | Status |
| --- | --- | --- |
| Q1 | Which staff are notified on cancellation (AC1b). Proposed: the venue staff member who approved each booking (`decided_by`) and the technical support member who last updated each equipment item (`updated_by`), as proposed in SCRUM-64. | Asked the PO 27 Oct 2026; **no answer yet**. AC1b stays on hold. |
| A1 | Email provider: plain SMTP settings (host, port, user, password, sender). Real delivery via a dedicated Gmail account with an app password; Mailtrap sandbox for development. | Agreed with the story owner 27 Oct 2026. Gmail app-password behaviour **not yet verified** for this account. |
| A2 | A type set to `email` only is still stored once (it is the duplicate guard) but is **not shown in the inbox**. | **Assumption, needs review.** Needs a column or filter on `notifications`. |
| A3 | Email wording: a short generic message (type, one line, link to the inbox). Wording for each type lives in the frontend today (`describeNotification`) and is **not** duplicated in the backend. | **Assumption, needs review.** |
| A4 | The recipient's address is looked up from Supabase Auth with the server key. | **Unverified.** Confirm the lookup works for the user ids that callers send before building. |
| A5 | If the setting cannot be read, the notification falls back to in-app only. | **Assumption.** The requirement does not say. |
| A6 | Only the assigned Coordinator can cancel (`POST /event-requests/{id}/cancellation`), so the Coordinator notice is a notice to the person who just cancelled. AC1 says the Coordinator is notified, so they are, once; the notice is a record in their inbox. | **Assumption, needs review.** Say if the Coordinator should be left out when they are the one cancelling. |
| A7 | The Organiser and Coordinator get their own notice type, `event_cancellation_recorded`, separate from the Attendee's `event_cancelled`. Someone who is both an Attendee and the Organiser gets both. The notice links to the event and names it. | **Assumption, needs review.** Channel settings (AC2) apply to the new type by name; with no setting it is in-app. |

## Specification

AC1b is not designed yet; its cases are written once Q1 is answered. AC1 cases are listed first; a person is "told" when notificationService receives one `event_cancellation_recorded` notice for them.

| ID | AC | Test scenario | Technique | Pre-conditions | Test steps | Test data | Expected result | Forbidden side effects | Layer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AC1-H1 | AC1 | Cancelling tells the Organiser and the assigned Coordinator | Happy | Confirmed event; Organiser `organiser-1`; assigned Coordinator `coord-1`; spy notification client | 1. Coordinator cancels the event | `event_id`, event name | `200`, status `Cancelled`; one notice each to `organiser-1` and `coord-1`, each naming the event | A notice to anyone else | API |
| AC1-P1 | AC1 | One person who is both Organiser and Coordinator gets one notice | Partition | Organiser id equals Coordinator id | Cancel the event | same id | One notice to that person | Two notices to one person | API |
| AC1-P2 | AC1 | A cancellation before any Attendee registered still tells the Organiser and Coordinator | Partition | No registered Attendees | Cancel the event | none | Notices to Organiser and Coordinator; none to Attendees | No notice only because there are no Attendees | API |
| AC1-X1 | AC1 | Attendee notices are unchanged | Cross-cutting | Two registered Attendees | Cancel the event | `attendee-1`, `attendee-2` | Attendees still get `event_cancelled`; Organiser and Coordinator get `event_cancellation_recorded` | An Attendee told with the Organiser wording, or the reverse | API |
| AC1-H2 | AC1 | The client posts one notice per recipient with a stable key | Happy | Fake HTTP post | Call the client for two recipients | `organiser-1`, `coord-1` | Two posts, type `event_cancellation_recorded`, key per event and recipient, payload has the event id and name | A shared key for two recipients | Unit |
| AC1-N1 | AC1 | A refused cancellation tells nobody | Negative | Terminal status, or a Coordinator who is not assigned | Cancel the event | `Completed`/`coord-1`; `Confirmed`/`coord-2` | `409` / `403`; status unchanged; no notice | Any notice | API |
| AC1-N2 | AC1 | If the Coordinator cannot be looked up, the cancellation stands and the Organiser is still told | Negative | Coordinator lookup raises a repository error | Cancel the event | as above | `200`, `Cancelled`; Organiser told; error logged | `5xx`; no notice to the Organiser | API |
| AC1-N3 | AC1 | An unreachable notification service never blocks the cancellation | Negative | HTTP post raises a connection error | Cancel the event | as above | `200`, `Cancelled` | `5xx`; status rolled back | API |
| AC1-B1 | AC1 | Cancelling twice tells nobody twice | Boundary | Event already `Cancelled` | Cancel again | as above | Second call refused (`409`); no further notice | A second notice | API |
| AC1-X2 | AC1 | The inbox shows the notice with the event name and a link | Cross-cutting | Notice of the new type | Describe it for the Organiser and for the Coordinator | type, payload | Text names the event as cancelled; link goes to the event (`/event-requests/{id}/edit` for the Organiser, `/coordination/requests/{id}` for the Coordinator) | A blank text; no link | Unit (frontend) |
| AC2-H1 | AC2 | A type set to `email` reaches the recipient by email | Happy | Setting `event_type=clarification_requested, channel=email`; fake mail sender; fake repository; recipient has address `organiser@test.local` | 1. POST an event of that type for that recipient | `event_id=ev-1` | `202`; one email to `organiser@test.local`; row stored once | No email to anyone else | API |
| AC2-P1 | AC2 | `in_app` stores the row and sends no email | Partition | Setting `channel=in_app` | POST an event | as above | `202`; row stored and visible in the inbox; zero emails | Any email sent | API |
| AC2-P2 | AC2 | `both` gives an inbox row and one email | Partition | Setting `channel=both` | POST an event | as above | `202`; row stored and visible in the inbox; one email | A second email | API |
| AC2-P3 | AC2 | `email` only is not shown in the inbox | Partition | Setting `channel=email` (see A2) | POST an event, then GET `/notifications` as the recipient | as above | One email; inbox list does not include it | Row visible in the inbox | API |
| AC2-P4 | AC2 | A type with no setting is delivered in-app only | Partition | No setting row for the type | POST an event | `event_type=coordinator_assigned` | `202`; inbox row; zero emails | Any email sent | API |
| AC2-X1 | AC2 | A setting for one type does not change another | Cross-cutting | Setting for type A = `both`; none for type B | POST one event of each type | A and B | A: inbox + email; B: inbox only | Email for B | API |
| AC2-N1 | AC2 | The database refuses a channel outside the three allowed values | Negative | Migration 0065 applied | Insert a setting with `channel=sms` | `sms` | Constraint violation; no row written | A stored `sms` setting | DB |
| AC2-N2 | AC2 | An unreadable setting falls back to in-app (see A5) | Negative | Settings store raises an error | POST an event | as above | `202`; inbox row stored; zero emails; error logged | `5xx`; lost notification | API |
| AC3-H1 | AC3 | One email carries the notification to the right address | Happy | Setting `both`; fake mail sender | POST an event with `payload.event_request_id` | `ev-1` | One email: to the recipient only, subject names the type, body links to the inbox | Other recipients in To/Cc/Bcc | Unit |
| AC3-N1 | AC3 | A mail server failure does not fail or undo the action | Negative | Mail sender raises a connection error | POST an event | `ev-1` | `202`; inbox row still stored; failure logged | `5xx`; row removed | API |
| AC3-N2 | AC3 | A retried event sends no second email | Negative | Event `ev-1` already stored and emailed | POST the same event again | `ev-1` | `202`; still one row; still one email | A second email | API |
| AC3-N3 | AC3 | A recipient with no address gets the inbox row only | Negative | Address lookup returns none | POST an event | `recipient_id=no-email-user` | `202`; inbox row stored; zero emails; reason logged | `5xx` | API |
| AC3-N4 | AC3 | Mail settings missing does not break the service or the action | Negative | SMTP host not set; setting `email` | Start the app; POST an event | as above | App starts; `202`; inbox row stored; zero emails; reason logged | Start-up failure; `5xx` | API |
| AC3-P1 | AC3 | The same `event_id` for two recipients emails each once | Partition | Setting `both` | POST `ev-1` for two recipients | two addresses | Two emails, one per recipient; two rows | One email to both; one skipped | API |
| AC3-P2 | AC3 | A type with no known wording still gets a generic email | Partition | Setting `email`; type not in any wording list | POST an event | `event_type=future_type` | One email with generic wording and the inbox link | No email; blank body | Unit |
| AC3-P3 | AC3 | A server needing no login and no encryption is used as given | Partition | Fake SMTP; `smtp_starttls=false`, no user | Send one message | `smtp_host=localhost` | No login, no encryption step; message sent | Login attempted with empty credentials | Unit |
| AC3-P4 | AC3 | A configured host selects the SMTP mailer, and none selects the stand-in | Partition | Settings with and without `smtp_host` | Build the mailer | as stated | `SmtpMailer` with a host; stand-in without | Silent no-op when no host | Unit |
| AC3-N5 | AC3 | An address lookup outage skips the email and keeps the action | Negative | Supabase Auth answers `500` | Look up an address | a user id | Lookup error raised, so Delivery logs it and sends nothing | `5xx` to the caller; an email to a wrong address | Unit |
| AC3-X1 | AC3 | A real mail server accepts and delivers the message | Cross-cutting | Gmail test account or Mailtrap sandbox configured in `.env`; shared database | Send one event with setting `both` | team test address | Email arrives in the real or sandbox inbox | Secrets in the email or the logs | Manual |

## Latest execution record

Local results below are **not** CI, shared-database or real-mail results; keep them separate.
Command (27 Oct 2026, on commit 78b9cd4): `cd backend/notificationService && .venv/bin/python -m pytest -q` (82 passed) and `ruff check .` (clean). Dependencies faked: Supabase, the Auth lookup and SMTP. AC2-P3 and the migration: 0065 was applied to the shared dev database on 27 Oct 2026 and its catalog checks passed (`database/verify_notification_channel_settings.sql`); the other cases were not run against it. Run on 27 Oct 2026 after the above: the live Auth lookup (read-only) and one real SMTP send to a Mailtrap sandbox (AC3-X1, sandbox only). Still not run: CI, delivery to a real inbox, the channel setting read in the same live run, and a refused insert (AC2-N1).

| ID | Automation status | Actual result | Execution status | Build or commit | Executed by and date | Remarks and evidence |
| --- | --- | --- | --- | --- | --- | --- |
| AC2-H1 | Planned | | Not executed | | | |
| AC2-P1 | Planned | | Not executed | | | |
| AC2-P2 | Planned | | Not executed | | | |
| AC2-P3 | Green | As expected | Pass (local, fakes) | commit 78b9cd4, local | Claude (AI) for Tate Lim, 27 Oct 2026 | test_email_delivery.py::test_an_email_only_type_is_not_shown_in_the_inbox; test_repository.py. Column `in_inbox` exists on the shared DB (catalog check); inbox behaviour not run against it (Depends on A2) |
| AC2-P4 | Planned | | Not executed | | | |
| AC2-X1 | Planned | | Not executed | | | |
| AC2-N1 | Not automated | See remarks | Not executed | commit 78b9cd4, local | Claude (AI) for Tate Lim, 27 Oct 2026 | Shared DB: `database/verify_notification_channel_settings.sql` passed, but it reads the constraint definition only. A refused insert was NOT run (Needs migration 0065) |
| AC2-N2 | Green | As expected | Pass (local, fakes) | commit 78b9cd4, local | Claude (AI) for Tate Lim, 27 Oct 2026 | test_email_delivery.py::test_an_unreadable_setting_falls_back_to_in_app; test_adapters.py::test_a_settings_failure_is_raised (Depends on A5) |
| AC3-H1 | Planned | | Not executed | | | |
| AC3-N1 | Planned | | Not executed | | | |
| AC3-N2 | Planned | | Not executed | | | |
| AC3-N3 | Green | As expected | Pass (local, fakes) | commit 78b9cd4, local | Claude (AI) for Tate Lim, 27 Oct 2026 | test_email_delivery.py; test_adapters.py::test_no_address_found (4 partitions) (Depends on A4) |
| AC3-N4 | Planned | | Not executed | | | |
| AC3-P1 | Planned | | Not executed | | | |
| AC3-P2 | Green | As expected | Pass (local, fakes) | commit 78b9cd4, local | Claude (AI) for Tate Lim, 27 Oct 2026 | test_email_delivery.py::test_an_unknown_type_gets_a_generic_email (Depends on A3) |
| AC3-X1 | Manual | One email sent through Delivery with the live Auth lookup and real SMTP; no failure logged; the story owner confirmed one message in the Mailtrap sandbox inbox | Pass (sandbox only) | code 78b9cd4, run from f8fb91b; shared dev Supabase, Mailtrap sandbox | Claude (AI) for Tate Lim, 27 Oct 2026 | Recipient: seeded `event_organiser@example.com` (sandbox catches it; nothing left Mailtrap). Sender `ConnectSphere <no-reply@connectsphere.test>`. LIMITS: the channel setting was stubbed to `email` so the shared DB was not written; the story owner confirmed the message arrived but did not report its To, Subject or body, so those were not checked; no real inbox received mail (Gmail not tried). Live Auth admin lookup also checked read-only: seeded user found, unknown id and non-UUID id gave no address, settings table readable (`in_app` for no row) |
| AC2-H1 | Green | As expected | Pass (local, fakes) | commit 78b9cd4, local | Claude (AI) for Tate Lim, 27 Oct 2026 | test_email_delivery.py::test_an_email_type_is_sent_to_the_recipient_only; test_adapters.py::test_reads_the_channel_for_a_type |
| AC2-P1 | Green | As expected | Pass (local, fakes) | commit 78b9cd4, local | Claude (AI) for Tate Lim, 27 Oct 2026 | test_email_delivery.py (parametrized AC2-P1/P2/P4) |
| AC2-P2 | Green | As expected | Pass (local, fakes) | commit 78b9cd4, local | Claude (AI) for Tate Lim, 27 Oct 2026 | as AC2-P1 |
| AC2-P4 | Green | As expected | Pass (local, fakes) | commit 78b9cd4, local | Claude (AI) for Tate Lim, 27 Oct 2026 | as AC2-P1; test_adapters.py::test_a_type_with_no_setting_is_in_app |
| AC2-X1 | Green | As expected | Pass (local, fakes) | commit 78b9cd4, local | Claude (AI) for Tate Lim, 27 Oct 2026 | test_email_delivery.py::test_a_setting_applies_to_its_own_type_only |
| AC3-H1 | Green | As expected | Pass (local, fakes) | commit 78b9cd4, local | Claude (AI) for Tate Lim, 27 Oct 2026 | test_email_delivery.py, test_adapters.py (SMTP message, address lookup, service wiring). Not run against live Auth or SMTP |
| AC3-N1 | Green | As expected | Pass (local, fakes) | commit 78b9cd4, local | Claude (AI) for Tate Lim, 27 Oct 2026 | test_email_delivery.py::test_a_mail_failure_keeps_the_notification_and_still_accepts |
| AC3-N2 | Green | As expected | Pass (local, fakes) | commit 78b9cd4, local | Claude (AI) for Tate Lim, 27 Oct 2026 | test_email_delivery.py::test_a_retried_event_sends_no_second_email |
| AC3-N4 | Green | As expected | Pass (local, fakes) | commit 78b9cd4, local | Claude (AI) for Tate Lim, 27 Oct 2026 | test_adapters.py::test_missing_mail_settings_do_not_break_the_action; test_the_unconfigured_mailer_refuses_to_send |
| AC3-P1 | Green | As expected | Pass (local, fakes) | commit 78b9cd4, local | Claude (AI) for Tate Lim, 27 Oct 2026 | test_email_delivery.py::test_the_same_event_id_emails_each_recipient_once |
| AC3-P3 | Green | As expected | Pass (local, fake SMTP) | commit 78b9cd4, local | Claude (AI) for Tate Lim, 27 Oct 2026 | test_adapters.py::test_smtp_mailer_skips_login_and_tls_when_not_configured |
| AC3-P4 | Green | As expected | Pass (local) | commit 78b9cd4, local | Claude (AI) for Tate Lim, 27 Oct 2026 | test_adapters.py::test_a_configured_host_selects_the_smtp_mailer |
| AC3-N5 | Green | As expected | Pass (local, fakes) | commit 78b9cd4, local | Claude (AI) for Tate Lim, 27 Oct 2026 | test_adapters.py::test_an_address_lookup_failure_is_raised |

Run on 1 November 2026 for AC1 (commit 6a406eb, local): `cd backend/eventRequestService && .venv/bin/python -m pytest -q` (1093 passed, 1 skipped) and `ruff check .` (one error, in `tests/test_registration_window_notifier.py`, a file this work did not touch; it appears without these changes too). `cd frontend && npx vitest run` (72 files, 619 tests passed), `npm run lint` (clean), `npm run typecheck` (exit 0). Dependencies faked: the repository, the notification service and its HTTP calls. Mutation checks: sending the notice for a refused cancellation fails AC1-N1 and AC1-B1; removing the client's failure handling fails AC1-N3. **Not run:** CI, a real cancellation against the running services and the shared database, the browser, and `npm run test:e2e`/`build`. AC1-N3 was not mutation-checked for the service call itself.

| ID | Automation status | Actual result | Execution status | Build or commit | Executed by and date | Remarks and evidence |
| --- | --- | --- | --- | --- | --- | --- |
| AC1-H1 | Green | As expected | Pass (local, fakes) | commit 9bb8aa5, local | Claude (AI) for Tate Lim, 1 Nov 2026 | test_cancellation_owner_notice.py::test_cancelling_tells_the_organiser_and_the_coordinator (Depends on A6, A7) |
| AC1-H2 | Green | As expected | Pass (local, fake HTTP) | commit 9bb8aa5, local | Claude (AI) for Tate Lim, 1 Nov 2026 | test_cancellation_owner_notice.py::test_the_client_posts_one_notice_per_recipient |
| AC1-P1 | Green | As expected | Pass (local, fakes) | commit c80428b, local | Claude (AI) for Tate Lim, 1 Nov 2026 | test_one_person_in_both_roles_is_told_once. Red first: two notices to one person |
| AC1-P2 | Green | As expected | Pass (local, fakes) | commit c80428b, local | Claude (AI) for Tate Lim, 1 Nov 2026 | test_no_attendees_still_tells_the_organiser_and_coordinator. Passed on first run (characterisation of H1) |
| AC1-X1 | Green | As expected | Pass (local, fakes) | commit c80428b, local | Claude (AI) for Tate Lim, 1 Nov 2026 | test_attendee_notices_are_unchanged; the SCRUM-38 AC4 tests also still pass |
| AC1-N1 | Green | As expected | Pass (local, fakes) | commit c80428b, local | Claude (AI) for Tate Lim, 1 Nov 2026 | test_refused_cancellation_tells_nobody (409 and 403). Mutation-checked |
| AC1-N2 | Green | As expected | Pass (local, fakes) | commit c80428b, local | Claude (AI) for Tate Lim, 1 Nov 2026 | test_coordinator_lookup_failure_still_tells_the_organiser. Red first: a saved cancellation answered `502` |
| AC1-N3 | Green | As expected | Pass (local, fake HTTP) | commit c80428b, local | Claude (AI) for Tate Lim, 1 Nov 2026 | test_notification_outage_does_not_block_the_cancellation. Client failure handling mutation-checked |
| AC1-B1 | Green | As expected | Pass (local, fakes) | commit c80428b, local | Claude (AI) for Tate Lim, 1 Nov 2026 | test_cancelling_twice_tells_nobody_twice. Mutation-checked |
| AC1-X2 | Green | As expected | Pass (local, vitest) | commit 6a406eb, local | Claude (AI) for Tate Lim, 1 Nov 2026 | frontend/__tests__/cancellation-recorded-notification.test.ts (3 tests). Not seen in a browser |
