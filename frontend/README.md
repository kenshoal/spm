This is the ConnectSphere frontend.

- **Organisers** (`/event-requests`) save incomplete drafts, submit a complete
  new request or saved draft, and track requests using All, Draft, Submitted,
  In Progress and Completed tabs. In Progress groups Under Review, Changes
  Requested, Approved, Planning and Confirmed; Cancelled and Rejected appear
  under All. Submitted requests are read-only, and the detail view shows a
  status progress display explaining the current stage.
- **Coordinators** (`/coordination/requests`) see only the requests currently
  assigned to them and open a read-only detail view. Actions depend on status:
  **Start review** (Submitted), **Cancel event** (any non-terminal status,
  confirmed first) and **Mark complete** (Confirmed, confirmed first).

Users with both roles see links to both workspaces.

Organiser and coordinator details show a read-only status timeline. Before rendering
status-dependent controls, the page compares the latest history entry with the event
status and retries both reads once if a transition occurred between them. If they
still disagree, it shows refresh guidance and withholds those controls. A history
outage keeps the event details available with an explicit unavailable message;
expired sessions still redirect to sign-in.

The timeline shows the latest five entries with a **Newest first** label.
**Show older activity** adds five more entries until the full history is visible;
the API keeps its complete chronological record. **Refresh status and history**
refreshes the whole detail view through the same server loader. Existing workflow
actions continue to refresh their detail pages after a successful change.

## Arrangement reviews (SCRUM-64)

The assigned coordinator's detail page streams an **Outstanding arrangement
reviews** panel with full recorded reasons, target/cause IDs and times. Domain
staff use `/arrangement-reviews?arrangement=venue_booking` (`venue_staff`) or
`arrangement=equipment_reservation` (`technical_support`). These are role-wide
queues; the full event ticket remains coordinator-only. Empty work and a failed
read have distinct messages, and **Refresh reviews** reloads the protected view.

Staff must tick **I have checked this arrangement against the recorded change**
before **Mark reviewed** submits the named review. The server action verifies the
current role and sends a bodyless clear request; the backend remains authoritative
for stale/domain refusals. This acknowledges that review only, preserves newer
causes and changes no booking, reservation or event status. The MVP shows UUID
references and recorded evidence, not a booking/reservation editor or independent
resource-availability validation.

The inbox renders `arrangement_needs_review` with its domain, target and complete
reason. Verified matching staff roles link to their domain queue, otherwise a
coordinator role links to the event detail. Links are constructed internally,
never taken from a payload URL. Protected destination APIs recheck access.

Run authService (8001), eventRequestService (8003) and notificationService (8005),
with the prepared migration stack, before `npm run dev`. Frontend server-only
`NOTIFICATION_API_URL` defaults to `http://127.0.0.1:8005`. Durable delivery also
requires the event service's `NOTIFICATION_SERVICE_URL`; see its README. Local
mocked browser checks do not prove shared Supabase delivery or real authentication.

## Workspaces

| Role | Lands on | Pages |
| --- | --- | --- |
| Event Organiser | `/event-requests` | create, edit, submit and track requests |
| Event Coordinator | `/coordination/requests` | assigned requests, status transitions, `/venues/search` |
| Event Coordinator Lead | `/operations/assignments` | assign and reassign coordinators (SCRUM-14, SCRUM-62). The role id is still `event_operations_manager`; users see "Event Coordinator Lead" |
| Venue Staff | `/venues` | venue catalogue (SCRUM-30), `/venues/search` (SCRUM-9), venue review queue |
| Technical Support | `/equipment` | equipment catalogue (SCRUM-45), status (SCRUM-16) and equipment review queue |
| Safety Officer | `/safety` | safety reviews of events in Safety Review (SCRUM-60) |
| Attendee | `/events` | browse Confirmed events and register (SCRUM-21) |

Venue search (`/venues/search`) is open to both Event Coordinators and Venue
Staff. A page-level fetch failure shows an "unavailable" banner instead of a
blank page, and an expired session redirects to sign-in rather than erroring.

Server-side environment variables: `AUTH_SERVICE_URL` (default `http://127.0.0.1:8001`),
`EVENT_REQUEST_API_URL` (8003), `VENUE_API_URL` (8004), `EQUIPMENT_API_URL` (8002).
`venueService` keeps venues in Supabase when `VENUE_STORAGE_BACKEND=supabase` (the Compose default) and in memory otherwise; in-memory venues are lost when it restarts.

## Getting Started

Start the event request service on port `8003`, then run the development server:

```bash
npm run dev
# or
yarn dev
# or
pnpm dev
# or
bun dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

The sign-up and login page is at [http://localhost:3000/auth](http://localhost:3000/auth).
Start authService on port `8001` (for example, `docker compose up auth-service`) or set
`AUTH_SERVICE_URL` for the Next.js server. If running authService directly with Uvicorn on
port `8000`, set `AUTH_SERVICE_URL=http://127.0.0.1:8000`. A successful login sets an
HTTP-only, same-site browser cookie for the access token and opens the protected
event-request area. Log out removes the local cookie; the session expires with
the access token (currently no automatic refresh).

The event-request API defaults to `http://127.0.0.1:8003`. Override it when needed:

```bash
EVENT_REQUEST_API_URL=http://127.0.0.1:8003 \
npm run dev
```

The Next.js server forwards the session token to eventRequestService. Never put
the Supabase secret key in frontend environment variables.

Run the frontend checks with:

```bash
npm test
npm run lint
npm run typecheck
npm run test:e2e
npm run build
```

The Playwright suite starts isolated auth and event-request APIs on ports `8104`
and `8103`, plus a frontend on `3100`. It exercises the browser workflow without
changing the shared Supabase project. The mock API has organiser, coordinator,
second-coordinator and Event Coordinator Lead sessions. `e2e/assign-coordinator.spec.ts`
assigns and reassigns a coordinator through the Lead's page.

You can start editing the page by modifying `app/page.tsx`. The page auto-updates as you edit the file.

This project uses [`next/font`](https://nextjs.org/docs/app/building-your-application/optimizing/fonts) to automatically optimize and load [Geist](https://vercel.com/font), a new font family for Vercel.

## Learn More

To learn more about Next.js, take a look at the following resources:

- [Next.js Documentation](https://nextjs.org/docs) - learn about Next.js features and API.
- [Learn Next.js](https://nextjs.org/learn) - an interactive Next.js tutorial.

You can check out [the Next.js GitHub repository](https://github.com/vercel/next.js) - your feedback and contributions are welcome!

## Deploy on Vercel

The easiest way to deploy your Next.js app is to use the [Vercel Platform](https://vercel.com/new?utm_medium=default-template&filter=next.js&utm_source=create-next-app&utm_campaign=create-next-app-readme) from the creators of Next.js.

Check out our [Next.js deployment documentation](https://nextjs.org/docs/app/building-your-application/deploying) for more details.
