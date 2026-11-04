# ConnectSphere (spm)

ConnectSphere supports the planning, coordination, resource allocation, registration and completion of organisational events.

**Repository:** <https://github.com/kenshoal/spm>

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

GitHub Actions runs these workflows from `.github/workflows/`:

| Workflow | Runs on | Checks |
| --- | --- | --- |
| Conventional Commits | Every push and pull request | Commit message format |
| Frontend CI | Pull requests and pushes to `dev` and `main` | Linting, type checking, production build, unit tests, Chromium end-to-end tests |
| Backend CI | Pull requests and pushes to `dev` and `main` that change backend, database or Compose files; can also be started by hand | Linting, tests and container builds for each service, plus database verifiers on disposable Postgres |
| Security | Pull requests and pushes to `main`, and weekly | Dependency vulnerability audits |

Dependabot checks Python packages, npm packages, and GitHub Actions weekly.

Run the frontend checks locally from `frontend/`:

```powershell
npm run lint
npm run typecheck
npm test
npm run test:e2e
npm run build
```

Run the backend checks locally from `backend/<service>/`:

```bash
python -m pip install -e ".[dev]"
ruff check .
pytest
```

## Documentation

| Topic | Location |
| --- | --- |
| Test cases and traceability, one file per story | [`docs/testcases/`](docs/testcases/) |
| Testing, commit, security and Done standards | [`docs/standards/`](docs/standards/) |
| Shared database rollout records | [`docs/deployment/`](docs/deployment/) |
| Migrations and database verifiers | [`database/README.md`](database/README.md) |

## Services

| Service | Technology | Local port | Purpose |
| --- | --- | --- | --- |
| `authService` | FastAPI + Supabase | `8001` | Registration, login, session verification and roles |
| `equipmentService` | FastAPI + Supabase | `8002` | Equipment catalogue, status, availability, requirements and reservations |
| `eventRequestService` | FastAPI + Pydantic + Supabase | `8003` | Event lifecycle, coordinator assignment, review, changes, registration, waiting list and technical support |
| `venueService` | FastAPI + Supabase | `8004` | Venue catalogue, search, suitability, availability, bookings, blocks and holds |
| `notificationService` | FastAPI + Supabase | `8005` | Stores workflow events from other services as in-app notifications and serves each user's inbox (SCRUM-37), with optional email per notification type (SCRUM-57) |

### Run the project from the repository root

Create the one shared, untracked environment file:

```bash
cp .env.example .env
```

Set `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, and the server-only
`SUPABASE_SECRET_KEY` in that root `.env`. Never commit this file.

Background features are set in the same file. `.env.example` lists them: automatic completion and registration-window notices are off by default, and the waiting-list timer is on.

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
