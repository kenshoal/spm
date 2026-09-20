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

Pull requests and pushes to `main` run frontend linting, type checking, a production build, unit tests, Chromium end-to-end tests, backend linting and tests, container builds, and dependency vulnerability audits. Dependabot checks Python packages, npm packages, and GitHub Actions weekly.

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
| `eventRequestService` | FastAPI + Pydantic + Supabase | `8003` | Event-request draft and submission workflow |
| `venueService` | FastAPI | `8004` | Venue catalogue and search |

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

Inspect logs or stop the backend stack from the root:

```bash
docker compose logs -f
docker compose down
```

Inside Compose, every API listens on port `8000`; the host ports above keep
the services distinct. Inter-service URLs use Compose service names, such as
`http://auth-service:8000`. Protected endpoints require a Supabase access
token in the `Authorization: Bearer` header.

The draft-request and operational-event ownership boundary is documented in
[`docs/event-domain-boundaries.md`](docs/event-domain-boundaries.md).
