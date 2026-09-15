# spm

## Commit messages

This repository uses [Conventional Commits](https://www.conventionalcommits.org/) for commit messages. GitHub Actions validates every commit pushed to the repository and every commit in a pull request:

```text
<type>(optional-scope): <description>
```

Examples include `feat: add user authentication`, `fix(api): handle empty responses`, and `feat!: remove the legacy endpoint`.

For earlier feedback before pushing, enable the version-controlled local Git hook once after cloning:

```powershell
./scripts/setup-git-hooks.ps1
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

## Services

| Service | Technology | Local port | Purpose |
| --- | --- | --- | --- |
| `authService` | FastAPI | `8001` | Authentication service scaffold |
| `eventRequestService` | FastAPI + Pydantic + Supabase | `8003` | Editable event-request drafts |

Start the services with Docker Compose:

```powershell
docker compose up --build
```

The event-request API documentation is available at
`http://localhost:8003/docs`. Event-request endpoints currently require an
`X-Organiser-Id` header until authentication integration is implemented.

The draft-request and operational-event ownership boundary is documented in
[`docs/event-domain-boundaries.md`](docs/event-domain-boundaries.md).
