# spm

## Commit messages

This repository uses [Conventional Commits](https://www.conventionalcommits.org/) for commit messages. GitHub Actions validates every commit pushed to the repository and every commit in a pull request:

```text
<type>(optional-scope): <description>
```

Examples include `feat: add user authentication`, `fix(api): handle empty responses`, and `feat!: remove the legacy endpoint`.

For earlier feedback before pushing, enable the version-controlled local Git hook once after cloning:

```bash
git config core.hooksPath .githooks
```

Allowed types are `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`, and `revert`.

## CI checks

Pull requests into `dev` or `main`, and pushes to either branch, run frontend linting, type checking, a production build, unit tests, Chromium end-to-end tests, backend linting and tests, container builds and the database verifiers. Backend CI runs when `backend/`, `database/` or `docker-compose.yaml` change. Dependency vulnerability audits run on `main` and weekly. Commit messages are checked on every branch. Dependabot checks Python packages, npm packages, and GitHub Actions weekly.

Run the frontend checks locally from `frontend/`:

```powershell
npm run lint
npm run typecheck
npm test
npm run test:e2e
npm run build
```

The purpose, layer and acceptance-criterion coverage of the SCRUM-8 tests are
documented in
[`docs/testcases/scrum_8_testcases.md`](docs/testcases/scrum_8_testcases.md).
Authentication coverage for SCRUM-26 is documented in
[`docs/testcases/scrum_26_testcases.md`](docs/testcases/scrum_26_testcases.md).
Submission coverage for SCRUM-11 is documented in
[`docs/testcases/scrum_11_testcases.md`](docs/testcases/scrum_11_testcases.md).

## Services

| Service | Technology | Local port | Purpose |
| --- | --- | --- | --- |
| `authService` | FastAPI | `8001` | Registration, login and session verification |
| `equipmentService` | FastAPI + Supabase | `8002` | Equipment catalogue, quantities and status |
| `eventRequestService` | FastAPI + Pydantic + Supabase | `8003` | Event-request drafts, submission, status and coordinator assignment |
| `venueService` | FastAPI | `8004` | Venue catalogue and search |
| `notificationService` | FastAPI + Supabase | `8005` | Stores workflow events from other services as in-app notifications and serves each user's inbox (SCRUM-37), with optional email per notification type (SCRUM-57) |

### First-time setup on a new Supabase project

Do this once, before "Run the project from the repository root" below. You need Docker, Node 22 and an empty Supabase project.

1. **Create the schema.** Apply every file in `database/migrations/` to the project, in filename order, and each one once. With the project's direct connection string (Supabase dashboard, Project Settings, Database) and `psql`:

   ```bash
   export SUPABASE_DB_URL='postgresql://postgres:<password>@db.<project-ref>.supabase.co:5432/postgres'
   for migration in $(ls database/migrations/*.sql | sort); do
     psql -X -v ON_ERROR_STOP=1 -q -d "$SUPABASE_DB_URL" -f "$migration"
   done
   ```

   Without `psql`, paste each file into the dashboard's SQL Editor in the same order ([`database/README.md`](database/README.md) lists what each file does). The migrations are not safe to re-run on a project that already has them. CI applies the same files in the same order to an empty PostgreSQL 16 database on every push; it has not been run for you against a real Supabase project.

2. **Configure and start the stack.** Create `.env` and run the backend and the frontend as described in the next section.

3. **Create the demo accounts.** With the stack running, register each account through authService, then give them roles:

   ```bash
   for name in admin attendee event_organiser event_organiser2 event_organiser3 \
               event_operations_manager event_coordinator1 event_coordinator2 \
               safety_officer technical_support venue_staff; do
     curl -s -X POST localhost:8001/auth/register \
       -H "Content-Type: application/json" \
       -d "{\"email\":\"$name@example.com\",\"password\":\"12345678\"}"
     echo
   done
   ```

   Then run [`database/seed_test_accounts.sql`](database/seed_test_accounts.sql) in the SQL Editor. It confirms the emails, assigns the roles and lists the result (expect 11 rows). Optionally run [`database/seed_technical_support_skills.sql`](database/seed_technical_support_skills.sql) for Technical Support skill tags. Development and test data only: never run either on production.

   | Role | Demo account (password `12345678`) | Lands on |
   | --- | --- | --- |
   | Event Organiser | `event_organiser@example.com` (also `event_organiser2@example.com`, same organisation; `event_organiser3@example.com`, another) | `/event-requests` |
   | Event Coordinator Lead | `event_operations_manager@example.com` | `/operations/assignments` |
   | Event Coordinator | `event_coordinator1@example.com` (and `event_coordinator2@example.com`, to test an unrelated coordinator) | `/coordination/requests` |
   | Safety Officer | `safety_officer@example.com` | `/safety` |
   | Venue Staff | `venue_staff@example.com` | `/venues` |
   | Technical Support | `technical_support@example.com` | `/equipment` |
   | Attendee | `attendee@example.com` | `/events` |
   | Admin | `admin@example.com` | no workspace (`/unauthorised`); admins change roles through authService (`PATCH /auth/users/{id}/role`) |

4. **Turn on the timers a full demo needs.** Four background features are switched by `.env` and some are off by default. Restart the stack after changing them.

   | Setting | Default | What it does |
   | --- | --- | --- |
   | `REGISTRATION_WINDOW_NOTICES_ENABLED` | `false` | Sends the "registration opens" and "registration closes" notices (SCRUM-38). Set `true` to see them. |
   | `AUTO_COMPLETION_ENABLED` | `false` | Completes events automatically after their final end (SCRUM-40). Needs migration 0063, which step 1 applied. |
   | `WAITLIST_TIMERS_ENABLED` | `true` | Waiting-list offer expiry and warnings (SCRUM-24). |
   | `SMTP_HOST` | empty | Email delivery. With it empty, notifications appear in the app only and no email is sent. |

### Run the project from the repository root

Create the one shared, untracked environment file:

```bash
cp .env.example .env
```

Set `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, and the server-only
`SUPABASE_SECRET_KEY` in that root `.env`. Never commit this file.

Build and start every backend microservice:

```bash
docker compose up --build -d
docker compose ps
```

Start the frontend from the same root in a second terminal:

```bash
npm --prefix frontend install
npm --prefix frontend run dev
```

Open the services at:

| Component | URL |
| --- | --- |
| Frontend | http://localhost:3000 |
| Auth API docs | http://localhost:8001/docs |
| Equipment API docs | http://localhost:8002/docs |
| Event-request API docs | http://localhost:8003/docs |
| Venue API docs | http://localhost:8004/docs |
| Notification API docs | http://localhost:8005/docs |

Inspect logs or stop the backend stack from the root:

```bash
docker compose logs -f
docker compose down
```

Inside Compose, every API listens on port `8000`; the host ports above keep
the services distinct. Inter-service URLs use Compose service names, such as
`http://auth-service:8000`. Protected endpoints require a Supabase access
token in the `Authorization: Bearer` header.
