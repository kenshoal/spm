# Sprint 1 Frontend Gaps Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every Sprint 1 user story whose backend is on `dev` a usable screen: Operations Manager assignment (SCRUM-14), venue search (SCRUM-9), venue catalogue (SCRUM-30), equipment catalogue (SCRUM-45) and equipment status (SCRUM-16).

**Architecture:** The Next.js 16 app router frontend gets three new role workspaces (`/operations`, `/venues`, `/equipment`) built the same way as the existing `/coordination` workspace: server components fetch with the session cookie's bearer token, and `"use server"` actions perform mutations and return `{ message }` state to `useActionState` client forms. Two small backend additions close gaps the UI cannot work around: authService lists users holding a role (the coordinator picker), and eventRequestService lists current assignments (reassignment discovery).

**Tech Stack:** Next.js 16.3 (app router, server actions), React 19.2, Tailwind 4, Vitest 5 + Testing Library, Playwright (Chromium, mock Node HTTP servers); FastAPI + pytest for the two backend tasks.

**Spec:** Jira Sprint 1 acceptance criteria, quoted in the "Spec (acceptance criteria)" section below; existing traceability in `docs/testcases/scrum_14_testcases.md`.

## Global Constraints

- Branch: `feat/frontend-sprint1-gaps`. Commits use Conventional Commits (`feat(frontend): …`, `feat(auth): …`, `feat(event-request): …`, `test(e2e): …`, `docs(…): …`) — `.githooks/commit-msg` and CI reject anything else.
- Every commit message ends with the line `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Next.js here is 16.3 and differs from training data. Before writing any Next API you have not seen in this repo, read the matching guide under `frontend/node_modules/next/dist/docs/`. Copy patterns from existing files: `params`/`searchParams` are `Promise`s; mutations are `"use server"` actions consumed with React's `useActionState`.
- A `"use server"` file may export only async functions (and types). Pure helpers used by tests go in `lib/`.
- **Never call `redirect()` inside a `try` block.** It throws `NEXT_REDIRECT`, which a surrounding `catch` swallows. Check `response.status === 401` *after* the `try/catch` that wraps `fetch`.
- Environment variables with defaults: `AUTH_SERVICE_URL` (`http://127.0.0.1:8001`), `EVENT_REQUEST_API_URL` (`http://127.0.0.1:8003`), `VENUE_API_URL` (`http://127.0.0.1:8004`), `EQUIPMENT_API_URL` (`http://127.0.0.1:8002`).
- Playwright mock ports: auth 8104, event-request 8103, venue **8105**, equipment **8106**, Next app 3100.
- Role strings (authService `Role` literal): `event_organiser`, `event_coordinator`, `event_operations_manager`, `venue_staff`, `technical_support`, `attendee`, `admin`.
- In Playwright specs, never use page-wide `getByRole("alert")` or `getByRole("status")`: Next.js injects a route announcer with `role="alert"`. Match by text or scope to a region/article.
- Every test gets a `// Purpose:` (TS) or `# Purpose:` (Python) comment above it, matching the existing suites.
- Visual style: reuse the Tailwind classes of the existing coordination pages (cards `rounded-2xl border border-[#dce4e0] bg-white`, primary button `bg-[#0f6b5b]`, alert `border-[#eccdbe] bg-[#fff8f3] text-[#793f27]`).
- Do not modify files outside the task's **Files** list except to fix a test the task's own change legitimately breaks (say so in the commit message).
- Out of scope: SCRUM-23 venue blocking (backend is only on unmerged `feat/venue-blocking`), notification delivery, persisting venues (venueService is in-memory).

## Commands

| What | Command (run from) |
| --- | --- |
| Frontend unit tests | `npm test` (`frontend/`) — one file: `npx vitest run __tests__/<file>` |
| Frontend types / lint | `npm run typecheck && npm run lint` (`frontend/`) |
| Frontend e2e | `npm run test:e2e` (`frontend/`) — one spec: `npx playwright test e2e/<spec>` (builds the app first, ~1–2 min) |
| authService | `.venv/bin/python -m pytest -q && .venv/bin/ruff check .` (`backend/authService/`) |
| eventRequestService | `.venv/bin/python -m pytest -q && .venv/bin/ruff check .` (`backend/eventRequestService/`) |

Baseline on 24 Sep 2026: frontend 53 unit tests passing, typecheck and lint clean; authService 38 passed; eventRequestService 157 passed.

## Spec (acceptance criteria)

**SCRUM-14 Assign an Event Coordinator** (Operations Manager): AC1 submitted requests awaiting assignment are visible to the Operations Manager · AC2 after submission the Operations Manager can assign one Event Coordinator · AC3 the event shows the assigned Coordinator and remains Submitted · AC4 review start moves it to Under Review (already built, coordinator side) · AC5 assigned Coordinator is notified (hook only; out of scope) · AC6 the event can be reassigned to a different Coordinator.

**SCRUM-9 Search and Filter Venues** (Event Coordinator): filter by date/slot, required capacity, location, accessibility, supported layout, required facilities · results match all applied filters, each showing key attributes · capacity filter N never shows a venue below N · blocked/unavailable venues excluded.

**SCRUM-30 Maintain the Venue Catalogue** (Venue Staff): create and update a venue with location, maximum capacity, facilities, accessibility, supported room layouts, operating hours · authorised users see current attributes · updates are reflected in search.

**SCRUM-45 Maintain the Equipment Catalogue** (Technical Support): create an equipment record with type, description, total owned quantity, home location, operational status · update total owned quantity · authorised users see current attributes.

**SCRUM-16 Maintain Equipment Status** (Technical Support): mark equipment unavailable (damaged, repair, maintenance) · such equipment is excluded from available quantity · each status change records who and when.

**SCRUM-27 Authorise Access by Role**: features available are determined by role; multi-role users get every workspace they hold.

## Review Focus

1. **Operations Manager signing in today lands on "Access unavailable".** After Task 3, login and `/` must route every staff role to its own workspace; a multi-role user must see a nav link to each workspace. Pinned by the `workspaceForRoles`/`workspaceLinks` tests in Task 3.
2. **Assigning with no coordinator chosen, or when no coordinators exist.** Must show "Choose a coordinator to assign." and never call the API; an empty coordinator list must render an explanation, not an empty `<select>`. Pinned in Task 4.
3. **Reassigning to the same coordinator.** The current coordinator must not be offered in the reassign picker. Pinned in Task 4.
4. **Non-numeric or zero numbers typed into capacity/quantity fields** (`"abc"`, `"0"`, `"12.5"`, `"-3"`). Venue capacity must be a whole number > 0, equipment quantity a whole number ≥ 0, venue search capacity a whole number > 0 — each reported inline without calling the API (the backend would 422). Pinned in Tasks 5, 6, 7.
5. **A comma list with blanks or duplicates** (`"Projector, , projector ,WiFi"`) must become `["Projector", "WiFi"]` — trimmed, blanks dropped, case-insensitive dedupe keeping first spelling. Pinned in Task 5 (`splitList`).

---

## File Structure

```
backend/authService/app/main.py                      # Task 1: GET /auth/users
backend/authService/tests/test_registration.py       # Task 1 tests
backend/eventRequestService/app/models/coordinator_assignment.py      # Task 2: CurrentAssignmentResponse
backend/eventRequestService/app/services/coordinator_assignment_service.py  # Task 2
backend/eventRequestService/app/controllers/coordinator_assignment_controller.py  # Task 2
backend/eventRequestService/tests/test_coordinator_assignment_controller.py  # Task 2 tests

frontend/lib/api.ts                  # Task 3: getJson / sendJson / readDetail
frontend/lib/auth.ts                 # Task 3: requireAnyRole, workspaceForRoles
frontend/app/components/app-shell.tsx  # Task 3: workspaceLinks
frontend/app/page.tsx                # Task 3: role-aware root redirect
frontend/app/unauthorised/page.tsx   # Task 3: role-neutral copy
frontend/e2e/support/auth-api.mjs    # Tasks 3, 4
frontend/lib/operations.ts           # Task 4
frontend/app/operations/**           # Task 4
frontend/e2e/support/event-request-api.mjs  # Task 4
frontend/lib/venues.ts, lib/venue-form.ts   # Tasks 5, 6
frontend/app/venues/**               # Tasks 5, 6
frontend/e2e/support/venue-api.mjs   # Tasks 5, 6
frontend/lib/equipment.ts, lib/equipment-form.ts  # Tasks 7, 8
frontend/app/equipment/**            # Tasks 7, 8
frontend/e2e/support/equipment-api.mjs  # Tasks 7, 8
frontend/playwright.config.ts        # Tasks 5, 7
docs/testcases/scrum_14_testcases.md, frontend/README.md  # Task 9
```

---

### Task 1: authService — list users holding a role

The assignment form needs real coordinator choices. `staff_roles` (migration 0010) is the role store; only admins (any role) and Operations Managers (only `event_coordinator`) may list.

**Files:**
- Modify: `backend/authService/app/main.py` (add model + endpoint after `update_user_role`)
- Test: `backend/authService/tests/test_registration.py` (append)

**Interfaces:**
- Produces: `GET /auth/users?role=<Role>` → `200 [{"id": str, "email": str | null}]` sorted by email then id; `401` no/invalid session; `403` caller not permitted; `422` unknown role; `502 {"detail": "Role store unavailable"}` on a `staff_roles` failure; `502 {"detail": "Authentication provider unavailable"}` on a non-404 provider failure. A `staff_roles` row whose user no longer exists (provider 404) is skipped.

- [ ] **Step 1: Write the failing tests** — append to `tests/test_registration.py`:

```python
def _caller(supabase: Mock, roles: list[str]) -> None:
    supabase.auth.get_user.return_value = SimpleNamespace(
        user=SimpleNamespace(
            id="caller-id", email="caller@example.com", app_metadata={"roles": roles}
        )
    )


COORDINATOR_EMAILS = {"coord-a": "alex@example.com", "coord-b": "blair@example.com"}


# Purpose: SCRUM-14 — an Operations Manager can list coordinators to choose from.
def test_operations_manager_lists_event_coordinators(
    client: TestClient, supabase: Mock, admin: Mock
) -> None:
    _caller(supabase, ["event_operations_manager"])
    admin.table.return_value.select.return_value.eq.return_value.execute.side_effect = [
        SimpleNamespace(data=[{"role": "event_operations_manager"}]),
        SimpleNamespace(data=[{"user_id": "coord-b"}, {"user_id": "coord-a"}]),
    ]
    admin.auth.admin.get_user_by_id.side_effect = lambda user_id: SimpleNamespace(
        user=SimpleNamespace(id=user_id, email=COORDINATOR_EMAILS[user_id])
    )

    response = client.get(
        "/auth/users?role=event_coordinator",
        headers={"Authorization": "Bearer manager-token"},
    )

    assert response.status_code == 200
    assert response.json() == [
        {"id": "coord-a", "email": "alex@example.com"},
        {"id": "coord-b", "email": "blair@example.com"},
    ]
    admin.table.return_value.select.return_value.eq.assert_called_with(
        "role", "event_coordinator"
    )


# Purpose: An Operations Manager may list coordinators only, not other staff roles.
def test_operations_manager_cannot_list_other_roles(
    client: TestClient, supabase: Mock, admin: Mock
) -> None:
    _caller(supabase, ["event_operations_manager"])
    admin.table.return_value.select.return_value.eq.return_value.execute.return_value = (
        SimpleNamespace(data=[{"role": "event_operations_manager"}])
    )

    response = client.get(
        "/auth/users?role=venue_staff",
        headers={"Authorization": "Bearer manager-token"},
    )

    assert response.status_code == 403


# Purpose: An admin may list the holders of any role.
def test_admin_lists_any_role(client: TestClient, supabase: Mock, admin: Mock) -> None:
    _caller(supabase, ["admin"])
    admin.table.return_value.select.return_value.eq.return_value.execute.side_effect = [
        SimpleNamespace(data=[{"role": "admin"}]),
        SimpleNamespace(data=[{"user_id": "venue-1"}]),
    ]
    admin.auth.admin.get_user_by_id.return_value = SimpleNamespace(
        user=SimpleNamespace(id="venue-1", email="venue@example.com")
    )

    response = client.get(
        "/auth/users?role=venue_staff", headers={"Authorization": "Bearer admin-token"}
    )

    assert response.status_code == 200
    assert response.json() == [{"id": "venue-1", "email": "venue@example.com"}]


# Purpose: Roles without assignment duties cannot enumerate staff.
def test_organiser_cannot_list_users(
    client: TestClient, supabase: Mock, admin: Mock
) -> None:
    _caller(supabase, ["event_organiser"])
    admin.table.return_value.select.return_value.eq.return_value.execute.return_value = (
        SimpleNamespace(data=[{"role": "event_organiser"}])
    )

    response = client.get(
        "/auth/users?role=event_coordinator",
        headers={"Authorization": "Bearer organiser-token"},
    )

    assert response.status_code == 403


# Purpose: Listing staff requires a session.
def test_list_users_requires_authentication(
    client: TestClient, supabase: Mock, admin: Mock
) -> None:
    response = client.get("/auth/users?role=event_coordinator")

    assert response.status_code == 401


# Purpose: A role row left behind by a deleted account does not break the picker.
def test_list_users_skips_deleted_accounts(
    client: TestClient, supabase: Mock, admin: Mock
) -> None:
    _caller(supabase, ["event_operations_manager"])
    admin.table.return_value.select.return_value.eq.return_value.execute.side_effect = [
        SimpleNamespace(data=[{"role": "event_operations_manager"}]),
        SimpleNamespace(data=[{"user_id": "gone"}, {"user_id": "coord-a"}]),
    ]

    def get_user(user_id: str) -> SimpleNamespace:
        if user_id == "gone":
            raise AuthApiError("user not found", 404, "user_not_found")
        return SimpleNamespace(user=SimpleNamespace(id=user_id, email="alex@example.com"))

    admin.auth.admin.get_user_by_id.side_effect = get_user

    response = client.get(
        "/auth/users?role=event_coordinator",
        headers={"Authorization": "Bearer manager-token"},
    )

    assert response.status_code == 200
    assert response.json() == [{"id": "coord-a", "email": "alex@example.com"}]


# Purpose: A role-store outage is reported as a gateway failure, not an empty list.
def test_list_users_maps_role_store_failure(
    client: TestClient, supabase: Mock, admin: Mock
) -> None:
    _caller(supabase, ["event_operations_manager"])
    admin.table.return_value.select.return_value.eq.return_value.execute.side_effect = [
        SimpleNamespace(data=[{"role": "event_operations_manager"}]),
        APIError({"message": "offline", "code": "PGRST000", "hint": None, "details": None}),
    ]

    response = client.get(
        "/auth/users?role=event_coordinator",
        headers={"Authorization": "Bearer manager-token"},
    )

    assert response.status_code == 502
    assert response.json() == {"detail": "Role store unavailable"}
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd backend/authService && .venv/bin/python -m pytest tests/test_registration.py -q -k "list_users or lists_ or cannot_list"`
Expected: FAIL — `404 Not Found` for `/auth/users` (7 failures).

- [ ] **Step 3: Implement** — in `app/main.py`, add after `RoleUpdateResponse`:

```python
class UserSummary(BaseModel):
    id: str
    email: str | None
```

and after the `update_user_role` function:

```python
@app.get("/auth/users", response_model=list[UserSummary], tags=["auth"])
def list_users_by_role(
    role: Role,
    supabase: Annotated[Client, Depends(get_supabase_client)],
    admin_client: Annotated[Client, Depends(get_admin_client)],
    authorization: Annotated[str | None, Header()] = None,
) -> list[UserSummary]:
    caller = _verify_bearer(supabase, authorization)
    caller_roles = _staff_roles_of(caller, admin_client)
    can_list_any = ADMIN_ROLE in caller_roles
    can_list_coordinators = EVENT_OPERATIONS_MANAGER_ROLE in caller_roles
    if not can_list_any and not (
        can_list_coordinators and role == "event_coordinator"
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permissions")

    try:
        rows = (
            admin_client.table("staff_roles")
            .select("user_id")
            .eq("role", role)
            .execute()
            .data
        )
    except APIError as error:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, "Role store unavailable"
        ) from error

    user_ids = sorted(
        {row["user_id"] for row in rows if isinstance(row.get("user_id"), str)}
    )
    users: list[UserSummary] = []
    for user_id in user_ids:
        try:
            found = admin_client.auth.admin.get_user_by_id(user_id).user
        except AuthApiError as error:
            if error.status == status.HTTP_404_NOT_FOUND:
                continue  # A role row outlived its account; nothing to offer.
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY, "Authentication provider unavailable"
            ) from error
        except AuthError as error:
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY, "Authentication provider unavailable"
            ) from error
        if found is not None:
            users.append(UserSummary(id=found.id, email=found.email))
    return sorted(users, key=lambda user: (user.email or "", user.id))
```

- [ ] **Step 4: Run to verify they pass, plus the whole suite and lint**

Run: `.venv/bin/python -m pytest -q && .venv/bin/ruff check .`
Expected: `45 passed`; `All checks passed!`

- [ ] **Step 5: Commit**

```bash
git add backend/authService/app/main.py backend/authService/tests/test_registration.py
git commit -m "feat(auth): list users holding a role for assignment pickers

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: eventRequestService — list current coordinator assignments

The awaiting queue drops a request once it is assigned, so a manager cannot find it to reassign (the "Discovery gap" in `scrum_14_testcases.md` AC6). Add an Operations-Manager-only list of in-flight requests with their current coordinator.

**Files:**
- Modify: `backend/eventRequestService/app/models/coordinator_assignment.py`
- Modify: `backend/eventRequestService/app/services/coordinator_assignment_service.py`
- Modify: `backend/eventRequestService/app/controllers/coordinator_assignment_controller.py`
- Test: `backend/eventRequestService/tests/test_coordinator_assignment_controller.py` (append); `tests/test_coordinator_assignment_service.py` (append)

**Interfaces:**
- Produces: `GET /event-requests/assignments` → `200 [{"event_request": EventRequestResponse, "assignment": CoordinatorAssignmentResponse}]`, newest request first; only requests whose status is Submitted, Under Review, Changes Requested, Approved, Planning or Confirmed **and** that have at least one assignment; `assignment` is the highest-`id` row. `403` for callers without `event_operations_manager`.

- [ ] **Step 1: Write the failing tests** — append to `tests/test_coordinator_assignment_controller.py`:

```python
# Purpose: SCRUM-14 AC6 — a manager can find assigned requests to reassign them,
# and sees the latest Coordinator rather than the first.
def test_current_assignments_list_the_latest_coordinator_per_request() -> None:
    event_requests = FakeEventRequestRepository()
    with make_client(event_requests) as client:
        assigned_id = submit_event_request(event_requests)
        submit_event_request(event_requests)  # never assigned
        for coordinator_id in ("coord-1", "coord-2"):
            client.post(
                f"/event-requests/{assigned_id}/coordinator",
                headers=headers(),
                json={"coordinator_id": coordinator_id},
            )
        response = client.get("/event-requests/assignments", headers=headers())

    assert response.status_code == 200
    body = response.json()
    assert [row["event_request"]["id"] for row in body] == [assigned_id]
    assert body[0]["assignment"]["coordinator_id"] == "coord-2"


# Purpose: Closed requests cannot be reassigned, so they are not offered.
def test_current_assignments_exclude_terminal_requests() -> None:
    event_requests = FakeEventRequestRepository()
    with make_client(event_requests) as client:
        closed_id = submit_event_request(event_requests)
        client.post(
            f"/event-requests/{closed_id}/coordinator",
            headers=headers(),
            json={"coordinator_id": "coord-1"},
        )
        event_requests.rows[closed_id]["status"] = "Cancelled"
        response = client.get("/event-requests/assignments", headers=headers())

    assert response.status_code == 200
    assert response.json() == []


# Purpose: Requests keep appearing once review has started, so they stay reassignable.
def test_current_assignments_include_requests_under_review() -> None:
    event_requests = FakeEventRequestRepository()
    with make_client(event_requests) as client:
        request_id = submit_event_request(event_requests)
        client.post(
            f"/event-requests/{request_id}/coordinator",
            headers=headers(),
            json={"coordinator_id": "coord-1"},
        )
        event_requests.rows[request_id]["status"] = "Under Review"
        response = client.get("/event-requests/assignments", headers=headers())

    assert [row["event_request"]["id"] for row in response.json()] == [request_id]


# Purpose: The assignment overview is closed to non-Operations Manager callers.
def test_current_assignments_require_operations_manager_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_test")
    monkeypatch.setattr(
        httpx,
        "get",
        lambda *args, **kwargs: httpx.Response(
            200,
            json={
                "id": str(uuid4()),
                "email": None,
                "role": "event_coordinator",
                "roles": ["event_coordinator"],
            },
        ),
    )
    from app.config import get_settings

    get_settings.cache_clear()
    try:
        app = create_app(
            FakeEventRequestRepository(), FakeCoordinatorAssignmentRepository()
        )
        with TestClient(app) as client:
            response = client.get(
                "/event-requests/assignments",
                headers={"Authorization": "Bearer valid-token"},
            )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 403
```

Append to `tests/test_coordinator_assignment_service.py`:

```python
# Purpose: With no in-flight requests there is nothing to look up in the assignments table.
def test_current_assignments_skip_the_assignment_lookup_when_nothing_in_flight() -> None:
    class ExplodingAssignmentRepository(FakeCoordinatorAssignmentRepository):
        def list_for_event_requests(
            self, event_request_ids: list[str]
        ) -> list[dict[str, Any]]:
            raise AssertionError("no in-flight requests means nothing to look up")

    service = CoordinatorAssignmentService(
        ExplodingAssignmentRepository(),
        EventRequestService(FakeEventRequestRepository()),
    )

    assert service.list_current_assignments() == []
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd backend/eventRequestService && .venv/bin/python -m pytest -q -k current_assignments`
Expected: FAIL — 404 for the route; `AttributeError: ... has no attribute 'list_current_assignments'`.

- [ ] **Step 3: Implement**

`app/models/coordinator_assignment.py` — add the import at the top and the model at the bottom:

```python
from app.models.event_request import EventRequestResponse
```

```python
class CurrentAssignmentResponse(BaseModel):
    event_request: EventRequestResponse
    assignment: CoordinatorAssignmentResponse
```

`app/services/coordinator_assignment_service.py` — import `CurrentAssignmentResponse` alongside the existing model imports, add below `_TERMINAL_STATUSES`:

```python
# Statuses in which a request has (or awaits) a responsible Coordinator and
# can still be reassigned — everything after submission and before closure.
_IN_FLIGHT_STATUSES = (
    EventRequestStatus.SUBMITTED,
    EventRequestStatus.UNDER_REVIEW,
    EventRequestStatus.CHANGES_REQUESTED,
    EventRequestStatus.APPROVED,
    EventRequestStatus.PLANNING,
    EventRequestStatus.CONFIRMED,
)
```

and add the method to `CoordinatorAssignmentService`, after `list_awaiting_assignment`:

```python
    def list_current_assignments(self) -> list[CurrentAssignmentResponse]:
        """In-flight requests that have a Coordinator, with the current one —
        what an Operations Manager needs to find a request to reassign."""
        in_flight = [
            request
            for status in _IN_FLIGHT_STATUSES
            for request in self.event_request_service.list_by_status(status)
        ]
        if not in_flight:
            return []

        latest: dict[str, dict[str, Any]] = {}
        for row in self.repository.list_for_event_requests(
            [request.id for request in in_flight]
        ):
            request_id = row["event_request_id"]
            if request_id not in latest or int(row["id"]) > int(
                latest[request_id]["id"]
            ):
                latest[request_id] = row

        current = [
            CurrentAssignmentResponse(
                event_request=request,
                assignment=CoordinatorAssignmentResponse.model_validate(
                    latest[request.id]
                ),
            )
            for request in in_flight
            if request.id in latest
        ]
        return sorted(
            current, key=lambda item: item.event_request.created_at, reverse=True
        )
```

`app/controllers/coordinator_assignment_controller.py` — import `CurrentAssignmentResponse` with the other model imports and add after `list_awaiting_assignment`:

```python
@router.get(
    "/assignments",
    response_model=list[CurrentAssignmentResponse],
)
def list_current_assignments(
    _assigned_by: OperationsManagerDependency,
    service: ServiceDependency,
) -> list[CurrentAssignmentResponse]:
    return service.list_current_assignments()
```

- [ ] **Step 4: Run the whole suite and lint**

Run: `.venv/bin/python -m pytest -q && .venv/bin/ruff check .`
Expected: `162 passed`; `All checks passed!`

- [ ] **Step 5: Commit**

```bash
git add backend/eventRequestService/app backend/eventRequestService/tests
git commit -m "feat(event-request): list current coordinator assignments for reassignment

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Frontend — role-aware routing, navigation and API helpers

**Files:**
- Create: `frontend/lib/api.ts`
- Modify: `frontend/lib/auth.ts`, `frontend/app/components/app-shell.tsx`, `frontend/app/page.tsx`, `frontend/app/unauthorised/page.tsx`, `frontend/e2e/support/auth-api.mjs`, `frontend/e2e/auth.spec.ts` (heading text only)
- Test: `frontend/__tests__/auth.test.tsx` (extend the workspace test), create `frontend/__tests__/api.test.ts`, create `frontend/__tests__/workspace-links.test.ts`

**Interfaces:**
- Produces (`lib/api.ts`):
  - `getJson<T>(baseUrl: string, path: string): Promise<T | null>` — GET with bearer token, `cache: "no-store"`; `401` → `redirect("/auth")`; `404` → `null`; other non-2xx → throws `Error`.
  - `sendJson(baseUrl: string, path: string, method: "POST" | "PATCH", body: unknown): Promise<Response>` — adds bearer + JSON content type; **does not redirect** (callers check 401 after their `try/catch`).
  - `readDetail(response: Response): Promise<string | null>` — FastAPI `detail` string or `null`.
- Produces (`lib/auth.ts`): `requireAnyRole(roles: readonly string[]): Promise<AuthenticatedUser>`; `workspaceForRoles` now returns `/event-requests`, `/coordination/requests`, `/operations/assignments`, `/venues`, `/equipment` (that priority), else `/unauthorised`.
- Produces (`app-shell.tsx`): `workspaceLinks(roles)` adds `{ "/operations/assignments", "Assignments" }`, `{ "/venues/search", "Venue search" }` (coordinator or venue staff, once), `{ "/venues", "Venues" }` (venue staff), `{ "/equipment", "Equipment" }` (technical support).
- Produces (e2e): sessions `venue-session` (`playwright-venue`, `venue_staff`) and `tech-session` (`playwright-tech`, `technical_support`); logins `ops@example.com`, `venue@example.com`, `tech@example.com` with password `test-password-123`.

- [ ] **Step 1: Write the failing tests**

In `__tests__/auth.test.tsx`, replace the body of the test `"selects the default workspace from verified roles"` with:

```tsx
  expect(workspaceForRoles(["event_coordinator", "event_organiser"])).toBe("/event-requests");
  expect(workspaceForRoles(["event_coordinator"])).toBe("/coordination/requests");
  expect(workspaceForRoles(["event_operations_manager"])).toBe("/operations/assignments");
  expect(workspaceForRoles(["venue_staff"])).toBe("/venues");
  expect(workspaceForRoles(["technical_support"])).toBe("/equipment");
  expect(workspaceForRoles(["attendee"])).toBe("/unauthorised");
```

Create `__tests__/workspace-links.test.ts`:

```ts
import { expect, test, vi } from "vitest";

vi.mock("@/app/auth/actions", () => ({ logout: vi.fn() }));

import { workspaceLinks } from "@/app/components/app-shell";

// Purpose: SCRUM-27 — each staff role sees the workspace it can use.
test("links each role to its own workspace", () => {
  expect(workspaceLinks(["event_operations_manager"])).toEqual([
    { href: "/operations/assignments", label: "Assignments" },
  ]);
  expect(workspaceLinks(["technical_support"])).toEqual([
    { href: "/equipment", label: "Equipment" },
  ]);
  expect(workspaceLinks(["venue_staff"])).toEqual([
    { href: "/venues", label: "Venues" },
    { href: "/venues/search", label: "Venue search" },
  ]);
  expect(workspaceLinks(["attendee"])).toEqual([]);
});

// Purpose: SCRUM-27 — a multi-role user sees every workspace, each exactly once.
test("gives a multi-role user one link per workspace", () => {
  expect(workspaceLinks(["event_coordinator", "venue_staff"])).toEqual([
    { href: "/coordination/requests", label: "Coordination" },
    { href: "/venues", label: "Venues" },
    { href: "/venues/search", label: "Venue search" },
  ]);
});
```

Create `__tests__/api.test.ts`:

```ts
import { beforeEach, expect, test, vi } from "vitest";

const navigation = vi.hoisted(() => ({ redirect: vi.fn() }));
vi.mock("next/navigation", () => ({ redirect: navigation.redirect }));
vi.mock("@/lib/auth", () => ({ requireAccessToken: async () => "valid-token" }));

import { getJson, readDetail, sendJson } from "@/lib/api";

beforeEach(() => {
  vi.restoreAllMocks();
  navigation.redirect.mockReset();
});

// Purpose: Reads carry the session token and are never cached across users.
test("getJson sends the bearer token and parses the body", async () => {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => [{ id: "v1" }],
  });
  vi.stubGlobal("fetch", fetchMock);

  await expect(getJson("http://svc", "/venues")).resolves.toEqual([{ id: "v1" }]);
  expect(fetchMock).toHaveBeenCalledWith("http://svc/venues", {
    headers: { Authorization: "Bearer valid-token" },
    cache: "no-store",
  });
});

// Purpose: A missing record is a normal outcome the page renders, not a crash.
test("getJson returns null for 404", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 404 }));

  await expect(getJson("http://svc", "/venues/x")).resolves.toBeNull();
});

// Purpose: An expired session goes to sign-in rather than an error page.
test("getJson redirects to sign-in on 401", async () => {
  navigation.redirect.mockImplementation(() => {
    throw new Error("NEXT_REDIRECT");
  });
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 401 }));

  await expect(getJson("http://svc", "/venues")).rejects.toThrow("NEXT_REDIRECT");
  expect(navigation.redirect).toHaveBeenCalledWith("/auth");
});

// Purpose: Other failures surface so the page can show "service unavailable".
test("getJson throws on server errors", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 500 }));

  await expect(getJson("http://svc", "/venues")).rejects.toThrow();
});

// Purpose: Writes send JSON with the token and leave status handling to the caller.
test("sendJson posts JSON without redirecting", async () => {
  const fetchMock = vi.fn().mockResolvedValue({ ok: false, status: 401 });
  vi.stubGlobal("fetch", fetchMock);

  const response = await sendJson("http://svc", "/venues", "POST", { name: "Hall" });

  expect(response.status).toBe(401);
  expect(navigation.redirect).not.toHaveBeenCalled();
  expect(fetchMock).toHaveBeenCalledWith("http://svc/venues", {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: "Bearer valid-token" },
    body: JSON.stringify({ name: "Hall" }),
  });
});

// Purpose: Backend explanations reach the user only when they are plain strings.
test("readDetail extracts a string detail and tolerates anything else", async () => {
  await expect(readDetail({ json: async () => ({ detail: "No." }) } as Response)).resolves.toBe("No.");
  await expect(readDetail({ json: async () => ({ detail: [{ msg: "x" }] }) } as Response)).resolves.toBeNull();
  await expect(readDetail({ json: async () => { throw new Error("bad"); } } as unknown as Response)).resolves.toBeNull();
});
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd frontend && npx vitest run __tests__/auth.test.tsx __tests__/workspace-links.test.ts __tests__/api.test.ts`
Expected: FAIL — `/operations/assignments` expected but got `/unauthorised`; cannot resolve `@/lib/api`.

- [ ] **Step 3: Implement**

Create `frontend/lib/api.ts`:

```ts
import { redirect } from "next/navigation";
import { requireAccessToken } from "./auth";

// Reads a JSON resource for a server component. A 404 is a normal "not found"
// outcome (null); any other failure throws so the page can show an outage.
export async function getJson<T>(baseUrl: string, path: string): Promise<T | null> {
  const token = await requireAccessToken();
  const response = await fetch(`${baseUrl}${path}`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });
  if (response.status === 401) redirect("/auth");
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(`${path} failed with status ${response.status}`);
  return response.json() as Promise<T>;
}

// Sends a JSON write for a server action. It never redirects: callers wrap it
// in try/catch for network failures, and redirect() inside that try would be
// swallowed — so the caller checks 401 after the try.
export async function sendJson(
  baseUrl: string,
  path: string,
  method: "POST" | "PATCH",
  body: unknown,
): Promise<Response> {
  const token = await requireAccessToken();
  return fetch(`${baseUrl}${path}`, {
    method,
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify(body),
  });
}

export async function readDetail(response: Response): Promise<string | null> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    return typeof body.detail === "string" ? body.detail : null;
  } catch {
    return null;
  }
}
```

In `frontend/lib/auth.ts`, replace `workspaceForRoles` and add `requireAnyRole` after `requireRole`:

```ts
export function workspaceForRoles(roles: string[]): string {
  if (roles.includes("event_organiser")) return "/event-requests";
  if (roles.includes("event_coordinator")) return "/coordination/requests";
  if (roles.includes("event_operations_manager")) return "/operations/assignments";
  if (roles.includes("venue_staff")) return "/venues";
  if (roles.includes("technical_support")) return "/equipment";
  return "/unauthorised";
}
```

```ts
export async function requireAnyRole(roles: readonly string[]): Promise<AuthenticatedUser> {
  const user = await requireAuthenticatedUser();
  if (!roles.some((role) => user.roles.includes(role))) redirect("/unauthorised");
  return user;
}
```

In `frontend/app/components/app-shell.tsx`, replace `workspaceLinks`:

```ts
export function workspaceLinks(roles: string[]): NavLink[] {
  const links: NavLink[] = [];
  if (roles.includes("event_organiser")) {
    links.push({ href: "/event-requests", label: "My event requests" });
  }
  if (roles.includes("event_coordinator")) {
    links.push({ href: "/coordination/requests", label: "Coordination" });
  }
  if (roles.includes("event_operations_manager")) {
    links.push({ href: "/operations/assignments", label: "Assignments" });
  }
  if (roles.includes("venue_staff")) {
    links.push({ href: "/venues", label: "Venues" });
  }
  if (roles.includes("event_coordinator") || roles.includes("venue_staff")) {
    links.push({ href: "/venues/search", label: "Venue search" });
  }
  if (roles.includes("technical_support")) {
    links.push({ href: "/equipment", label: "Equipment" });
  }
  return links;
}
```

Also change the logo link fallback in `AppShell` from `"/event-requests"` to `"/"` (so a role without links is routed by `app/page.tsx`).

Replace `frontend/app/page.tsx`:

```tsx
import { redirect } from "next/navigation";
import { requireAuthenticatedUser, workspaceForRoles } from "@/lib/auth";

export default async function HomePage() {
  const user = await requireAuthenticatedUser();
  redirect(workspaceForRoles(user.roles));
}
```

In `frontend/app/unauthorised/page.tsx`, change the `<h1>` text to `Your role can't use this page` and the paragraph to: `Your account is signed in, but none of its roles give access to this page. Contact an administrator if you need access.` In `frontend/e2e/auth.spec.ts` line 43 change the expected heading to `"Your role can't use this page"`.

In `frontend/e2e/support/auth-api.mjs`, add inside the `/auth/me` handler (before the final 401):

```js
    if (request.headers.authorization === "Bearer venue-session") {
      send(response, 200, { id: "playwright-venue", email: "venue@example.com", role: "venue_staff", roles: ["venue_staff"] });
      return;
    }
    if (request.headers.authorization === "Bearer tech-session") {
      send(response, 200, { id: "playwright-tech", email: "tech@example.com", role: "technical_support", roles: ["technical_support"] });
      return;
    }
```

and replace the login token selection with a lookup:

```js
    const LOGINS = {
      "playwright@example.com": "test-session",
      "coordinator@example.com": "coordinator-session",
      "ops@example.com": "ops-session",
      "venue@example.com": "venue-session",
      "tech@example.com": "tech-session",
    };
    const token = credentials.password === "test-password-123" ? LOGINS[credentials.email] ?? null : null;
```

- [ ] **Step 4: Run unit tests, typecheck, lint, then the existing e2e suite**

Run: `npm test && npm run typecheck && npm run lint && npm run test:e2e`
Expected: all unit tests pass (53 + 8 new = 61); typecheck/lint clean; all existing e2e specs pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/lib frontend/app/components/app-shell.tsx frontend/app/page.tsx frontend/app/unauthorised/page.tsx frontend/e2e frontend/__tests__
git commit -m "feat(frontend): route every staff role to its own workspace

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: SCRUM-14 — Operations Manager assignment workspace

**Files:**
- Create: `frontend/lib/operations.ts`
- Create: `frontend/app/operations/layout.tsx`, `frontend/app/operations/actions.ts`, `frontend/app/operations/assignments/page.tsx`, `frontend/app/operations/assignments/assignment-lists.tsx`, `frontend/app/operations/assignments/assign-coordinator-form.tsx`
- Modify: `frontend/e2e/support/event-request-api.mjs`, `frontend/e2e/support/auth-api.mjs`
- Test: create `frontend/__tests__/operations-actions.test.ts`, `frontend/__tests__/operations.test.tsx`, `frontend/e2e/assign-coordinator.spec.ts`

**Interfaces:**
- Consumes: `getJson`, `sendJson`, `readDetail` (Task 3); `requireRole`, `workspaceLinks`; `EventRequest`, `formatDateTime`, `statusBadgeClass` from `lib/event-requests.ts`; backend endpoints from Tasks 1–2 and the existing `POST /event-requests/{id}/coordinator`.
- Produces (`lib/operations.ts`): types `CoordinatorAssignment`, `CurrentAssignment`, `CoordinatorOption`; `listAwaitingAssignment(): Promise<EventRequest[]>`, `listCurrentAssignments(): Promise<CurrentAssignment[]>`, `listCoordinators(): Promise<CoordinatorOption[]>`, `coordinatorLabel(id: string, coordinators: CoordinatorOption[]): string`.
- Produces (`app/operations/actions.ts`): `assignCoordinator(eventRequestId: string, previousState: AssignState, formData: FormData): Promise<AssignState>` where `AssignState = { message?: string; assigned?: boolean }`.

- [ ] **Step 1: Write the failing unit tests**

Create `__tests__/operations-actions.test.ts`:

```ts
import { beforeEach, expect, test, vi } from "vitest";

const navigation = vi.hoisted(() => ({ redirect: vi.fn(), revalidatePath: vi.fn() }));
vi.mock("next/navigation", () => ({ redirect: navigation.redirect }));
vi.mock("next/cache", () => ({ revalidatePath: navigation.revalidatePath }));
vi.mock("@/lib/auth", () => ({
  requireAccessToken: async () => "valid-token",
  requireRole: async () => ({ id: "ops-1", email: "ops@example.com", role: "event_operations_manager", roles: ["event_operations_manager"] }),
}));

import { assignCoordinator } from "@/app/operations/actions";

function form(coordinatorId: string): FormData {
  const data = new FormData();
  data.set("coordinator_id", coordinatorId);
  return data;
}

beforeEach(() => {
  vi.restoreAllMocks();
  navigation.redirect.mockReset();
  navigation.revalidatePath.mockReset();
});

// Purpose: SCRUM-14 AC2 — assigning posts the chosen coordinator for that request.
test("assigns the chosen coordinator through the event request API", async () => {
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 201 });
  vi.stubGlobal("fetch", fetchMock);

  const state = await assignCoordinator("request/1", {}, form("coord-1"));

  expect(fetchMock.mock.calls[0][0]).toBe("http://127.0.0.1:8003/event-requests/request%2F1/coordinator");
  expect(fetchMock.mock.calls[0][1]).toMatchObject({
    method: "POST",
    body: JSON.stringify({ coordinator_id: "coord-1" }),
  });
  expect(state).toEqual({ assigned: true, message: "Coordinator assigned." });
  expect(navigation.revalidatePath).toHaveBeenCalledWith("/operations/assignments");
});

// Purpose: Submitting without a choice is caught before any request is sent.
test("requires a coordinator to be chosen", async () => {
  const fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);

  const state = await assignCoordinator("request-1", {}, form("  "));

  expect(state).toEqual({ message: "Choose a coordinator to assign." });
  expect(fetchMock).not.toHaveBeenCalled();
});

// Purpose: The backend's reason for refusing (terminal status, not a coordinator) is shown.
test("shows the backend's reason when assignment is refused", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
    ok: false,
    status: 409,
    json: async () => ({ detail: "The selected user is not an Event Coordinator" }),
  }));

  const state = await assignCoordinator("request-1", {}, form("coord-1"));

  expect(state).toEqual({ message: "The selected user is not an Event Coordinator" });
  expect(navigation.revalidatePath).not.toHaveBeenCalled();
});

// Purpose: A request deleted or closed since the page loaded is explained.
test("explains a request that no longer exists", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 404 }));

  const state = await assignCoordinator("request-1", {}, form("coord-1"));

  expect(state).toEqual({ message: "This request no longer exists. Refresh the page." });
});

// Purpose: An unreachable API leaves the manager on the page with a retryable error.
test("returns a retryable error when the API cannot be reached", async () => {
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));

  const state = await assignCoordinator("request-1", {}, form("coord-1"));

  expect(state).toEqual({ message: "The coordinator could not be assigned. Please try again." });
});

// Purpose: An expired session sends the manager to sign in.
test("redirects to sign-in when the session has expired", async () => {
  navigation.redirect.mockImplementation(() => {
    throw new Error("NEXT_REDIRECT");
  });
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 401 }));

  await expect(assignCoordinator("request-1", {}, form("coord-1"))).rejects.toThrow("NEXT_REDIRECT");
});
```

Create `__tests__/operations.test.tsx`:

```tsx
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

vi.mock("@/app/operations/actions", () => ({ assignCoordinator: vi.fn().mockResolvedValue({}) }));

import { AssignCoordinatorForm } from "@/app/operations/assignments/assign-coordinator-form";
import { AssignedList, AwaitingList } from "@/app/operations/assignments/assignment-lists";
import type { EventRequest } from "@/lib/event-requests";
import { coordinatorLabel, type CoordinatorOption } from "@/lib/operations";

afterEach(cleanup);

const coordinators: CoordinatorOption[] = [
  { id: "coord-1", email: "alex@example.com" },
  { id: "coord-2", email: "blair@example.com" },
];

function makeRequest(id: string, name: string): EventRequest {
  return {
    id,
    organiser_id: "organiser-1",
    status: "Submitted",
    event_name: name,
    purpose: "Celebrate",
    description: null,
    proposed_date_times: ["2026-10-20T02:00:00Z"],
    expected_attendance: 80,
    venue_requirements: null,
    accessibility_needs: null,
    equipment_requirements: null,
    registration_needs: null,
    created_at: "2026-09-13T03:00:00Z",
    updated_at: "2026-09-14T03:00:00Z",
  };
}

// Purpose: SCRUM-14 AC1 — each awaiting request is listed with a way to assign it.
test("lists awaiting requests with an assign control each", () => {
  render(<AwaitingList requests={[makeRequest("r1", "Gala Dinner")]} coordinators={coordinators} />);

  const card = screen.getByRole("article", { name: "Gala Dinner" });
  expect(within(card).getByRole("combobox", { name: "Coordinator" })).toBeDefined();
  expect(within(card).getByRole("button", { name: "Assign" })).toBeDefined();
});

// Purpose: An empty queue explains itself instead of looking broken.
test("shows an empty state when nothing awaits assignment", () => {
  render(<AwaitingList requests={[]} coordinators={coordinators} />);

  expect(screen.getByText("Nothing is waiting for a coordinator.")).toBeDefined();
});

// Purpose: SCRUM-14 AC3 — an assigned request shows who is responsible.
test("shows the current coordinator of an assigned request", () => {
  render(
    <AssignedList
      assignments={[{
        event_request: { ...makeRequest("r2", "Tech Summit"), status: "Under Review" },
        assignment: { id: 7, event_request_id: "r2", coordinator_id: "coord-1", assigned_by: "ops-1", assigned_at: "2026-09-20T02:00:00Z" },
      }]}
      coordinators={coordinators}
    />,
  );

  const card = screen.getByRole("article", { name: "Tech Summit" });
  expect(within(card).getByText(/alex@example\.com/)).toBeDefined();
  expect(within(card).getByRole("button", { name: "Reassign" })).toBeDefined();
});

// Purpose: SCRUM-14 AC6 — reassignment never offers the coordinator already responsible.
test("omits the current coordinator from the reassign choices", () => {
  render(<AssignCoordinatorForm eventRequestId="r2" coordinators={coordinators} currentCoordinatorId="coord-1" />);

  const options = within(screen.getByRole("combobox", { name: "Coordinator" })).getAllByRole("option");
  expect(options.map((option) => option.textContent)).toEqual(["Choose a coordinator", "blair@example.com"]);
});

// Purpose: With no one to choose, the form explains why instead of offering an empty picker.
test("explains when no coordinator is available", () => {
  render(<AssignCoordinatorForm eventRequestId="r1" coordinators={[]} />);

  expect(screen.queryByRole("combobox")).toBeNull();
  expect(screen.getByText("No Event Coordinator is available to assign.")).toBeDefined();
});

// Purpose: A coordinator missing from the directory still shows by id rather than blank.
test("labels an unknown coordinator by id", () => {
  expect(coordinatorLabel("coord-9", coordinators)).toBe("coord-9");
  expect(coordinatorLabel("coord-2", coordinators)).toBe("blair@example.com");
});
```

- [ ] **Step 2: Run to verify they fail**

Run: `npx vitest run __tests__/operations-actions.test.ts __tests__/operations.test.tsx`
Expected: FAIL — cannot resolve `@/app/operations/actions` / `@/lib/operations`.

- [ ] **Step 3: Implement**

Create `frontend/lib/operations.ts`:

```ts
import { getJson } from "./api";
import type { EventRequest } from "./event-requests";

export interface CoordinatorAssignment {
  id: number;
  event_request_id: string;
  coordinator_id: string;
  assigned_by: string;
  assigned_at: string;
}

export interface CurrentAssignment {
  event_request: EventRequest;
  assignment: CoordinatorAssignment;
}

export interface CoordinatorOption {
  id: string;
  email: string | null;
}

const eventRequestApi = process.env.EVENT_REQUEST_API_URL ?? "http://127.0.0.1:8003";
const authServiceUrl = process.env.AUTH_SERVICE_URL ?? "http://127.0.0.1:8001";

export async function listAwaitingAssignment(): Promise<EventRequest[]> {
  return (await getJson<EventRequest[]>(eventRequestApi, "/event-requests/awaiting-assignment")) ?? [];
}

export async function listCurrentAssignments(): Promise<CurrentAssignment[]> {
  return (await getJson<CurrentAssignment[]>(eventRequestApi, "/event-requests/assignments")) ?? [];
}

export async function listCoordinators(): Promise<CoordinatorOption[]> {
  return (await getJson<CoordinatorOption[]>(authServiceUrl, "/auth/users?role=event_coordinator")) ?? [];
}

export function coordinatorLabel(id: string, coordinators: CoordinatorOption[]): string {
  return coordinators.find((coordinator) => coordinator.id === id)?.email ?? id;
}
```

Create `frontend/app/operations/layout.tsx`:

```tsx
import type { ReactNode } from "react";
import { requireRole } from "@/lib/auth";

export default async function OperationsLayout({ children }: { children: ReactNode }) {
  await requireRole("event_operations_manager");
  return children;
}
```

Create `frontend/app/operations/actions.ts`:

```ts
"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { readDetail, sendJson } from "@/lib/api";
import { requireRole } from "@/lib/auth";

export interface AssignState {
  message?: string;
  assigned?: boolean;
}

const apiUrl = process.env.EVENT_REQUEST_API_URL ?? "http://127.0.0.1:8003";

export async function assignCoordinator(
  eventRequestId: string,
  previousState: AssignState,
  formData: FormData,
): Promise<AssignState> {
  void previousState;
  const coordinatorId = String(formData.get("coordinator_id") ?? "").trim();
  if (!coordinatorId) return { message: "Choose a coordinator to assign." };

  await requireRole("event_operations_manager");
  let response: Response;
  try {
    response = await sendJson(
      apiUrl,
      `/event-requests/${encodeURIComponent(eventRequestId)}/coordinator`,
      "POST",
      { coordinator_id: coordinatorId },
    );
  } catch {
    return { message: "The coordinator could not be assigned. Please try again." };
  }
  if (response.status === 401) redirect("/auth");
  if (!response.ok) {
    if (response.status === 409) {
      return { message: (await readDetail(response)) ?? "This request can no longer be assigned. Refresh the page." };
    }
    return {
      message:
        response.status === 403
          ? "Only an Event Operations Manager can assign coordinators."
          : response.status === 404
            ? "This request no longer exists. Refresh the page."
            : "The coordinator could not be assigned. Please try again.",
    };
  }
  revalidatePath("/operations/assignments");
  return { assigned: true, message: "Coordinator assigned." };
}
```

Create `frontend/app/operations/assignments/assign-coordinator-form.tsx`:

```tsx
"use client";

import { useActionState } from "react";
import { assignCoordinator, type AssignState } from "../actions";
import type { CoordinatorOption } from "@/lib/operations";

const initialState: AssignState = {};

export function AssignCoordinatorForm({
  eventRequestId,
  coordinators,
  currentCoordinatorId,
}: {
  eventRequestId: string;
  coordinators: CoordinatorOption[];
  currentCoordinatorId?: string;
}) {
  const [state, formAction, isPending] = useActionState(
    assignCoordinator.bind(null, eventRequestId),
    initialState,
  );
  const choices = coordinators.filter((coordinator) => coordinator.id !== currentCoordinatorId);

  if (choices.length === 0) {
    return (
      <p className="text-sm text-[#718078]">
        {currentCoordinatorId ? "No other Event Coordinator is available." : "No Event Coordinator is available to assign."}
      </p>
    );
  }

  return (
    <form action={formAction} className="flex flex-wrap items-end gap-3">
      <label className="text-sm font-semibold text-[#34463f]">
        Coordinator
        <select
          name="coordinator_id"
          defaultValue=""
          className="mt-1 block min-h-11 rounded-xl border border-[#cfd9d4] bg-white px-3 text-sm text-[#273832]"
        >
          <option value="">Choose a coordinator</option>
          {choices.map((coordinator) => (
            <option key={coordinator.id} value={coordinator.id}>
              {coordinator.email ?? coordinator.id}
            </option>
          ))}
        </select>
      </label>
      <button
        type="submit"
        disabled={isPending}
        className="min-h-11 rounded-xl bg-[#0f6b5b] px-4 text-sm font-semibold text-white hover:bg-[#0b5b4d] disabled:opacity-60"
      >
        {isPending ? "Saving…" : currentCoordinatorId ? "Reassign" : "Assign"}
      </button>
      {state.message ? (
        <p role={state.assigned ? "status" : "alert"} className={`w-full rounded-lg px-3 py-2 text-sm ${state.assigned ? "bg-[#e7f5ed] text-[#145d40]" : "bg-[#fff0f0] text-[#a23939]"}`}>
          {state.message}
        </p>
      ) : null}
    </form>
  );
}
```

Create `frontend/app/operations/assignments/assignment-lists.tsx`:

```tsx
import { formatDateTime, statusBadgeClass, type EventRequest } from "@/lib/event-requests";
import { coordinatorLabel, type CoordinatorOption, type CurrentAssignment } from "@/lib/operations";
import { CalendarIcon, PeopleIcon } from "../../components/icons";
import { AssignCoordinatorForm } from "./assign-coordinator-form";

function RequestSummary({ request }: { request: EventRequest }) {
  const headingId = `request-${request.id}`;
  return (
    <>
      <div className="flex flex-wrap items-center gap-3">
        <h3 id={headingId} className="text-base font-bold text-[#1b2b25] sm:text-lg">{request.event_name ?? "Untitled event request"}</h3>
        <span className={`rounded-full px-2.5 py-1 text-xs font-bold ${statusBadgeClass(request.status)}`}>{request.status}</span>
      </div>
      <p className="mt-2 line-clamp-2 text-sm text-[#68776f]">{request.purpose ?? "Purpose not provided"}</p>
      <div className="mt-3 flex flex-wrap gap-x-5 gap-y-2 text-xs font-medium text-[#718078]">
        <span className="inline-flex items-center gap-1.5"><CalendarIcon className="size-4" />{request.proposed_date_times[0] ? formatDateTime(request.proposed_date_times[0]) : "Date not set"}</span>
        <span className="inline-flex items-center gap-1.5"><PeopleIcon className="size-4" />{request.expected_attendance ? `${request.expected_attendance} attendees` : "Attendance not set"}</span>
      </div>
    </>
  );
}

const cardClass = "rounded-2xl border border-[#dce4e0] bg-white p-5 sm:p-6";

export function AwaitingList({ requests, coordinators }: { requests: EventRequest[]; coordinators: CoordinatorOption[] }) {
  if (requests.length === 0) {
    return <p className="rounded-2xl border border-dashed border-[#cbd7d1] bg-white px-6 py-10 text-center text-sm text-[#718078]">Nothing is waiting for a coordinator.</p>;
  }
  return (
    <div className="space-y-3">
      {requests.map((request) => (
        <article key={request.id} aria-labelledby={`request-${request.id}`} className={cardClass}>
          <RequestSummary request={request} />
          <div className="mt-4 border-t border-[#edf1ef] pt-4">
            <AssignCoordinatorForm eventRequestId={request.id} coordinators={coordinators} />
          </div>
        </article>
      ))}
    </div>
  );
}

export function AssignedList({ assignments, coordinators }: { assignments: CurrentAssignment[]; coordinators: CoordinatorOption[] }) {
  if (assignments.length === 0) {
    return <p className="rounded-2xl border border-dashed border-[#cbd7d1] bg-white px-6 py-10 text-center text-sm text-[#718078]">No in-progress request has a coordinator yet.</p>;
  }
  return (
    <div className="space-y-3">
      {assignments.map(({ event_request: request, assignment }) => (
        <article key={request.id} aria-labelledby={`request-${request.id}`} className={cardClass}>
          <RequestSummary request={request} />
          <p className="mt-3 text-sm text-[#273832]">
            Coordinator: <span className="font-semibold">{coordinatorLabel(assignment.coordinator_id, coordinators)}</span>
            <span className="text-[#718078]"> · assigned {formatDateTime(assignment.assigned_at)}</span>
          </p>
          <div className="mt-4 border-t border-[#edf1ef] pt-4">
            <AssignCoordinatorForm eventRequestId={request.id} coordinators={coordinators} currentCoordinatorId={assignment.coordinator_id} />
          </div>
        </article>
      ))}
    </div>
  );
}
```

Create `frontend/app/operations/assignments/page.tsx`:

```tsx
import { Suspense } from "react";
import { requireRole } from "@/lib/auth";
import { listAwaitingAssignment, listCoordinators, listCurrentAssignments } from "@/lib/operations";
import { AppShell, workspaceLinks } from "../../components/app-shell";
import { AssignedList, AwaitingList } from "./assignment-lists";

async function AssignmentData() {
  const [awaiting, assigned, coordinators] = await Promise.allSettled([
    listAwaitingAssignment(),
    listCurrentAssignments(),
    listCoordinators(),
  ]);
  if (awaiting.status === "rejected" || assigned.status === "rejected") {
    return (
      <div role="alert" className="rounded-2xl border border-[#eccdbe] bg-[#fff8f3] px-6 py-8">
        <p className="font-semibold text-[#793f27]">The event request service is unavailable.</p>
        <p className="mt-2 text-sm leading-6 text-[#8b604d]">Start the local API on port 8003, then refresh this page.</p>
      </div>
    );
  }
  const people = coordinators.status === "fulfilled" ? coordinators.value : [];
  return (
    <div className="space-y-10">
      {coordinators.status === "rejected" ? (
        <p role="alert" className="rounded-xl border border-[#ead7ae] bg-[#fff9eb] px-4 py-3 text-sm text-[#6f4b12]">The coordinator directory is unavailable, so assignments can't be made right now. Start the auth service on port 8001, then refresh.</p>
      ) : null}
      <section aria-labelledby="awaiting-heading">
        <h2 id="awaiting-heading" className="mb-4 text-xl font-bold text-[#17211d]">Awaiting a coordinator ({awaiting.value.length})</h2>
        <AwaitingList requests={awaiting.value} coordinators={people} />
      </section>
      <section aria-labelledby="assigned-heading">
        <h2 id="assigned-heading" className="mb-4 text-xl font-bold text-[#17211d]">Assigned ({assigned.value.length})</h2>
        <AssignedList assignments={assigned.value} coordinators={people} />
      </section>
    </div>
  );
}

function Loading() {
  return <div aria-label="Loading assignments" className="space-y-3">{[1, 2].map((item) => <div key={item} className="h-36 animate-pulse rounded-2xl border border-[#e1e7e4] bg-white" />)}</div>;
}

export default async function AssignmentsPage() {
  const user = await requireRole("event_operations_manager");
  return (
    <AppShell signedIn navLinks={workspaceLinks(user.roles)}>
      <div className="mb-8">
        <p className="mb-2 text-xs font-bold uppercase tracking-[0.16em] text-[#0f6b5b]">Operations workspace</p>
        <h1 className="text-3xl font-bold tracking-[-0.035em] text-[#17211d] sm:text-4xl">Coordinator assignments</h1>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-[#68776f] sm:text-base">Give each submitted request a coordinator, or hand an in-progress request to someone else.</p>
      </div>
      <Suspense fallback={<Loading />}>
        <AssignmentData />
      </Suspense>
    </AppShell>
  );
}
```

- [ ] **Step 4: Run unit tests, typecheck, lint**

Run: `npx vitest run __tests__/operations-actions.test.ts __tests__/operations.test.tsx && npm run typecheck && npm run lint`
Expected: 12 new tests pass; typecheck and lint clean.

- [ ] **Step 5: Extend the e2e mocks**

In `e2e/support/auth-api.mjs`, at the top of the request handler (after `/health`), add:

```js
  const url = new URL(request.url ?? "/", "http://127.0.0.1");
  if (request.method === "GET" && url.pathname === "/auth/users") {
    if (request.headers.authorization !== "Bearer ops-session" || url.searchParams.get("role") !== "event_coordinator") {
      send(response, 403, { detail: "Insufficient permissions" });
      return;
    }
    send(response, 200, [
      { id: "playwright-coordinator", email: "coordinator@example.com" },
      { id: "other-coordinator", email: "other.coordinator@example.com" },
    ]);
    return;
  }
```

In `e2e/support/event-request-api.mjs`, add `const COORDINATOR_IDS = new Set(["playwright-coordinator", "other-coordinator"]);` and `const TERMINAL = new Set(["Completed", "Cancelled", "Rejected"]);` near the other constants. Insert directly **after** the `/event-requests/assigned-to-me` block (it must run before the generic `/event-requests/:id` match):

```js
  if (url.pathname === "/event-requests/awaiting-assignment" && request.method === "GET") {
    if (user.role !== "event_operations_manager") {
      send(response, 403, { detail: "Insufficient permissions" });
      return;
    }
    send(response, 200, [...records.values()]
      .filter((record) => record.status === "Submitted" && latestAssignmentFor(record.id) === null)
      .sort((a, b) => b.created_at.localeCompare(a.created_at)));
    return;
  }

  if (url.pathname === "/event-requests/assignments" && request.method === "GET") {
    if (user.role !== "event_operations_manager") {
      send(response, 403, { detail: "Insufficient permissions" });
      return;
    }
    send(response, 200, [...records.values()]
      .filter((record) => record.status !== "Draft" && !TERMINAL.has(record.status) && latestAssignmentFor(record.id) !== null)
      .sort((a, b) => b.created_at.localeCompare(a.created_at))
      .map((record) => ({ event_request: record, assignment: latestAssignmentFor(record.id) })));
    return;
  }
```

In the existing `POST /event-requests/:id/coordinator` block, after the `!record` check and after reading `body`, add:

```js
      if (record.status === "Draft" || TERMINAL.has(record.status)) {
        send(response, 409, { detail: `Cannot assign a Coordinator to a ${record.status} request` });
        return;
      }
      if (!COORDINATOR_IDS.has(body.coordinator_id)) {
        send(response, 409, { detail: "The selected user is not an Event Coordinator" });
        return;
      }
```

Also delete the now-stale comment "the UI for it belongs to another story, so tests drive this endpoint directly."

- [ ] **Step 6: Write the e2e spec** — create `e2e/assign-coordinator.spec.ts`:

```ts
import { expect, test } from "@playwright/test";

const EVENT_API = "http://127.0.0.1:8103";

function sessionCookie(value: string) {
  return [{ name: "cs_access_token", value, url: "http://127.0.0.1:3100" }];
}

test.describe.serial("SCRUM-14 coordinator assignment", () => {
  // Purpose: Covers AC1, AC2, AC3 and AC6 end to end — the manager finds an
  // unassigned submission, assigns it, the coordinator sees it, then the
  // manager reassigns it and the first coordinator loses it.
  test("manager assigns and reassigns a submitted request", async ({ page, request }) => {
    const seeded = await request.post(`${EVENT_API}/__seed`, {
      data: { event_name: "Harbour Lights Gala", organiser_id: "playwright-user", status: "Submitted", purpose: "Annual fundraiser" },
    });
    expect(seeded.ok()).toBeTruthy();

    await page.goto("/auth");
    await page.getByLabel("Email").fill("ops@example.com");
    await page.getByLabel("Password").fill("test-password-123");
    await page.getByRole("button", { name: "Log in", exact: true }).last().click();
    await expect(page).toHaveURL(/\/operations\/assignments$/);

    const awaitingCard = page.getByRole("article", { name: "Harbour Lights Gala" });
    await expect(awaitingCard).toBeVisible();
    await awaitingCard.getByRole("button", { name: "Assign" }).click();
    await expect(awaitingCard.getByRole("alert")).toHaveText("Choose a coordinator to assign.");

    await awaitingCard.getByLabel("Coordinator").selectOption({ label: "coordinator@example.com" });
    await awaitingCard.getByRole("button", { name: "Assign" }).click();

    const assignedCard = page.locator("section", { has: page.getByRole("heading", { name: /^Assigned/ }) })
      .getByRole("article", { name: "Harbour Lights Gala" });
    await expect(assignedCard).toContainText("coordinator@example.com");
    await expect(assignedCard).toContainText("Submitted");

    await page.context().clearCookies();
    await page.context().addCookies(sessionCookie("coordinator-session"));
    await page.goto("/coordination/requests");
    await expect(page.getByRole("heading", { name: "Harbour Lights Gala" })).toBeVisible();

    await page.context().clearCookies();
    await page.context().addCookies(sessionCookie("ops-session"));
    await page.goto("/operations/assignments");
    const card = page.locator("section", { has: page.getByRole("heading", { name: /^Assigned/ }) })
      .getByRole("article", { name: "Harbour Lights Gala" });
    const picker = card.getByLabel("Coordinator");
    await expect(picker.getByRole("option", { name: "coordinator@example.com", exact: true })).toHaveCount(0);
    await picker.selectOption({ label: "other.coordinator@example.com" });
    await card.getByRole("button", { name: "Reassign" }).click();
    await expect(card).toContainText("other.coordinator@example.com");

    await page.context().clearCookies();
    await page.context().addCookies(sessionCookie("coordinator-session"));
    await page.goto("/coordination/requests");
    await expect(page.getByRole("heading", { name: "Harbour Lights Gala" })).toHaveCount(0);
  });

  // Purpose: SCRUM-27 — the assignment workspace is closed to other roles.
  test("organisers cannot open the assignment workspace", async ({ page }) => {
    await page.context().addCookies(sessionCookie("test-session"));
    await page.goto("/operations/assignments");
    await expect(page).toHaveURL(/\/unauthorised$/);
  });
});
```

- [ ] **Step 7: Run the e2e suite**

Run: `npm run test:e2e`
Expected: all specs pass, including the 2 new ones.

- [ ] **Step 8: Commit**

```bash
git add frontend/lib/operations.ts frontend/app/operations frontend/e2e frontend/__tests__/operations-actions.test.ts frontend/__tests__/operations.test.tsx
git commit -m "feat(frontend): operations manager assigns and reassigns coordinators (SCRUM-14)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: SCRUM-30 — Venue Staff catalogue

**Files:**
- Create: `frontend/lib/venues.ts`, `frontend/lib/venue-form.ts`
- Create: `frontend/app/venues/page.tsx`, `frontend/app/venues/actions.ts`, `frontend/app/venues/venue-form.tsx`, `frontend/app/venues/new/page.tsx`, `frontend/app/venues/[id]/edit/page.tsx`
- Create: `frontend/e2e/support/venue-api.mjs`; Modify: `frontend/playwright.config.ts`
- Test: create `frontend/__tests__/venue-form.test.ts`, `frontend/__tests__/venues.test.tsx`, `frontend/e2e/venue-catalogue.spec.ts`

**Interfaces:**
- Consumes: `getJson`, `sendJson`, `readDetail` (Task 3); `requireRole`, `workspaceLinks`.
- Produces (`lib/venues.ts`): `ROOM_LAYOUTS`, `SLOTS` (readonly tuples), types `RoomLayout`, `Slot`, `VenueStatus = "available" | "blocked"`, `Venue`; `venueApiUrl`; `listVenues(): Promise<Venue[]>`; `getVenue(id: string): Promise<Venue | null>`; `layoutLabel(layout: RoomLayout): string` (capitalised).
- Produces (`lib/venue-form.ts`): `splitList(value: string): string[]`; `parseVenueForm(formData: FormData, { includeStatus }: { includeStatus: boolean }): { payload: VenuePayload; errors: Record<string, string> }` where `VenuePayload = { name: string; location: string; max_capacity: number | null; facilities: string[]; accessibility_features: string[]; supported_layouts: RoomLayout[]; operating_slots: Slot[]; status?: VenueStatus }`.
- Produces (`app/venues/actions.ts`): `createVenue(prev: VenueFormState, fd): Promise<VenueFormState>`, `updateVenue(venueId: string, prev, fd)`; `VenueFormState = { message?: string; errors?: Record<string, string> }`.
- Produces (e2e): mock venue API on 8105 with `GET/POST /venues`, `GET/PATCH /venues/:id`; `POST /__seed` accepts a full venue.

- [ ] **Step 1: Write the failing unit tests**

Create `__tests__/venue-form.test.ts`:

```ts
import { expect, test } from "vitest";
import { parseVenueForm, splitList } from "@/lib/venue-form";

function venueForm(fields: Record<string, string | string[]>): FormData {
  const data = new FormData();
  for (const [key, value] of Object.entries(fields)) {
    for (const item of Array.isArray(value) ? value : [value]) data.append(key, item);
  }
  return data;
}

const valid = {
  name: "Riverside Hall",
  location: "Level 2, East Wing",
  max_capacity: "120",
  facilities: "Projector, WiFi",
  accessibility_features: "Ramp access",
  supported_layouts: ["theatre", "classroom"],
  operating_slots: ["AM", "PM"],
};

// Purpose: Review focus 5 — comma lists are trimmed, blank-free and de-duplicated.
test("splitList trims, drops blanks and de-duplicates case-insensitively", () => {
  expect(splitList("Projector, , projector ,WiFi")).toEqual(["Projector", "WiFi"]);
  expect(splitList("   ")).toEqual([]);
});

// Purpose: SCRUM-30 AC1 — every catalogue attribute is captured from the form.
test("parses a complete venue", () => {
  const { payload, errors } = parseVenueForm(venueForm(valid), { includeStatus: false });

  expect(errors).toEqual({});
  expect(payload).toEqual({
    name: "Riverside Hall",
    location: "Level 2, East Wing",
    max_capacity: 120,
    facilities: ["Projector", "WiFi"],
    accessibility_features: ["Ramp access"],
    supported_layouts: ["theatre", "classroom"],
    operating_slots: ["AM", "PM"],
  });
});

// Purpose: Review focus 4 — capacity must be a whole number above zero.
test.each(["abc", "0", "-3", "12.5", ""])("rejects capacity %j", (capacity) => {
  const { errors } = parseVenueForm(venueForm({ ...valid, max_capacity: capacity }), { includeStatus: false });

  expect(errors.max_capacity).toBe("Enter a whole number greater than zero.");
});

// Purpose: A venue needs a name, a location and at least one bookable slot.
test("reports missing required fields", () => {
  const { errors } = parseVenueForm(venueForm({ max_capacity: "10" }), { includeStatus: false });

  expect(errors).toMatchObject({
    name: "Enter the venue name.",
    location: "Enter the venue location.",
    operating_slots: "Choose at least one operating slot.",
  });
});

// Purpose: Values outside the backend enums are dropped rather than sent.
test("ignores unknown layouts, slots and statuses", () => {
  const { payload } = parseVenueForm(
    venueForm({ ...valid, supported_layouts: ["theatre", "ballroom"], operating_slots: ["AM", "MIDNIGHT"], status: "gone" }),
    { includeStatus: true },
  );

  expect(payload.supported_layouts).toEqual(["theatre"]);
  expect(payload.operating_slots).toEqual(["AM"]);
  expect(payload.status).toBe("available");
});

// Purpose: Editing can take a venue out of service; creating cannot set status.
test("includes status only when editing", () => {
  expect(parseVenueForm(venueForm({ ...valid, status: "blocked" }), { includeStatus: true }).payload.status).toBe("blocked");
  expect("status" in parseVenueForm(venueForm({ ...valid, status: "blocked" }), { includeStatus: false }).payload).toBe(false);
});
```

Create `__tests__/venues.test.tsx`:

```tsx
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

vi.mock("@/app/venues/actions", () => ({ createVenue: vi.fn(), updateVenue: vi.fn() }));

import { VenueForm } from "@/app/venues/venue-form";
import type { Venue } from "@/lib/venues";

afterEach(cleanup);

const venue: Venue = {
  id: "venue-1",
  name: "Riverside Hall",
  location: "Level 2",
  max_capacity: 120,
  facilities: ["Projector", "WiFi"],
  accessibility_features: ["Ramp access"],
  supported_layouts: ["theatre"],
  operating_slots: ["AM", "PM"],
  status: "available",
  created_at: "2026-09-13T03:00:00Z",
  updated_at: "2026-09-14T03:00:00Z",
};

// Purpose: SCRUM-30 AC1 — a new venue form asks for every catalogue attribute.
test("new venue form offers every attribute and no status", () => {
  render(<VenueForm />);

  for (const label of ["Venue name", "Location", "Maximum capacity", "Facilities", "Accessibility features"]) {
    expect(screen.getByLabelText(label)).toBeDefined();
  }
  expect(screen.getByRole("checkbox", { name: "Theatre" })).toBeDefined();
  expect(screen.getByRole("checkbox", { name: "NIGHT" })).toBeDefined();
  expect(screen.queryByLabelText("Availability")).toBeNull();
  expect(screen.getByRole("button", { name: "Add venue" })).toBeDefined();
});

// Purpose: SCRUM-30 AC2 — editing starts from the venue's current attributes.
test("edit form is prefilled with the current attributes", () => {
  render(<VenueForm venue={venue} />);

  expect((screen.getByLabelText("Venue name") as HTMLInputElement).value).toBe("Riverside Hall");
  expect((screen.getByLabelText("Facilities") as HTMLInputElement).value).toBe("Projector, WiFi");
  expect((screen.getByRole("checkbox", { name: "Theatre" }) as HTMLInputElement).checked).toBe(true);
  expect((screen.getByRole("checkbox", { name: "Classroom" }) as HTMLInputElement).checked).toBe(false);
  expect((screen.getByLabelText("Availability") as HTMLSelectElement).value).toBe("available");
  expect(screen.getByRole("button", { name: "Save changes" })).toBeDefined();
});
```

- [ ] **Step 2: Run to verify they fail**

Run: `npx vitest run __tests__/venue-form.test.ts __tests__/venues.test.tsx`
Expected: FAIL — cannot resolve `@/lib/venue-form`, `@/app/venues/venue-form`.

- [ ] **Step 3: Implement the libraries**

Create `frontend/lib/venues.ts`:

```ts
import { getJson } from "./api";

export const ROOM_LAYOUTS = ["classroom", "theatre", "boardroom", "banquet", "exhibition"] as const;
export const SLOTS = ["AM", "PM", "NIGHT"] as const;
export type RoomLayout = (typeof ROOM_LAYOUTS)[number];
export type Slot = (typeof SLOTS)[number];
export type VenueStatus = "available" | "blocked";

export interface Venue {
  id: string;
  name: string;
  location: string;
  max_capacity: number;
  facilities: string[];
  accessibility_features: string[];
  supported_layouts: RoomLayout[];
  operating_slots: Slot[];
  status: VenueStatus;
  created_at: string;
  updated_at: string;
}

export const venueApiUrl = process.env.VENUE_API_URL ?? "http://127.0.0.1:8004";

export async function listVenues(): Promise<Venue[]> {
  return (await getJson<Venue[]>(venueApiUrl, "/venues")) ?? [];
}

export async function getVenue(id: string): Promise<Venue | null> {
  return getJson<Venue>(venueApiUrl, `/venues/${encodeURIComponent(id)}`);
}

export function layoutLabel(layout: RoomLayout): string {
  return layout.charAt(0).toUpperCase() + layout.slice(1);
}
```

Create `frontend/lib/venue-form.ts`:

```ts
import { ROOM_LAYOUTS, SLOTS, type RoomLayout, type Slot, type VenueStatus } from "./venues";

export interface VenuePayload {
  name: string;
  location: string;
  max_capacity: number | null;
  facilities: string[];
  accessibility_features: string[];
  supported_layouts: RoomLayout[];
  operating_slots: Slot[];
  status?: VenueStatus;
}

// Comma-separated free text → trimmed, non-empty values, de-duplicated
// case-insensitively (first spelling wins).
export function splitList(value: string): string[] {
  const seen = new Set<string>();
  const items: string[] = [];
  for (const raw of value.split(",")) {
    const item = raw.trim();
    const key = item.toLowerCase();
    if (item && !seen.has(key)) {
      seen.add(key);
      items.push(item);
    }
  }
  return items;
}

function text(formData: FormData, field: string): string {
  return String(formData.get(field) ?? "").trim();
}

function pick<T extends string>(formData: FormData, field: string, allowed: readonly T[]): T[] {
  const chosen = new Set(formData.getAll(field).map(String));
  return allowed.filter((value) => chosen.has(value));
}

export function parseVenueForm(
  formData: FormData,
  { includeStatus }: { includeStatus: boolean },
): { payload: VenuePayload; errors: Record<string, string> } {
  const capacityText = text(formData, "max_capacity");
  const capacity = /^\d+$/.test(capacityText) ? Number(capacityText) : null;
  const payload: VenuePayload = {
    name: text(formData, "name"),
    location: text(formData, "location"),
    max_capacity: capacity,
    facilities: splitList(text(formData, "facilities")),
    accessibility_features: splitList(text(formData, "accessibility_features")),
    supported_layouts: pick(formData, "supported_layouts", ROOM_LAYOUTS),
    operating_slots: pick(formData, "operating_slots", SLOTS),
  };
  if (includeStatus) {
    payload.status = text(formData, "status") === "blocked" ? "blocked" : "available";
  }

  const errors: Record<string, string> = {};
  if (!payload.name) errors.name = "Enter the venue name.";
  if (!payload.location) errors.location = "Enter the venue location.";
  if (capacity === null || capacity <= 0) errors.max_capacity = "Enter a whole number greater than zero.";
  if (payload.operating_slots.length === 0) errors.operating_slots = "Choose at least one operating slot.";
  return { payload, errors };
}
```

- [ ] **Step 4: Implement actions, form and pages**

Create `frontend/app/venues/actions.ts`:

```ts
"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { sendJson } from "@/lib/api";
import { requireRole } from "@/lib/auth";
import { parseVenueForm } from "@/lib/venue-form";
import { venueApiUrl } from "@/lib/venues";

export interface VenueFormState {
  message?: string;
  errors?: Record<string, string>;
}

async function saveVenue(
  path: string,
  method: "POST" | "PATCH",
  formData: FormData,
): Promise<VenueFormState> {
  const { payload, errors } = parseVenueForm(formData, { includeStatus: method === "PATCH" });
  if (Object.keys(errors).length) return { message: "Check the highlighted fields.", errors };

  await requireRole("venue_staff");
  let response: Response;
  try {
    response = await sendJson(venueApiUrl, path, method, payload);
  } catch {
    return { message: "The venue could not be saved. Please try again." };
  }
  if (response.status === 401) redirect("/auth");
  if (!response.ok) {
    return {
      message:
        response.status === 403
          ? "Only Venue Staff can change the venue catalogue."
          : response.status === 404
            ? "This venue no longer exists."
            : response.status === 422
              ? "Check the highlighted fields."
              : "The venue could not be saved. Please try again.",
    };
  }
  revalidatePath("/venues");
  redirect("/venues");
}

export async function createVenue(previousState: VenueFormState, formData: FormData): Promise<VenueFormState> {
  void previousState;
  return saveVenue("/venues", "POST", formData);
}

export async function updateVenue(
  venueId: string,
  previousState: VenueFormState,
  formData: FormData,
): Promise<VenueFormState> {
  void previousState;
  return saveVenue(`/venues/${encodeURIComponent(venueId)}`, "PATCH", formData);
}
```

Create `frontend/app/venues/venue-form.tsx`:

```tsx
"use client";

import { useActionState } from "react";
import { layoutLabel, ROOM_LAYOUTS, SLOTS, type Venue } from "@/lib/venues";
import { createVenue, updateVenue, type VenueFormState } from "./actions";

const initialState: VenueFormState = {};
const inputClass = "mt-2 w-full rounded-xl border border-[#cfd9d4] bg-white px-4 py-3 text-sm text-[#273832] outline-none focus:border-[#0f6b5b] focus:ring-3 focus:ring-[#dff1eb]";
const labelClass = "block text-sm font-semibold text-[#34463f]";

function FieldError({ message }: { message?: string }) {
  return message ? <p className="mt-1 text-sm text-[#a23939]">{message}</p> : null;
}

export function VenueForm({ venue }: { venue?: Venue }) {
  const action = venue ? updateVenue.bind(null, venue.id) : createVenue;
  const [state, formAction, isPending] = useActionState(action, initialState);
  const errors = state.errors ?? {};

  return (
    <form action={formAction} noValidate className="space-y-6 rounded-2xl border border-[#dce4e0] bg-white p-6 sm:p-8">
      <div className="grid gap-5 sm:grid-cols-2">
        <label className={labelClass}>Venue name<input name="name" defaultValue={venue?.name} className={inputClass} /><FieldError message={errors.name} /></label>
        <label className={labelClass}>Location<input name="location" defaultValue={venue?.location} className={inputClass} /><FieldError message={errors.location} /></label>
        <label className={labelClass}>Maximum capacity<input name="max_capacity" type="number" min={1} step={1} defaultValue={venue?.max_capacity} className={inputClass} /><FieldError message={errors.max_capacity} /></label>
        {venue ? (
          <label className={labelClass}>Availability
            <select name="status" defaultValue={venue.status} className={inputClass}>
              <option value="available">Available</option>
              <option value="blocked">Blocked — hidden from venue search</option>
            </select>
          </label>
        ) : null}
        <div className="sm:col-span-2"><label className={labelClass}>Facilities<input name="facilities" defaultValue={venue?.facilities.join(", ")} placeholder="Projector, WiFi, Stage" className={inputClass} /></label><p className="mt-1 text-xs text-[#718078]">Separate items with commas.</p></div>
        <div className="sm:col-span-2"><label className={labelClass}>Accessibility features<input name="accessibility_features" defaultValue={venue?.accessibility_features.join(", ")} placeholder="Ramp access, Hearing loop" className={inputClass} /></label><p className="mt-1 text-xs text-[#718078]">Separate items with commas.</p></div>
      </div>
      <fieldset>
        <legend className={labelClass}>Supported room layouts</legend>
        <div className="mt-2 flex flex-wrap gap-4">
          {ROOM_LAYOUTS.map((layout) => (
            <label key={layout} className="inline-flex items-center gap-2 text-sm text-[#273832]">
              <input type="checkbox" name="supported_layouts" value={layout} defaultChecked={venue?.supported_layouts.includes(layout)} />
              {layoutLabel(layout)}
            </label>
          ))}
        </div>
      </fieldset>
      <fieldset>
        <legend className={labelClass}>Operating slots</legend>
        <div className="mt-2 flex flex-wrap gap-4">
          {SLOTS.map((slot) => (
            <label key={slot} className="inline-flex items-center gap-2 text-sm text-[#273832]">
              <input type="checkbox" name="operating_slots" value={slot} defaultChecked={venue ? venue.operating_slots.includes(slot) : true} />
              {slot}
            </label>
          ))}
        </div>
        <FieldError message={errors.operating_slots} />
      </fieldset>
      {state.message ? <p role="alert" className="rounded-xl bg-[#fff4f3] px-4 py-3 text-sm text-[#8e3d35]">{state.message}</p> : null}
      <button type="submit" disabled={isPending} className="min-h-11 rounded-xl bg-[#0f6b5b] px-5 text-sm font-bold text-white hover:bg-[#0b5b4d] disabled:opacity-60">
        {isPending ? "Saving…" : venue ? "Save changes" : "Add venue"}
      </button>
    </form>
  );
}
```

Create `frontend/app/venues/page.tsx`:

```tsx
import Link from "next/link";
import { Suspense } from "react";
import { requireRole } from "@/lib/auth";
import { layoutLabel, listVenues } from "@/lib/venues";
import { AppShell, workspaceLinks } from "../components/app-shell";

async function VenueData() {
  const result = await listVenues().then((venues) => ({ venues, failed: false as const })).catch(() => ({ venues: [], failed: true as const }));
  if (result.failed) {
    return <div role="alert" className="rounded-2xl border border-[#eccdbe] bg-[#fff8f3] px-6 py-8 text-[#793f27]">The venue service is unavailable. Start the local API on port 8004, then refresh.</div>;
  }
  if (result.venues.length === 0) {
    return <p className="rounded-2xl border border-dashed border-[#cbd7d1] bg-white px-6 py-14 text-center text-sm text-[#718078]">No venues yet. Add the first venue to the catalogue.</p>;
  }
  return (
    <div className="space-y-3">
      {result.venues.map((venue) => (
        <article key={venue.id} aria-labelledby={`venue-${venue.id}`} className="flex flex-col gap-3 rounded-2xl border border-[#dce4e0] bg-white p-5 sm:flex-row sm:items-center sm:justify-between sm:p-6">
          <div>
            <div className="flex flex-wrap items-center gap-3">
              <h2 id={`venue-${venue.id}`} className="text-lg font-bold text-[#1b2b25]">{venue.name}</h2>
              <span className={`rounded-full px-2.5 py-1 text-xs font-bold ${venue.status === "available" ? "bg-[#e3f2ea] text-[#145c40]" : "bg-[#fdecea] text-[#8c3a2b]"}`}>{venue.status === "available" ? "Available" : "Blocked"}</span>
            </div>
            <p className="mt-1 text-sm text-[#68776f]">{venue.location} · up to {venue.max_capacity} people · {venue.operating_slots.join(", ")}</p>
            <p className="mt-1 text-xs text-[#718078]">Layouts: {venue.supported_layouts.map(layoutLabel).join(", ") || "none recorded"} · Facilities: {venue.facilities.join(", ") || "none recorded"} · Accessibility: {venue.accessibility_features.join(", ") || "none recorded"}</p>
          </div>
          <Link href={`/venues/${venue.id}/edit`} className="text-sm font-semibold text-[#0f6b5b] hover:underline">Edit {venue.name}</Link>
        </article>
      ))}
    </div>
  );
}

export default async function VenuesPage() {
  const user = await requireRole("venue_staff");
  return (
    <AppShell signedIn navLinks={workspaceLinks(user.roles)}>
      <div className="mb-8 flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="mb-2 text-xs font-bold uppercase tracking-[0.16em] text-[#0f6b5b]">Venue workspace</p>
          <h1 className="text-3xl font-bold tracking-[-0.035em] text-[#17211d] sm:text-4xl">Venue catalogue</h1>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-[#68776f] sm:text-base">Keep each venue's details accurate so coordinators plan against the real space.</p>
        </div>
        <Link href="/venues/new" className="inline-flex min-h-11 items-center justify-center rounded-xl bg-[#0f6b5b] px-5 text-sm font-bold text-white hover:bg-[#0b5b4d]">+ Add venue</Link>
      </div>
      <Suspense fallback={<div aria-label="Loading venues" className="h-36 animate-pulse rounded-2xl border border-[#e1e7e4] bg-white" />}>
        <VenueData />
      </Suspense>
    </AppShell>
  );
}
```

Create `frontend/app/venues/new/page.tsx`:

```tsx
import Link from "next/link";
import { requireRole } from "@/lib/auth";
import { AppShell, workspaceLinks } from "../../components/app-shell";
import { VenueForm } from "../venue-form";

export default async function NewVenuePage() {
  const user = await requireRole("venue_staff");
  return (
    <AppShell signedIn navLinks={workspaceLinks(user.roles)}>
      <div className="mx-auto max-w-3xl">
        <Link href="/venues" className="mb-5 inline-block text-sm font-semibold text-[#0f6b5b] hover:underline">← Back to venues</Link>
        <h1 className="mb-6 text-3xl font-bold tracking-[-0.035em] text-[#17211d]">Add a venue</h1>
        <VenueForm />
      </div>
    </AppShell>
  );
}
```

Create `frontend/app/venues/[id]/edit/page.tsx`:

```tsx
import Link from "next/link";
import { requireRole } from "@/lib/auth";
import { getVenue } from "@/lib/venues";
import { AppShell, workspaceLinks } from "../../../components/app-shell";
import { VenueForm } from "../../venue-form";

export default async function EditVenuePage({ params }: { params: Promise<{ id: string }> }) {
  const user = await requireRole("venue_staff");
  const { id } = await params;
  const result = await getVenue(id).then((venue) => ({ venue, failed: false as const })).catch(() => ({ venue: null, failed: true as const }));
  return (
    <AppShell signedIn navLinks={workspaceLinks(user.roles)}>
      <div className="mx-auto max-w-3xl">
        <Link href="/venues" className="mb-5 inline-block text-sm font-semibold text-[#0f6b5b] hover:underline">← Back to venues</Link>
        {result.failed ? (
          <div role="alert" className="rounded-2xl border border-[#eccdbe] bg-[#fff8f3] px-6 py-8 text-[#793f27]">The venue service is unavailable. Start the local API on port 8004, then refresh.</div>
        ) : result.venue ? (
          <>
            <h1 className="mb-6 text-3xl font-bold tracking-[-0.035em] text-[#17211d]">Edit {result.venue.name}</h1>
            <VenueForm venue={result.venue} />
          </>
        ) : (
          <h1 className="text-xl font-bold">Venue not found</h1>
        )}
      </div>
    </AppShell>
  );
}
```

- [ ] **Step 5: Run unit tests, typecheck, lint**

Run: `npx vitest run __tests__/venue-form.test.ts __tests__/venues.test.tsx && npm run typecheck && npm run lint`
Expected: new tests pass; clean.

- [ ] **Step 6: Mock venue API and Playwright wiring**

Create `frontend/e2e/support/venue-api.mjs`:

```js
import { randomUUID } from "node:crypto";
import { createServer } from "node:http";

const venues = new Map();
const SESSIONS = {
  "test-session": "event_organiser",
  "coordinator-session": "event_coordinator",
  "ops-session": "event_operations_manager",
  "venue-session": "venue_staff",
  "tech-session": "technical_support",
};

function send(response, status, body) {
  response.writeHead(status, { "Content-Type": "application/json" });
  response.end(JSON.stringify(body));
}

async function readJson(request) {
  const chunks = [];
  for await (const chunk of request) chunks.push(chunk);
  return chunks.length ? JSON.parse(Buffer.concat(chunks).toString("utf8")) : {};
}

function invalid(body) {
  return !body.name || !body.location || !Number.isInteger(body.max_capacity) || body.max_capacity <= 0;
}

function makeVenue(body) {
  const now = new Date().toISOString();
  return {
    facilities: [], accessibility_features: [], supported_layouts: [], operating_slots: ["AM", "PM", "NIGHT"],
    ...body, id: body.id ?? randomUUID(), status: body.status ?? "available", created_at: now, updated_at: now,
  };
}

createServer(async (request, response) => {
  const url = new URL(request.url ?? "/", "http://127.0.0.1");
  if (request.method === "GET" && url.pathname === "/health") return send(response, 200, { status: "ok" });
  if (request.method === "POST" && url.pathname === "/__seed") {
    const venue = makeVenue(await readJson(request));
    venues.set(venue.id, venue);
    return send(response, 201, venue);
  }

  const role = SESSIONS[(request.headers.authorization ?? "").replace(/^Bearer /, "")];
  if (!role) return send(response, 401, { detail: "Authentication required" });

  if (url.pathname === "/venues" && request.method === "GET") return send(response, 200, [...venues.values()]);
  if (url.pathname === "/venues" && request.method === "POST") {
    if (role !== "venue_staff") return send(response, 403, { detail: "Insufficient permissions" });
    const body = await readJson(request);
    if (invalid(body)) return send(response, 422, { detail: "Invalid venue" });
    const venue = makeVenue(body);
    venues.set(venue.id, venue);
    return send(response, 201, venue);
  }

  const match = url.pathname.match(/^\/venues\/([^/]+)$/);
  const venue = match ? venues.get(decodeURIComponent(match[1])) : undefined;
  if (match && request.method === "GET") return venue ? send(response, 200, venue) : send(response, 404, { detail: "Venue not found" });
  if (match && request.method === "PATCH") {
    if (role !== "venue_staff") return send(response, 403, { detail: "Insufficient permissions" });
    if (!venue) return send(response, 404, { detail: "Venue not found" });
    const updated = { ...venue, ...(await readJson(request)), updated_at: new Date().toISOString() };
    venues.set(venue.id, updated);
    return send(response, 200, updated);
  }
  send(response, 404, { detail: "Not found" });
}).listen(8105, "127.0.0.1");
```

In `frontend/playwright.config.ts`, add to `webServer` before the Next entry:

```ts
    {
      command: "node e2e/support/venue-api.mjs",
      url: "http://127.0.0.1:8105/health",
      reuseExistingServer: false,
      timeout: 30_000,
    },
```

and add `VENUE_API_URL: "http://127.0.0.1:8105",` to the Next server's `env`.

- [ ] **Step 7: Write the e2e spec** — create `frontend/e2e/venue-catalogue.spec.ts`:

```ts
import { expect, test } from "@playwright/test";

// Purpose: SCRUM-30 AC1–AC2 — venue staff add a venue, see its attributes, then update it.
test("venue staff add and update a venue", async ({ page }) => {
  await page.goto("/auth");
  await page.getByLabel("Email").fill("venue@example.com");
  await page.getByLabel("Password").fill("test-password-123");
  await page.getByRole("button", { name: "Log in", exact: true }).last().click();
  await expect(page).toHaveURL(/\/venues$/);

  await page.getByRole("link", { name: "+ Add venue" }).click();
  await page.getByLabel("Venue name").fill("Orchard Studio");
  await page.getByLabel("Location").fill("Level 3, North Wing");
  await page.getByLabel("Maximum capacity").fill("0");
  await page.getByRole("button", { name: "Add venue" }).click();
  await expect(page.getByText("Enter a whole number greater than zero.")).toBeVisible();

  await page.getByLabel("Maximum capacity").fill("45");
  await page.getByLabel("Facilities").fill("Projector, WiFi");
  await page.getByLabel("Accessibility features").fill("Ramp access");
  await page.getByRole("checkbox", { name: "Boardroom" }).check();
  await page.getByRole("button", { name: "Add venue" }).click();

  await expect(page).toHaveURL(/\/venues$/);
  const card = page.getByRole("article", { name: "Orchard Studio" });
  await expect(card).toContainText("up to 45 people");
  await expect(card).toContainText("Boardroom");

  await card.getByRole("link", { name: "Edit Orchard Studio" }).click();
  await page.getByLabel("Maximum capacity").fill("60");
  await page.getByLabel("Availability").selectOption("blocked");
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page).toHaveURL(/\/venues$/);
  await expect(card).toContainText("up to 60 people");
  await expect(card).toContainText("Blocked");
});

// Purpose: SCRUM-27 — only Venue Staff can maintain the catalogue.
test("coordinators cannot open the venue catalogue", async ({ page }) => {
  await page.context().addCookies([{ name: "cs_access_token", value: "coordinator-session", url: "http://127.0.0.1:3100" }]);
  await page.goto("/venues/new");
  await expect(page).toHaveURL(/\/unauthorised$/);
});
```

- [ ] **Step 8: Run the e2e suite**

Run: `npm run test:e2e`
Expected: all pass.

- [ ] **Step 9: Commit**

```bash
git add frontend/lib/venues.ts frontend/lib/venue-form.ts frontend/app/venues frontend/e2e frontend/playwright.config.ts frontend/__tests__/venue-form.test.ts frontend/__tests__/venues.test.tsx
git commit -m "feat(frontend): venue staff maintain the venue catalogue (SCRUM-30)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: SCRUM-9 — Venue search for coordinators

**Files:**
- Modify: `frontend/lib/venue-form.ts` (add search helpers), `frontend/lib/venues.ts` (add `searchVenues`), `frontend/e2e/support/venue-api.mjs` (add `/venues/search`), `frontend/app/coordination/requests/[id]/page.tsx` (add "Find venues" link)
- Create: `frontend/app/venues/search/page.tsx`, `frontend/app/venues/search/venue-results.tsx`
- Test: create `frontend/__tests__/venue-search.test.tsx`, `frontend/e2e/venue-search.spec.ts`

**Interfaces:**
- Consumes: `Venue`, `ROOM_LAYOUTS`, `SLOTS`, `layoutLabel`, `venueApiUrl`, `splitList` (Task 5); `getJson`; `requireAnyRole`.
- Produces: `VenueSearchInput = { required_capacity?: string; location?: string; date?: string; slot?: string; layout?: string; facility?: string; accessibility?: string }`; `buildVenueSearch(input: VenueSearchInput): { query: string | null; errors: Record<string, string> }` (`query` is `null` when nothing is filled in or there are errors; otherwise a `URLSearchParams` string with `facility`/`accessibility` repeated per list item and unknown `slot`/`layout` dropped); `searchVenues(query: string): Promise<Venue[]>`.

- [ ] **Step 1: Write the failing tests** — create `__tests__/venue-search.test.tsx`:

```tsx
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";

import { VenueResults } from "@/app/venues/search/venue-results";
import { buildVenueSearch } from "@/lib/venue-form";
import type { Venue } from "@/lib/venues";

afterEach(cleanup);

// Purpose: SCRUM-9 AC1 — every filter is sent, lists as repeated parameters.
test("builds a query from every filter", () => {
  const { query, errors } = buildVenueSearch({
    required_capacity: "80",
    location: " East ",
    date: "2026-11-14",
    slot: "PM",
    layout: "theatre",
    facility: "Projector, WiFi",
    accessibility: "Ramp access",
  });

  expect(errors).toEqual({});
  expect(new URLSearchParams(query!).getAll("facility")).toEqual(["Projector", "WiFi"]);
  expect(Object.fromEntries(new URLSearchParams(query!))).toMatchObject({
    required_capacity: "80", location: "East", date: "2026-11-14", slot: "PM", layout: "theatre", accessibility: "Ramp access",
  });
});

// Purpose: An untouched form does not search.
test("returns no query when nothing is filled in", () => {
  expect(buildVenueSearch({})).toEqual({ query: null, errors: {} });
});

// Purpose: Review focus 4 — a non-positive or non-integer capacity is reported, not sent.
test.each(["0", "abc", "2.5", "-1"])("rejects capacity %j", (value) => {
  expect(buildVenueSearch({ required_capacity: value })).toEqual({
    query: null,
    errors: { required_capacity: "Enter a whole number greater than zero." },
  });
});

// Purpose: Values outside the backend enums are dropped instead of causing a 422.
test("drops unknown slot and layout values", () => {
  expect(buildVenueSearch({ slot: "MIDNIGHT", layout: "ballroom", location: "East" }).query).toBe("location=East");
});

const venue: Venue = {
  id: "v1", name: "Riverside Hall", location: "East Wing", max_capacity: 120,
  facilities: ["Projector"], accessibility_features: ["Ramp access"], supported_layouts: ["theatre"],
  operating_slots: ["AM", "PM"], status: "available", created_at: "2026-09-13T03:00:00Z", updated_at: "2026-09-13T03:00:00Z",
};

// Purpose: SCRUM-9 AC2 — each result shows the attributes a coordinator shortlists by.
test("shows key attributes for each result", () => {
  render(<VenueResults venues={[venue]} />);

  const card = screen.getByRole("article", { name: "Riverside Hall" });
  for (const text of ["East Wing", "120", "Theatre", "Projector", "Ramp access", "AM, PM"]) {
    expect(within(card).getByText(new RegExp(text))).toBeDefined();
  }
  expect(screen.getByText("1 venue matches every filter.")).toBeDefined();
});

// Purpose: No matches is stated plainly so the coordinator can loosen filters.
test("explains when no venue matches", () => {
  render(<VenueResults venues={[]} />);

  expect(screen.getByText("No venue matches every filter. Try removing one.")).toBeDefined();
});
```

- [ ] **Step 2: Run to verify they fail**

Run: `npx vitest run __tests__/venue-search.test.tsx`
Expected: FAIL — `buildVenueSearch` not exported; results module missing.

- [ ] **Step 3: Implement**

Append to `frontend/lib/venue-form.ts`:

```ts
export interface VenueSearchInput {
  required_capacity?: string;
  location?: string;
  date?: string;
  slot?: string;
  layout?: string;
  facility?: string;
  accessibility?: string;
}

export function buildVenueSearch(input: VenueSearchInput): { query: string | null; errors: Record<string, string> } {
  const params = new URLSearchParams();
  const errors: Record<string, string> = {};
  const capacity = (input.required_capacity ?? "").trim();
  if (capacity) {
    if (/^\d+$/.test(capacity) && Number(capacity) > 0) params.set("required_capacity", String(Number(capacity)));
    else errors.required_capacity = "Enter a whole number greater than zero.";
  }
  const location = (input.location ?? "").trim();
  if (location) params.set("location", location);
  const date = (input.date ?? "").trim();
  if (/^\d{4}-\d{2}-\d{2}$/.test(date)) params.set("date", date);
  if ((SLOTS as readonly string[]).includes(input.slot ?? "")) params.set("slot", input.slot!);
  if ((ROOM_LAYOUTS as readonly string[]).includes(input.layout ?? "")) params.set("layout", input.layout!);
  for (const item of splitList(input.facility ?? "")) params.append("facility", item);
  for (const item of splitList(input.accessibility ?? "")) params.append("accessibility", item);

  if (Object.keys(errors).length) return { query: null, errors };
  const query = params.toString();
  return { query: query || null, errors };
}
```

Append to `frontend/lib/venues.ts`:

```ts
export async function searchVenues(query: string): Promise<Venue[]> {
  return (await getJson<Venue[]>(venueApiUrl, `/venues/search?${query}`)) ?? [];
}
```

Create `frontend/app/venues/search/venue-results.tsx`:

```tsx
import { layoutLabel, type Venue } from "@/lib/venues";

export function VenueResults({ venues }: { venues: Venue[] }) {
  if (venues.length === 0) {
    return <p className="rounded-2xl border border-dashed border-[#cbd7d1] bg-white px-6 py-10 text-center text-sm text-[#718078]">No venue matches every filter. Try removing one.</p>;
  }
  return (
    <div>
      <p role="status" className="mb-3 text-sm font-semibold text-[#34463f]">{venues.length} {venues.length === 1 ? "venue matches" : "venues match"} every filter.</p>
      <div className="grid gap-3 sm:grid-cols-2">
        {venues.map((venue) => (
          <article key={venue.id} aria-labelledby={`result-${venue.id}`} className="rounded-2xl border border-[#dce4e0] bg-white p-5">
            <h3 id={`result-${venue.id}`} className="text-lg font-bold text-[#1b2b25]">{venue.name}</h3>
            <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
              <dt className="text-[#718078]">Location</dt><dd className="text-[#273832]">{venue.location}</dd>
              <dt className="text-[#718078]">Capacity</dt><dd className="text-[#273832]">{venue.max_capacity} people</dd>
              <dt className="text-[#718078]">Layouts</dt><dd className="text-[#273832]">{venue.supported_layouts.map(layoutLabel).join(", ") || "None recorded"}</dd>
              <dt className="text-[#718078]">Facilities</dt><dd className="text-[#273832]">{venue.facilities.join(", ") || "None recorded"}</dd>
              <dt className="text-[#718078]">Accessibility</dt><dd className="text-[#273832]">{venue.accessibility_features.join(", ") || "None recorded"}</dd>
              <dt className="text-[#718078]">Slots</dt><dd className="text-[#273832]">{venue.operating_slots.join(", ")}</dd>
            </dl>
          </article>
        ))}
      </div>
    </div>
  );
}
```

Create `frontend/app/venues/search/page.tsx`:

```tsx
import { requireAnyRole } from "@/lib/auth";
import { buildVenueSearch, type VenueSearchInput } from "@/lib/venue-form";
import { layoutLabel, ROOM_LAYOUTS, searchVenues, SLOTS } from "@/lib/venues";
import { AppShell, workspaceLinks } from "../../components/app-shell";
import { VenueResults } from "./venue-results";

const inputClass = "mt-1 w-full rounded-xl border border-[#cfd9d4] bg-white px-3 py-2.5 text-sm text-[#273832]";
const labelClass = "block text-sm font-semibold text-[#34463f]";

function first(value: string | string[] | undefined): string {
  return Array.isArray(value) ? value[0] ?? "" : value ?? "";
}

export default async function VenueSearchPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const user = await requireAnyRole(["event_coordinator", "venue_staff"]);
  const raw = await searchParams;
  const input: VenueSearchInput = {
    required_capacity: first(raw.required_capacity),
    location: first(raw.location),
    date: first(raw.date),
    slot: first(raw.slot),
    layout: first(raw.layout),
    facility: first(raw.facility),
    accessibility: first(raw.accessibility),
  };
  const { query, errors } = buildVenueSearch(input);
  const outcome = query === null
    ? null
    : await searchVenues(query).then((venues) => ({ venues, failed: false as const })).catch(() => ({ venues: [], failed: true as const }));

  return (
    <AppShell signedIn navLinks={workspaceLinks(user.roles)}>
      <div className="mb-8">
        <p className="mb-2 text-xs font-bold uppercase tracking-[0.16em] text-[#0f6b5b]">Venue search</p>
        <h1 className="text-3xl font-bold tracking-[-0.035em] text-[#17211d] sm:text-4xl">Find a venue</h1>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-[#68776f] sm:text-base">Only venues that meet every filter are shown. Blocked venues never appear.</p>
      </div>
      <form method="get" noValidate className="mb-8 grid gap-4 rounded-2xl border border-[#dce4e0] bg-white p-6 sm:grid-cols-2 lg:grid-cols-4">
        <label className={labelClass}>Attendees<input name="required_capacity" type="number" min={1} step={1} defaultValue={input.required_capacity} className={inputClass} />{errors.required_capacity ? <span role="alert" className="mt-1 block text-xs font-normal text-[#a23939]">{errors.required_capacity}</span> : null}</label>
        <label className={labelClass}>Location<input name="location" defaultValue={input.location} className={inputClass} /></label>
        <label className={labelClass}>Date<input name="date" type="date" defaultValue={input.date} className={inputClass} /></label>
        <label className={labelClass}>Slot
          <select name="slot" defaultValue={input.slot} className={inputClass}>
            <option value="">Any slot</option>
            {SLOTS.map((slot) => <option key={slot} value={slot}>{slot}</option>)}
          </select>
        </label>
        <label className={labelClass}>Layout
          <select name="layout" defaultValue={input.layout} className={inputClass}>
            <option value="">Any layout</option>
            {ROOM_LAYOUTS.map((layout) => <option key={layout} value={layout}>{layoutLabel(layout)}</option>)}
          </select>
        </label>
        <label className={labelClass}>Required facilities<input name="facility" defaultValue={input.facility} placeholder="Projector, WiFi" className={inputClass} /></label>
        <label className={labelClass}>Accessibility needs<input name="accessibility" defaultValue={input.accessibility} placeholder="Ramp access" className={inputClass} /></label>
        <div className="flex items-end"><button type="submit" className="min-h-11 w-full rounded-xl bg-[#0f6b5b] px-5 text-sm font-bold text-white hover:bg-[#0b5b4d]">Search venues</button></div>
        <p className="text-xs text-[#718078] sm:col-span-2 lg:col-span-4">The date is recorded with your search, but date-specific bookings are not checked yet; a venue blocked as a whole is always excluded.</p>
      </form>
      {outcome === null ? (
        Object.keys(errors).length ? null : <p className="text-sm text-[#718078]">Add at least one filter to search.</p>
      ) : outcome.failed ? (
        <div role="alert" className="rounded-2xl border border-[#eccdbe] bg-[#fff8f3] px-6 py-8 text-[#793f27]">The venue service is unavailable. Start the local API on port 8004, then refresh.</div>
      ) : (
        <VenueResults venues={outcome.venues} />
      )}
    </AppShell>
  );
}
```

In `frontend/app/coordination/requests/[id]/page.tsx`, add below `<RequestDetails request={request} />`:

```tsx
      <Link
        href={`/venues/search${request.expected_attendance ? `?required_capacity=${request.expected_attendance}` : ""}`}
        className="mt-5 inline-flex min-h-11 items-center rounded-xl border border-[#cfd9d4] bg-white px-4 text-sm font-semibold text-[#0f6b5b] hover:bg-[#f4f7f5]"
      >
        Find venues for this event
      </Link>
```

In `e2e/support/venue-api.mjs`, insert **before** the `const match = …` line:

```js
  if (url.pathname === "/venues/search" && request.method === "GET") {
    const capacity = url.searchParams.get("required_capacity");
    const location = url.searchParams.get("location");
    const slot = url.searchParams.get("slot");
    const layout = url.searchParams.get("layout");
    const facilities = url.searchParams.getAll("facility").map((f) => f.toLowerCase());
    const access = url.searchParams.getAll("accessibility").map((a) => a.toLowerCase());
    return send(response, 200, [...venues.values()].filter((v) =>
      v.status === "available"
      && (!capacity || v.max_capacity >= Number(capacity))
      && (!location || v.location.toLowerCase().includes(location.toLowerCase()))
      && (!slot || v.operating_slots.includes(slot))
      && (!layout || v.supported_layouts.includes(layout))
      && facilities.every((f) => v.facilities.map((x) => x.toLowerCase()).includes(f))
      && access.every((a) => v.accessibility_features.map((x) => x.toLowerCase()).includes(a))));
  }
```

- [ ] **Step 4: Run unit tests, typecheck, lint**

Run: `npx vitest run __tests__/venue-search.test.tsx && npm test && npm run typecheck && npm run lint`
Expected: all pass; clean.

- [ ] **Step 5: Write the e2e spec** — create `frontend/e2e/venue-search.spec.ts`:

```ts
import { expect, test } from "@playwright/test";

const VENUE_API = "http://127.0.0.1:8105";

// Purpose: SCRUM-9 AC2–AC4 — results match every filter, never fall below the
// requested capacity, and exclude blocked venues.
test("coordinator filters venues by capacity and facilities", async ({ page, request }) => {
  const seed = (data: object) => request.post(`${VENUE_API}/__seed`, { data });
  await seed({ name: "Search Big Hall", location: "Search Wing", max_capacity: 300, facilities: ["Projector", "Stage"], supported_layouts: ["theatre"] });
  await seed({ name: "Search Small Room", location: "Search Wing", max_capacity: 20, facilities: ["Projector"], supported_layouts: ["boardroom"] });
  await seed({ name: "Search Closed Hall", location: "Search Wing", max_capacity: 400, facilities: ["Projector", "Stage"], status: "blocked" });

  await page.context().addCookies([{ name: "cs_access_token", value: "coordinator-session", url: "http://127.0.0.1:3100" }]);
  await page.goto("/venues/search");
  await page.getByLabel("Attendees").fill("0");
  await page.getByRole("button", { name: "Search venues" }).click();
  await expect(page.getByText("Enter a whole number greater than zero.")).toBeVisible();

  await page.getByLabel("Attendees").fill("100");
  await page.getByLabel("Location").fill("Search Wing");
  await page.getByLabel("Required facilities").fill("projector, stage");
  await page.getByRole("button", { name: "Search venues" }).click();

  await expect(page.getByRole("article", { name: "Search Big Hall" })).toBeVisible();
  await expect(page.getByRole("article", { name: "Search Small Room" })).toHaveCount(0);
  await expect(page.getByRole("article", { name: "Search Closed Hall" })).toHaveCount(0);
  await expect(page.getByText("1 venue matches every filter.")).toBeVisible();
});

// Purpose: SCRUM-27 — organisers cannot search the internal venue catalogue.
test("organisers cannot open venue search", async ({ page }) => {
  await page.context().addCookies([{ name: "cs_access_token", value: "test-session", url: "http://127.0.0.1:3100" }]);
  await page.goto("/venues/search");
  await expect(page).toHaveURL(/\/unauthorised$/);
});
```

- [ ] **Step 6: Run the e2e suite**

Run: `npm run test:e2e`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add frontend/lib frontend/app/venues/search "frontend/app/coordination/requests/[id]/page.tsx" frontend/e2e frontend/__tests__/venue-search.test.tsx
git commit -m "feat(frontend): coordinators search and filter venues (SCRUM-9)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: SCRUM-45 — Equipment catalogue for Technical Support

**Files:**
- Create: `frontend/lib/equipment.ts`, `frontend/lib/equipment-form.ts`
- Create: `frontend/app/equipment/layout.tsx`, `frontend/app/equipment/page.tsx`, `frontend/app/equipment/actions.ts`, `frontend/app/equipment/equipment-form.tsx`, `frontend/app/equipment/new/page.tsx`, `frontend/app/equipment/[id]/page.tsx`, `frontend/app/equipment/[id]/quantity-form.tsx`
- Create: `frontend/e2e/support/equipment-api.mjs`; Modify: `frontend/playwright.config.ts`
- Test: create `frontend/__tests__/equipment-form.test.ts`, `frontend/__tests__/equipment-actions.test.ts`, `frontend/e2e/equipment-catalogue.spec.ts`

**Interfaces:**
- Consumes: `getJson`, `sendJson`, `readDetail` (Task 3); `requireRole`, `workspaceLinks`.
- Produces (`lib/equipment.ts`): `OPERATIONAL_STATUSES = ["AVAILABLE","DAMAGED","UNDER_REPAIR","UNDER_MAINTENANCE","RETIRED"] as const`; `OperationalStatus`; `statusLabel(status): string` (`"Available"`, `"Damaged"`, `"Under repair"`, `"Under maintenance"`, `"Retired"`); `Equipment` `{ id, type, description: string | null, total_owned_quantity: number, home_location, operational_status, created_by: string | null, created_at, updated_at }`; `equipmentApiUrl`; `listEquipment(status?: OperationalStatus): Promise<Equipment[]>`; `getEquipment(id): Promise<Equipment | null>`.
- Produces (`lib/equipment-form.ts`): `parseQuantity(value: string): number | null` (whole number ≥ 0 else `null`); `parseEquipmentForm(fd): { payload: { type; description: string | null; total_owned_quantity: number | null; home_location; operational_status: OperationalStatus }; errors }`.
- Produces (`app/equipment/actions.ts`): `createEquipment(prev: EquipmentFormState, fd)`, `updateEquipmentQuantity(equipmentId: string, prev: EquipmentFormState, fd)`; `EquipmentFormState = { message?: string; errors?: Record<string, string>; saved?: boolean }`.
- Produces (e2e): mock equipment API on 8106 — `GET /equipment[?operational_status=]`, `POST /equipment`, `GET /equipment/:id`, `PATCH /equipment/:id/quantity`.

- [ ] **Step 1: Write the failing unit tests**

Create `__tests__/equipment-form.test.ts`:

```ts
import { expect, test } from "vitest";
import { parseEquipmentForm, parseQuantity } from "@/lib/equipment-form";
import { statusLabel } from "@/lib/equipment";

function form(fields: Record<string, string>): FormData {
  const data = new FormData();
  for (const [key, value] of Object.entries(fields)) data.set(key, value);
  return data;
}

// Purpose: SCRUM-45 AC1 — every catalogue attribute is captured.
test("parses a complete equipment record", () => {
  const { payload, errors } = parseEquipmentForm(form({
    type: "Wireless microphone", description: "  Handheld  ", total_owned_quantity: "12",
    home_location: "Store B", operational_status: "UNDER_MAINTENANCE",
  }));

  expect(errors).toEqual({});
  expect(payload).toEqual({
    type: "Wireless microphone", description: "Handheld", total_owned_quantity: 12,
    home_location: "Store B", operational_status: "UNDER_MAINTENANCE",
  });
});

// Purpose: Review focus 4 — quantity is a whole number, zero allowed (all retired).
test("accepts zero and rejects non-whole quantities", () => {
  expect(parseQuantity("0")).toBe(0);
  for (const bad of ["", "abc", "-1", "2.5"]) expect(parseQuantity(bad)).toBeNull();
});

// Purpose: Type and home location are required; blank description is stored as null.
test("reports missing fields and defaults the status", () => {
  const { payload, errors } = parseEquipmentForm(form({ total_owned_quantity: "x", operational_status: "LOST" }));

  expect(errors).toEqual({
    type: "Enter the equipment type.",
    home_location: "Enter the home location.",
    total_owned_quantity: "Enter a whole number of zero or more.",
  });
  expect(payload.description).toBeNull();
  expect(payload.operational_status).toBe("AVAILABLE");
});

// Purpose: Statuses read as words, not enum constants.
test("labels every operational status", () => {
  expect(statusLabel("UNDER_REPAIR")).toBe("Under repair");
  expect(statusLabel("AVAILABLE")).toBe("Available");
});
```

Create `__tests__/equipment-actions.test.ts`:

```ts
import { beforeEach, expect, test, vi } from "vitest";

const navigation = vi.hoisted(() => ({ redirect: vi.fn(), revalidatePath: vi.fn() }));
vi.mock("next/navigation", () => ({ redirect: navigation.redirect }));
vi.mock("next/cache", () => ({ revalidatePath: navigation.revalidatePath }));
vi.mock("@/lib/auth", () => ({
  requireAccessToken: async () => "valid-token",
  requireRole: async () => ({ id: "tech-1", email: "tech@example.com", role: "technical_support", roles: ["technical_support"] }),
}));

import { createEquipment, updateEquipmentQuantity } from "@/app/equipment/actions";

function form(fields: Record<string, string>): FormData {
  const data = new FormData();
  for (const [key, value] of Object.entries(fields)) data.set(key, value);
  return data;
}

beforeEach(() => {
  vi.restoreAllMocks();
  navigation.redirect.mockReset();
  navigation.revalidatePath.mockReset();
});

// Purpose: SCRUM-45 AC1 — creating posts the record and opens its detail page.
test("creates equipment and opens its record", async () => {
  navigation.redirect.mockImplementation(() => { throw new Error("NEXT_REDIRECT"); });
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 201, json: async () => ({ id: "eq-1" }) });
  vi.stubGlobal("fetch", fetchMock);

  await expect(createEquipment({}, form({ type: "Projector", total_owned_quantity: "3", home_location: "Store A", operational_status: "AVAILABLE" }))).rejects.toThrow("NEXT_REDIRECT");

  expect(fetchMock.mock.calls[0][0]).toBe("http://127.0.0.1:8002/equipment");
  expect(navigation.redirect).toHaveBeenCalledWith("/equipment/eq-1");
});

// Purpose: Invalid input never reaches the API.
test("does not call the API when the form is invalid", async () => {
  const fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);

  const state = await createEquipment({}, form({ type: "", total_owned_quantity: "-1", home_location: "" }));

  expect(state.message).toBe("Check the highlighted fields.");
  expect(fetchMock).not.toHaveBeenCalled();
});

// Purpose: SCRUM-45 AC2 — updating the owned quantity patches only the quantity.
test("updates the total owned quantity", async () => {
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200 });
  vi.stubGlobal("fetch", fetchMock);

  const state = await updateEquipmentQuantity("eq-1", {}, form({ total_owned_quantity: "9" }));

  expect(fetchMock.mock.calls[0][0]).toBe("http://127.0.0.1:8002/equipment/eq-1/quantity");
  expect(fetchMock.mock.calls[0][1]).toMatchObject({ method: "PATCH", body: JSON.stringify({ total_owned_quantity: 9 }) });
  expect(state).toEqual({ saved: true, message: "Quantity updated." });
  expect(navigation.revalidatePath).toHaveBeenCalledWith("/equipment/eq-1");
});

// Purpose: Review focus 4 — a bad quantity is reported inline.
test("rejects a non-whole quantity", async () => {
  vi.stubGlobal("fetch", vi.fn());

  const state = await updateEquipmentQuantity("eq-1", {}, form({ total_owned_quantity: "2.5" }));

  expect(state).toEqual({ message: "Enter a whole number of zero or more." });
});

// Purpose: Equipment removed since the page loaded is explained.
test("explains missing equipment", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 404 }));

  const state = await updateEquipmentQuantity("eq-1", {}, form({ total_owned_quantity: "4" }));

  expect(state).toEqual({ message: "This equipment record no longer exists." });
});
```

- [ ] **Step 2: Run to verify they fail**

Run: `npx vitest run __tests__/equipment-form.test.ts __tests__/equipment-actions.test.ts`
Expected: FAIL — modules missing.

- [ ] **Step 3: Implement libraries and actions**

Create `frontend/lib/equipment.ts`:

```ts
import { getJson } from "./api";

export const OPERATIONAL_STATUSES = ["AVAILABLE", "DAMAGED", "UNDER_REPAIR", "UNDER_MAINTENANCE", "RETIRED"] as const;
export type OperationalStatus = (typeof OPERATIONAL_STATUSES)[number];

const LABELS: Record<OperationalStatus, string> = {
  AVAILABLE: "Available",
  DAMAGED: "Damaged",
  UNDER_REPAIR: "Under repair",
  UNDER_MAINTENANCE: "Under maintenance",
  RETIRED: "Retired",
};

export function statusLabel(status: OperationalStatus): string {
  return LABELS[status];
}

export function isOperationalStatus(value: string): value is OperationalStatus {
  return (OPERATIONAL_STATUSES as readonly string[]).includes(value);
}

export interface Equipment {
  id: string;
  type: string;
  description: string | null;
  total_owned_quantity: number;
  home_location: string;
  operational_status: OperationalStatus;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

export const equipmentApiUrl = process.env.EQUIPMENT_API_URL ?? "http://127.0.0.1:8002";

export async function listEquipment(status?: OperationalStatus): Promise<Equipment[]> {
  const query = status ? `?operational_status=${status}` : "";
  return (await getJson<Equipment[]>(equipmentApiUrl, `/equipment${query}`)) ?? [];
}

export async function getEquipment(id: string): Promise<Equipment | null> {
  return getJson<Equipment>(equipmentApiUrl, `/equipment/${encodeURIComponent(id)}`);
}
```

Create `frontend/lib/equipment-form.ts`:

```ts
import { isOperationalStatus, type OperationalStatus } from "./equipment";

export function parseQuantity(value: string): number | null {
  const text = value.trim();
  return /^\d+$/.test(text) ? Number(text) : null;
}

export function parseEquipmentForm(formData: FormData) {
  const text = (field: string) => String(formData.get(field) ?? "").trim();
  const status = text("operational_status");
  const payload = {
    type: text("type"),
    description: text("description") || null,
    total_owned_quantity: parseQuantity(text("total_owned_quantity")),
    home_location: text("home_location"),
    operational_status: (isOperationalStatus(status) ? status : "AVAILABLE") as OperationalStatus,
  };
  const errors: Record<string, string> = {};
  if (!payload.type) errors.type = "Enter the equipment type.";
  if (!payload.home_location) errors.home_location = "Enter the home location.";
  if (payload.total_owned_quantity === null) errors.total_owned_quantity = "Enter a whole number of zero or more.";
  return { payload, errors };
}
```

Create `frontend/app/equipment/actions.ts`:

```ts
"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { sendJson } from "@/lib/api";
import { requireRole } from "@/lib/auth";
import { equipmentApiUrl } from "@/lib/equipment";
import { parseEquipmentForm, parseQuantity } from "@/lib/equipment-form";

export interface EquipmentFormState {
  message?: string;
  errors?: Record<string, string>;
  saved?: boolean;
}

function failure(status: number, fallback: string): EquipmentFormState {
  return {
    message:
      status === 403
        ? "Only Technical Support Staff can change equipment."
        : status === 404
          ? "This equipment record no longer exists."
          : fallback,
  };
}

export async function createEquipment(previousState: EquipmentFormState, formData: FormData): Promise<EquipmentFormState> {
  void previousState;
  const { payload, errors } = parseEquipmentForm(formData);
  if (Object.keys(errors).length) return { message: "Check the highlighted fields.", errors };

  await requireRole("technical_support");
  let response: Response;
  try {
    response = await sendJson(equipmentApiUrl, "/equipment", "POST", payload);
  } catch {
    return { message: "The equipment could not be saved. Please try again." };
  }
  if (response.status === 401) redirect("/auth");
  if (!response.ok) return failure(response.status, "The equipment could not be saved. Please try again.");
  const created = (await response.json()) as { id: string };
  revalidatePath("/equipment");
  redirect(`/equipment/${created.id}`);
}

export async function updateEquipmentQuantity(
  equipmentId: string,
  previousState: EquipmentFormState,
  formData: FormData,
): Promise<EquipmentFormState> {
  void previousState;
  const quantity = parseQuantity(String(formData.get("total_owned_quantity") ?? ""));
  if (quantity === null) return { message: "Enter a whole number of zero or more." };

  await requireRole("technical_support");
  let response: Response;
  try {
    response = await sendJson(equipmentApiUrl, `/equipment/${encodeURIComponent(equipmentId)}/quantity`, "PATCH", { total_owned_quantity: quantity });
  } catch {
    return { message: "The quantity could not be updated. Please try again." };
  }
  if (response.status === 401) redirect("/auth");
  if (!response.ok) return failure(response.status, "The quantity could not be updated. Please try again.");
  revalidatePath("/equipment");
  revalidatePath(`/equipment/${equipmentId}`);
  return { saved: true, message: "Quantity updated." };
}
```

- [ ] **Step 4: Implement pages and forms**

Create `frontend/app/equipment/layout.tsx`:

```tsx
import type { ReactNode } from "react";
import { requireRole } from "@/lib/auth";

export default async function EquipmentLayout({ children }: { children: ReactNode }) {
  await requireRole("technical_support");
  return children;
}
```

Create `frontend/app/equipment/equipment-form.tsx`:

```tsx
"use client";

import { useActionState } from "react";
import { OPERATIONAL_STATUSES, statusLabel } from "@/lib/equipment";
import { createEquipment, type EquipmentFormState } from "./actions";

const initialState: EquipmentFormState = {};
const inputClass = "mt-2 w-full rounded-xl border border-[#cfd9d4] bg-white px-4 py-3 text-sm text-[#273832]";
const labelClass = "block text-sm font-semibold text-[#34463f]";

function FieldError({ message }: { message?: string }) {
  return message ? <p className="mt-1 text-sm text-[#a23939]">{message}</p> : null;
}

export function EquipmentForm() {
  const [state, formAction, isPending] = useActionState(createEquipment, initialState);
  const errors = state.errors ?? {};
  return (
    <form action={formAction} noValidate className="grid gap-5 rounded-2xl border border-[#dce4e0] bg-white p-6 sm:grid-cols-2 sm:p-8">
      <label className={labelClass}>Equipment type<input name="type" maxLength={120} className={inputClass} /><FieldError message={errors.type} /></label>
      <label className={labelClass}>Home location<input name="home_location" maxLength={120} className={inputClass} /><FieldError message={errors.home_location} /></label>
      <label className={labelClass}>Total owned quantity<input name="total_owned_quantity" type="number" min={0} step={1} className={inputClass} /><FieldError message={errors.total_owned_quantity} /></label>
      <label className={labelClass}>Operational status
        <select name="operational_status" defaultValue="AVAILABLE" className={inputClass}>
          {OPERATIONAL_STATUSES.map((status) => <option key={status} value={status}>{statusLabel(status)}</option>)}
        </select>
      </label>
      <label className={`${labelClass} sm:col-span-2`}>Description<textarea name="description" rows={3} className={inputClass} /></label>
      {state.message ? <p role="alert" className="rounded-xl bg-[#fff4f3] px-4 py-3 text-sm text-[#8e3d35] sm:col-span-2">{state.message}</p> : null}
      <div className="sm:col-span-2"><button type="submit" disabled={isPending} className="min-h-11 rounded-xl bg-[#0f6b5b] px-5 text-sm font-bold text-white hover:bg-[#0b5b4d] disabled:opacity-60">{isPending ? "Saving…" : "Add equipment"}</button></div>
    </form>
  );
}
```

Create `frontend/app/equipment/new/page.tsx`:

```tsx
import Link from "next/link";
import { requireRole } from "@/lib/auth";
import { AppShell, workspaceLinks } from "../../components/app-shell";
import { EquipmentForm } from "../equipment-form";

export default async function NewEquipmentPage() {
  const user = await requireRole("technical_support");
  return (
    <AppShell signedIn navLinks={workspaceLinks(user.roles)}>
      <div className="mx-auto max-w-3xl">
        <Link href="/equipment" className="mb-5 inline-block text-sm font-semibold text-[#0f6b5b] hover:underline">← Back to equipment</Link>
        <h1 className="mb-6 text-3xl font-bold tracking-[-0.035em] text-[#17211d]">Add equipment</h1>
        <EquipmentForm />
      </div>
    </AppShell>
  );
}
```

Create `frontend/app/equipment/page.tsx`:

```tsx
import Link from "next/link";
import { requireRole } from "@/lib/auth";
import { isOperationalStatus, listEquipment, OPERATIONAL_STATUSES, statusLabel } from "@/lib/equipment";
import { AppShell, workspaceLinks } from "../components/app-shell";

export default async function EquipmentPage({ searchParams }: { searchParams: Promise<{ status?: string }> }) {
  const user = await requireRole("technical_support");
  const requested = (await searchParams).status ?? "";
  const status = isOperationalStatus(requested) ? requested : undefined;
  const result = await listEquipment(status).then((items) => ({ items, failed: false as const })).catch(() => ({ items: [], failed: true as const }));

  return (
    <AppShell signedIn navLinks={workspaceLinks(user.roles)}>
      <div className="mb-8 flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="mb-2 text-xs font-bold uppercase tracking-[0.16em] text-[#0f6b5b]">Technical support workspace</p>
          <h1 className="text-3xl font-bold tracking-[-0.035em] text-[#17211d] sm:text-4xl">Equipment catalogue</h1>
        </div>
        <Link href="/equipment/new" className="inline-flex min-h-11 items-center justify-center rounded-xl bg-[#0f6b5b] px-5 text-sm font-bold text-white hover:bg-[#0b5b4d]">+ Add equipment</Link>
      </div>
      <form method="get" className="mb-5 flex items-end gap-3">
        <label className="text-sm font-semibold text-[#34463f]">Show
          <select name="status" defaultValue={status ?? ""} className="mt-1 block min-h-11 rounded-xl border border-[#cfd9d4] bg-white px-3 text-sm">
            <option value="">All statuses</option>
            {OPERATIONAL_STATUSES.map((value) => <option key={value} value={value}>{statusLabel(value)}</option>)}
          </select>
        </label>
        <button type="submit" className="min-h-11 rounded-xl border border-[#cfd9d4] bg-white px-4 text-sm font-semibold text-[#0f6b5b]">Filter</button>
      </form>
      {result.failed ? (
        <div role="alert" className="rounded-2xl border border-[#eccdbe] bg-[#fff8f3] px-6 py-8 text-[#793f27]">The equipment service is unavailable. Start the local API on port 8002, then refresh.</div>
      ) : result.items.length === 0 ? (
        <p className="rounded-2xl border border-dashed border-[#cbd7d1] bg-white px-6 py-14 text-center text-sm text-[#718078]">No equipment matches. Add equipment to the catalogue.</p>
      ) : (
        <div className="space-y-3">
          {result.items.map((item) => (
            <article key={item.id} aria-labelledby={`equipment-${item.id}`} className="flex flex-col gap-2 rounded-2xl border border-[#dce4e0] bg-white p-5 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h2 id={`equipment-${item.id}`} className="text-lg font-bold text-[#1b2b25]">{item.type}</h2>
                <p className="text-sm text-[#68776f]">{item.total_owned_quantity} owned · {item.home_location} · {statusLabel(item.operational_status)}</p>
              </div>
              <Link href={`/equipment/${item.id}`} className="text-sm font-semibold text-[#0f6b5b] hover:underline">Open {item.type}</Link>
            </article>
          ))}
        </div>
      )}
    </AppShell>
  );
}
```

Create `frontend/app/equipment/[id]/quantity-form.tsx`:

```tsx
"use client";

import { useActionState } from "react";
import { updateEquipmentQuantity, type EquipmentFormState } from "../actions";

const initialState: EquipmentFormState = {};

export function QuantityForm({ equipmentId, quantity }: { equipmentId: string; quantity: number }) {
  const [state, formAction, isPending] = useActionState(updateEquipmentQuantity.bind(null, equipmentId), initialState);
  return (
    <form action={formAction} noValidate className="flex flex-wrap items-end gap-3">
      <label className="text-sm font-semibold text-[#34463f]">Total owned quantity
        <input name="total_owned_quantity" type="number" min={0} step={1} defaultValue={quantity} className="mt-1 block min-h-11 w-40 rounded-xl border border-[#cfd9d4] bg-white px-3 text-sm" />
      </label>
      <button type="submit" disabled={isPending} className="min-h-11 rounded-xl bg-[#0f6b5b] px-4 text-sm font-semibold text-white disabled:opacity-60">{isPending ? "Saving…" : "Update quantity"}</button>
      {state.message ? <p role={state.saved ? "status" : "alert"} className={`w-full rounded-lg px-3 py-2 text-sm ${state.saved ? "bg-[#e7f5ed] text-[#145d40]" : "bg-[#fff0f0] text-[#a23939]"}`}>{state.message}</p> : null}
    </form>
  );
}
```

Create `frontend/app/equipment/[id]/page.tsx`:

```tsx
import Link from "next/link";
import { requireRole } from "@/lib/auth";
import { formatDateTime } from "@/lib/event-requests";
import { getEquipment, statusLabel } from "@/lib/equipment";
import { AppShell, workspaceLinks } from "../../components/app-shell";
import { QuantityForm } from "./quantity-form";

export default async function EquipmentDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const user = await requireRole("technical_support");
  const { id } = await params;
  const result = await getEquipment(id).then((item) => ({ item, failed: false as const })).catch(() => ({ item: null, failed: true as const }));

  return (
    <AppShell signedIn navLinks={workspaceLinks(user.roles)}>
      <div className="mx-auto max-w-4xl space-y-5">
        <Link href="/equipment" className="inline-block text-sm font-semibold text-[#0f6b5b] hover:underline">← Back to equipment</Link>
        {result.failed ? (
          <div role="alert" className="rounded-2xl border border-[#eccdbe] bg-[#fff8f3] px-6 py-8 text-[#793f27]">The equipment service is unavailable. Start the local API on port 8002, then refresh.</div>
        ) : !result.item ? (
          <h1 className="text-xl font-bold">Equipment not found</h1>
        ) : (
          <>
            <section className="rounded-2xl border border-[#dce4e0] bg-white p-6 sm:p-7">
              <h1 className="text-2xl font-bold text-[#17211d]">{result.item.type}</h1>
              <dl className="mt-5 grid gap-4 sm:grid-cols-2">
                <div><dt className="text-xs font-bold uppercase tracking-wide text-[#718078]">Home location</dt><dd className="mt-1 text-sm text-[#273832]">{result.item.home_location}</dd></div>
                <div><dt className="text-xs font-bold uppercase tracking-wide text-[#718078]">Operational status</dt><dd className="mt-1 text-sm text-[#273832]">{statusLabel(result.item.operational_status)}</dd></div>
                <div><dt className="text-xs font-bold uppercase tracking-wide text-[#718078]">Total owned</dt><dd className="mt-1 text-sm text-[#273832]">{result.item.total_owned_quantity}</dd></div>
                <div><dt className="text-xs font-bold uppercase tracking-wide text-[#718078]">Last updated</dt><dd className="mt-1 text-sm text-[#273832]">{formatDateTime(result.item.updated_at)}</dd></div>
                <div className="sm:col-span-2"><dt className="text-xs font-bold uppercase tracking-wide text-[#718078]">Description</dt><dd className="mt-1 whitespace-pre-wrap text-sm text-[#273832]">{result.item.description ?? "No description"}</dd></div>
              </dl>
            </section>
            <section aria-labelledby="quantity-heading" className="rounded-2xl border border-[#dce4e0] bg-white p-6 sm:p-7">
              <h2 id="quantity-heading" className="mb-4 text-lg font-bold text-[#17211d]">Quantity</h2>
              <QuantityForm equipmentId={result.item.id} quantity={result.item.total_owned_quantity} />
            </section>
          </>
        )}
      </div>
    </AppShell>
  );
}
```

- [ ] **Step 5: Run unit tests, typecheck, lint**

Run: `npx vitest run __tests__/equipment-form.test.ts __tests__/equipment-actions.test.ts && npm run typecheck && npm run lint`
Expected: pass; clean.

- [ ] **Step 6: Mock equipment API and Playwright wiring**

Create `frontend/e2e/support/equipment-api.mjs`:

```js
import { randomUUID } from "node:crypto";
import { createServer } from "node:http";

const items = new Map();
const history = [];
let nextHistoryId = 1;
const SESSIONS = {
  "test-session": { id: "playwright-user", role: "event_organiser" },
  "tech-session": { id: "playwright-tech", role: "technical_support" },
};

function send(response, status, body) {
  response.writeHead(status, { "Content-Type": "application/json" });
  response.end(JSON.stringify(body));
}

async function readJson(request) {
  const chunks = [];
  for await (const chunk of request) chunks.push(chunk);
  return chunks.length ? JSON.parse(Buffer.concat(chunks).toString("utf8")) : {};
}

createServer(async (request, response) => {
  const url = new URL(request.url ?? "/", "http://127.0.0.1");
  if (request.method === "GET" && url.pathname === "/health") return send(response, 200, { status: "ok" });
  const user = SESSIONS[(request.headers.authorization ?? "").replace(/^Bearer /, "")];
  if (!user) return send(response, 401, { detail: "Authentication required" });
  const staffOnly = () => user.role !== "technical_support" && (send(response, 403, { detail: "Insufficient permissions" }), true);

  if (url.pathname === "/equipment" && request.method === "GET") {
    const status = url.searchParams.get("operational_status");
    return send(response, 200, [...items.values()].filter((item) => !status || item.operational_status === status));
  }
  if (url.pathname === "/equipment" && request.method === "POST") {
    if (staffOnly()) return;
    const body = await readJson(request);
    if (!body.type || !body.home_location || !Number.isInteger(body.total_owned_quantity) || body.total_owned_quantity < 0) {
      return send(response, 422, { detail: "Invalid equipment" });
    }
    const now = new Date().toISOString();
    const item = { description: null, operational_status: "AVAILABLE", ...body, id: randomUUID(), created_by: user.id, created_at: now, updated_at: now };
    items.set(item.id, item);
    history.push({ id: nextHistoryId++, equipment_id: item.id, old_status: null, new_status: item.operational_status, reason: "Created", changed_by: user.id, changed_at: now });
    return send(response, 201, item);
  }

  const match = url.pathname.match(/^\/equipment\/([^/]+)(\/quantity|\/status|\/status\/history)?$/);
  const item = match ? items.get(decodeURIComponent(match[1])) : undefined;
  if (!match) return send(response, 404, { detail: "Not found" });
  if (!item) return send(response, 404, { detail: "Equipment not found" });
  const suffix = match[2] ?? "";

  if (suffix === "" && request.method === "GET") return send(response, 200, item);
  if (suffix === "/quantity" && request.method === "PATCH") {
    if (staffOnly()) return;
    const body = await readJson(request);
    const updated = { ...item, total_owned_quantity: body.total_owned_quantity, updated_at: new Date().toISOString() };
    items.set(item.id, updated);
    return send(response, 200, updated);
  }
  send(response, 405, { detail: "Method not allowed" });
}).listen(8106, "127.0.0.1");
```

In `frontend/playwright.config.ts` add a `webServer` entry for `node e2e/support/equipment-api.mjs` with `url: "http://127.0.0.1:8106/health"` (same shape as the venue entry) and `EQUIPMENT_API_URL: "http://127.0.0.1:8106",` to the Next server `env`.

- [ ] **Step 7: Write the e2e spec** — create `frontend/e2e/equipment-catalogue.spec.ts`:

```ts
import { expect, test } from "@playwright/test";

// Purpose: SCRUM-45 AC1–AC3 — technical support add equipment, see its
// attributes, and update the owned quantity.
test("technical support add equipment and update its quantity", async ({ page }) => {
  await page.goto("/auth");
  await page.getByLabel("Email").fill("tech@example.com");
  await page.getByLabel("Password").fill("test-password-123");
  await page.getByRole("button", { name: "Log in", exact: true }).last().click();
  await expect(page).toHaveURL(/\/equipment$/);

  await page.getByRole("link", { name: "+ Add equipment" }).click();
  await page.getByLabel("Equipment type").fill("Catalogue Projector");
  await page.getByLabel("Home location").fill("Store A");
  await page.getByLabel("Total owned quantity").fill("4");
  await page.getByLabel("Description").fill("4K laser projector");
  await page.getByRole("button", { name: "Add equipment" }).click();

  await expect(page.getByRole("heading", { name: "Catalogue Projector" })).toBeVisible();
  await expect(page.getByText("4K laser projector")).toBeVisible();

  await page.getByLabel("Total owned quantity").fill("-1");
  await page.getByRole("button", { name: "Update quantity" }).click();
  await expect(page.getByText("Enter a whole number of zero or more.")).toBeVisible();

  await page.getByLabel("Total owned quantity").fill("6");
  await page.getByRole("button", { name: "Update quantity" }).click();
  await expect(page.getByText("Quantity updated.")).toBeVisible();
  await page.reload();
  await expect(page.getByLabel("Total owned quantity")).toHaveValue("6");
});

// Purpose: SCRUM-27 — the equipment workspace is closed to other roles.
test("organisers cannot open the equipment workspace", async ({ page }) => {
  await page.context().addCookies([{ name: "cs_access_token", value: "test-session", url: "http://127.0.0.1:3100" }]);
  await page.goto("/equipment");
  await expect(page).toHaveURL(/\/unauthorised$/);
});
```

- [ ] **Step 8: Run the e2e suite**

Run: `npm run test:e2e`
Expected: all pass.

- [ ] **Step 9: Commit**

```bash
git add frontend/lib/equipment.ts frontend/lib/equipment-form.ts frontend/app/equipment frontend/e2e frontend/playwright.config.ts frontend/__tests__/equipment-form.test.ts frontend/__tests__/equipment-actions.test.ts
git commit -m "feat(frontend): technical support maintain the equipment catalogue (SCRUM-45)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: SCRUM-16 — Equipment status changes and history

**Files:**
- Modify: `frontend/lib/equipment.ts` (status + history reads), `frontend/app/equipment/actions.ts` (`changeEquipmentStatus`), `frontend/app/equipment/[id]/page.tsx` (status panel + history), `frontend/e2e/support/equipment-api.mjs` (status routes)
- Create: `frontend/app/equipment/[id]/status-form.tsx`, `frontend/app/equipment/[id]/status-history.tsx`
- Test: extend `frontend/__tests__/equipment-actions.test.ts`; create `frontend/__tests__/equipment-status.test.tsx`, `frontend/e2e/equipment-status.spec.ts`

**Interfaces:**
- Consumes: Task 7's `OPERATIONAL_STATUSES`, `statusLabel`, `isOperationalStatus`, `equipmentApiUrl`, `EquipmentFormState`.
- Produces (`lib/equipment.ts`): `EquipmentStatus { equipment_id: string; operational_status: OperationalStatus; available: boolean; available_quantity: number }`; `StatusHistoryEntry { id: number; equipment_id: string; old_status: OperationalStatus | null; new_status: OperationalStatus; reason: string | null; changed_by: string; changed_at: string }`; `getEquipmentStatus(id): Promise<EquipmentStatus | null>`; `getStatusHistory(id): Promise<StatusHistoryEntry[]>`.
- Produces (`actions.ts`): `changeEquipmentStatus(equipmentId: string, currentStatus: OperationalStatus, prev: EquipmentFormState, fd): Promise<EquipmentFormState>` — PATCH `/equipment/{id}/status` with `{ new_status, reason }`.

- [ ] **Step 1: Write the failing tests**

Append to `__tests__/equipment-actions.test.ts` (and add `changeEquipmentStatus` to its import):

```ts
// Purpose: SCRUM-16 AC1 — marking equipment damaged sends the status and reason.
test("changes the operational status with a reason", async () => {
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200 });
  vi.stubGlobal("fetch", fetchMock);

  const state = await changeEquipmentStatus("eq-1", "AVAILABLE", {}, form({ new_status: "DAMAGED", reason: "  Cracked lens " }));

  expect(fetchMock.mock.calls[0][0]).toBe("http://127.0.0.1:8002/equipment/eq-1/status");
  expect(fetchMock.mock.calls[0][1]).toMatchObject({ method: "PATCH", body: JSON.stringify({ new_status: "DAMAGED", reason: "Cracked lens" }) });
  expect(state).toEqual({ saved: true, message: "Status changed to Damaged." });
});

// Purpose: A status change must actually change something, and use a known status.
test("refuses an unchanged or unknown status", async () => {
  const fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);

  expect(await changeEquipmentStatus("eq-1", "DAMAGED", {}, form({ new_status: "DAMAGED" }))).toEqual({ message: "Choose a different status." });
  expect(await changeEquipmentStatus("eq-1", "DAMAGED", {}, form({ new_status: "LOST" }))).toEqual({ message: "Choose a different status." });
  expect(fetchMock).not.toHaveBeenCalled();
});

// Purpose: The backend's 255-character reason limit is enforced before sending.
test("rejects an overlong reason", async () => {
  vi.stubGlobal("fetch", vi.fn());

  const state = await changeEquipmentStatus("eq-1", "AVAILABLE", {}, form({ new_status: "DAMAGED", reason: "x".repeat(256) }));

  expect(state).toEqual({ message: "Keep the reason to 255 characters or fewer." });
});
```

Create `__tests__/equipment-status.test.tsx`:

```tsx
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

vi.mock("@/app/equipment/actions", () => ({ changeEquipmentStatus: vi.fn(), updateEquipmentQuantity: vi.fn(), createEquipment: vi.fn() }));

import { StatusForm } from "@/app/equipment/[id]/status-form";
import { StatusHistory } from "@/app/equipment/[id]/status-history";

afterEach(cleanup);

// Purpose: The status picker never offers the status the equipment already has.
test("offers every status except the current one", () => {
  render(<StatusForm equipmentId="eq-1" currentStatus="AVAILABLE" />);

  const options = within(screen.getByRole("combobox", { name: "New status" })).getAllByRole("option");
  expect(options.map((option) => option.textContent)).toEqual(["Damaged", "Under repair", "Under maintenance", "Retired"]);
});

// Purpose: SCRUM-16 AC3 — each change shows who made it and when.
test("lists each change with who and when", () => {
  render(
    <StatusHistory
      entries={[{ id: 2, equipment_id: "eq-1", old_status: "AVAILABLE", new_status: "DAMAGED", reason: "Dropped", changed_by: "tech-1", changed_at: "2026-09-20T02:00:00Z" }]}
    />,
  );

  const item = screen.getByRole("listitem");
  expect(item.textContent).toContain("Available → Damaged");
  expect(item.textContent).toContain("Dropped");
  expect(item.textContent).toContain("tech-1");
  expect(item.textContent).toMatch(/20 Sept? 2026/);
});

// Purpose: An empty history explains itself.
test("explains an empty history", () => {
  render(<StatusHistory entries={[]} />);

  expect(screen.getByText("No status changes recorded yet.")).toBeDefined();
});
```

- [ ] **Step 2: Run to verify they fail**

Run: `npx vitest run __tests__/equipment-actions.test.ts __tests__/equipment-status.test.tsx`
Expected: FAIL — `changeEquipmentStatus` undefined; modules missing.

- [ ] **Step 3: Implement**

Append to `frontend/lib/equipment.ts`:

```ts
export interface EquipmentStatus {
  equipment_id: string;
  operational_status: OperationalStatus;
  available: boolean;
  available_quantity: number;
}

export interface StatusHistoryEntry {
  id: number;
  equipment_id: string;
  old_status: OperationalStatus | null;
  new_status: OperationalStatus;
  reason: string | null;
  changed_by: string;
  changed_at: string;
}

export async function getEquipmentStatus(id: string): Promise<EquipmentStatus | null> {
  return getJson<EquipmentStatus>(equipmentApiUrl, `/equipment/${encodeURIComponent(id)}/status`);
}

export async function getStatusHistory(id: string): Promise<StatusHistoryEntry[]> {
  return (await getJson<StatusHistoryEntry[]>(equipmentApiUrl, `/equipment/${encodeURIComponent(id)}/status/history`)) ?? [];
}
```

Append to `frontend/app/equipment/actions.ts` (import `isOperationalStatus`, `statusLabel`, `type OperationalStatus` from `@/lib/equipment`):

```ts
export async function changeEquipmentStatus(
  equipmentId: string,
  currentStatus: OperationalStatus,
  previousState: EquipmentFormState,
  formData: FormData,
): Promise<EquipmentFormState> {
  void previousState;
  const newStatus = String(formData.get("new_status") ?? "");
  if (!isOperationalStatus(newStatus) || newStatus === currentStatus) return { message: "Choose a different status." };
  const reason = String(formData.get("reason") ?? "").trim();
  if (reason.length > 255) return { message: "Keep the reason to 255 characters or fewer." };

  await requireRole("technical_support");
  let response: Response;
  try {
    response = await sendJson(equipmentApiUrl, `/equipment/${encodeURIComponent(equipmentId)}/status`, "PATCH", { new_status: newStatus, reason: reason || null });
  } catch {
    return { message: "The status could not be changed. Please try again." };
  }
  if (response.status === 401) redirect("/auth");
  if (!response.ok) return failure(response.status, "The status could not be changed. Please try again.");
  revalidatePath("/equipment");
  revalidatePath(`/equipment/${equipmentId}`);
  return { saved: true, message: `Status changed to ${statusLabel(newStatus)}.` };
}
```

Create `frontend/app/equipment/[id]/status-form.tsx`:

```tsx
"use client";

import { useActionState } from "react";
import { OPERATIONAL_STATUSES, statusLabel, type OperationalStatus } from "@/lib/equipment";
import { changeEquipmentStatus, type EquipmentFormState } from "../actions";

const initialState: EquipmentFormState = {};

export function StatusForm({ equipmentId, currentStatus }: { equipmentId: string; currentStatus: OperationalStatus }) {
  const [state, formAction, isPending] = useActionState(changeEquipmentStatus.bind(null, equipmentId, currentStatus), initialState);
  const choices = OPERATIONAL_STATUSES.filter((status) => status !== currentStatus);
  return (
    <form action={formAction} className="grid gap-4 sm:grid-cols-[auto_1fr_auto] sm:items-end">
      <label className="text-sm font-semibold text-[#34463f]">New status
        <select name="new_status" defaultValue={choices[0]} className="mt-1 block min-h-11 rounded-xl border border-[#cfd9d4] bg-white px-3 text-sm">
          {choices.map((status) => <option key={status} value={status}>{statusLabel(status)}</option>)}
        </select>
      </label>
      <label className="text-sm font-semibold text-[#34463f]">Reason (optional)
        <input name="reason" maxLength={255} className="mt-1 block min-h-11 w-full rounded-xl border border-[#cfd9d4] bg-white px-3 text-sm" />
      </label>
      <button type="submit" disabled={isPending} className="min-h-11 rounded-xl bg-[#0f6b5b] px-4 text-sm font-semibold text-white disabled:opacity-60">{isPending ? "Saving…" : "Change status"}</button>
      {state.message ? <p role={state.saved ? "status" : "alert"} className={`rounded-lg px-3 py-2 text-sm sm:col-span-3 ${state.saved ? "bg-[#e7f5ed] text-[#145d40]" : "bg-[#fff0f0] text-[#a23939]"}`}>{state.message}</p> : null}
    </form>
  );
}
```

Create `frontend/app/equipment/[id]/status-history.tsx`:

```tsx
import { formatDateTime } from "@/lib/event-requests";
import { statusLabel, type StatusHistoryEntry } from "@/lib/equipment";

export function StatusHistory({ entries }: { entries: StatusHistoryEntry[] }) {
  if (entries.length === 0) return <p className="text-sm text-[#718078]">No status changes recorded yet.</p>;
  return (
    <ol className="space-y-3">
      {entries.map((entry) => (
        <li key={entry.id} className="rounded-xl border border-[#edf1ef] px-4 py-3 text-sm text-[#273832]">
          <p className="font-semibold">{entry.old_status ? `${statusLabel(entry.old_status)} → ` : ""}{statusLabel(entry.new_status)}</p>
          {entry.reason ? <p className="mt-1 text-[#52635c]">{entry.reason}</p> : null}
          <p className="mt-1 text-xs text-[#718078]">By {entry.changed_by} · {formatDateTime(entry.changed_at)}</p>
        </li>
      ))}
    </ol>
  );
}
```

In `frontend/app/equipment/[id]/page.tsx`: import `getEquipmentStatus`, `getStatusHistory`, `StatusForm`, `StatusHistory`. After loading the item, when it exists also load:

```tsx
  const [statusResult, historyResult] = result.item
    ? await Promise.allSettled([getEquipmentStatus(result.item.id), getStatusHistory(result.item.id)])
    : [null, null];
  const availability = statusResult?.status === "fulfilled" ? statusResult.value : null;
  const history = historyResult?.status === "fulfilled" ? historyResult.value : null;
```

and after the Quantity section render:

```tsx
            <section aria-labelledby="status-heading" className="rounded-2xl border border-[#dce4e0] bg-white p-6 sm:p-7">
              <h2 id="status-heading" className="text-lg font-bold text-[#17211d]">Operational status</h2>
              <p className="mt-2 mb-4 text-sm text-[#52635c]">
                {availability
                  ? availability.available
                    ? `Available for events: ${availability.available_quantity} of ${result.item.total_owned_quantity}.`
                    : "Not available — excluded from equipment availability until it is marked Available."
                  : "Availability could not be loaded."}
              </p>
              <StatusForm equipmentId={result.item.id} currentStatus={result.item.operational_status} />
            </section>
            <section aria-labelledby="history-heading" className="rounded-2xl border border-[#dce4e0] bg-white p-6 sm:p-7">
              <h2 id="history-heading" className="mb-4 text-lg font-bold text-[#17211d]">Status history</h2>
              {history ? <StatusHistory entries={history} /> : <p role="alert" className="text-sm text-[#793f27]">Status history could not be loaded.</p>}
            </section>
```

In `e2e/support/equipment-api.mjs`, insert before the final `send(response, 405, …)`:

```js
  if (suffix === "/status" && request.method === "GET") {
    const available = item.operational_status === "AVAILABLE";
    return send(response, 200, { equipment_id: item.id, operational_status: item.operational_status, available, available_quantity: available ? item.total_owned_quantity : 0 });
  }
  if (suffix === "/status" && request.method === "PATCH") {
    if (staffOnly()) return;
    const body = await readJson(request);
    const now = new Date().toISOString();
    history.push({ id: nextHistoryId++, equipment_id: item.id, old_status: item.operational_status, new_status: body.new_status, reason: body.reason ?? null, changed_by: user.id, changed_at: now });
    items.set(item.id, { ...item, operational_status: body.new_status, updated_at: now });
    return send(response, 200, { equipment_id: item.id, new_status: body.new_status, changed_by: user.id, reason: body.reason ?? null });
  }
  if (suffix === "/status/history" && request.method === "GET") {
    return send(response, 200, history.filter((entry) => entry.equipment_id === item.id).sort((a, b) => b.id - a.id));
  }
```

- [ ] **Step 4: Run unit tests, typecheck, lint**

Run: `npm test && npm run typecheck && npm run lint`
Expected: all pass; clean.

- [ ] **Step 5: Write the e2e spec** — create `frontend/e2e/equipment-status.spec.ts`:

```ts
import { expect, test } from "@playwright/test";

// Purpose: SCRUM-16 AC1–AC3 — marking equipment damaged removes it from
// availability and records who changed it and why.
test("technical support mark equipment damaged and see the history", async ({ page }) => {
  await page.context().addCookies([{ name: "cs_access_token", value: "tech-session", url: "http://127.0.0.1:3100" }]);
  await page.goto("/equipment/new");
  await page.getByLabel("Equipment type").fill("Status Speaker");
  await page.getByLabel("Home location").fill("Store C");
  await page.getByLabel("Total owned quantity").fill("5");
  await page.getByRole("button", { name: "Add equipment" }).click();

  await expect(page.getByText("Available for events: 5 of 5.")).toBeVisible();
  await page.getByLabel("New status").selectOption("DAMAGED");
  await page.getByLabel("Reason (optional)").fill("Blown driver");
  await page.getByRole("button", { name: "Change status" }).click();

  await expect(page.getByText("Status changed to Damaged.")).toBeVisible();
  await expect(page.getByText("Not available — excluded from equipment availability until it is marked Available.")).toBeVisible();
  const latest = page.getByRole("region", { name: "Status history" }).getByRole("listitem").first();
  await expect(latest).toContainText("Available → Damaged");
  await expect(latest).toContainText("Blown driver");
  await expect(latest).toContainText("playwright-tech");
  await expect(page.getByLabel("New status").getByRole("option", { name: "Damaged" })).toHaveCount(0);
});
```

- [ ] **Step 6: Run the e2e suite**

Run: `npm run test:e2e`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add frontend/lib/equipment.ts frontend/app/equipment frontend/e2e frontend/__tests__/equipment-actions.test.ts frontend/__tests__/equipment-status.test.tsx
git commit -m "feat(frontend): technical support change equipment status with history (SCRUM-16)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Traceability and run documentation

**Files:**
- Modify: `docs/testcases/scrum_14_testcases.md`, `frontend/README.md`

- [ ] **Step 1: Collect the real test names** — never cite a name you have not seen in this output:

```bash
cd backend/eventRequestService && .venv/bin/python -m pytest --collect-only -q | tail -3
cd ../authService && .venv/bin/python -m pytest --collect-only -q | grep -E "list_users|lists_|cannot_list"
cd ../../frontend && npx vitest list 2>/dev/null | grep -E "operations|workspace-links" ; npx playwright test --list | grep -iE "assign|venue|equipment"
```

- [ ] **Step 2: Update `docs/testcases/scrum_14_testcases.md`**
  - Change "Last reviewed" to 24 September 2026 and refresh the suite counts in "How to run the suites" from Step 1's output.
  - AC1 row: replace "**API covered; no user interface.** …" with a statement that `/operations/assignments` lists the queue; add evidence `operations.test.tsx` (`lists awaiting requests with an assign control each`, `shows an empty state when nothing awaits assignment`) and Playwright `manager assigns and reassigns a submitted request`.
  - AC2/AC3 rows: add frontend evidence (`assigns the chosen coordinator through the event request API`, `requires a coordinator to be chosen`, `shows the backend's reason when assignment is refused`, `shows the current coordinator of an assigned request`) and the authService picker tests from Task 1.
  - AC6 row: remove the "**Discovery gap**" sentence; add `test_current_assignments_list_the_latest_coordinator_per_request`, `test_current_assignments_exclude_terminal_requests`, `test_current_assignments_include_requests_under_review`, `omits the current coordinator from the reassign choices`, and the Playwright spec.
  - "Explicitly deferred": delete the "No Operations Manager user interface" and "No reassignment discovery" bullets. Keep the notification bullet.
  - Add a limitation line: the coordinator picker lists users from `staff_roles` only; a coordinator whose role exists only in Supabase `app_metadata` will not appear (unverified against live data).

- [ ] **Step 3: Update `frontend/README.md`** — add a "Workspaces" section:

```markdown
## Workspaces

| Role | Lands on | Pages |
| --- | --- | --- |
| Event Organiser | `/event-requests` | create, edit, submit and track requests |
| Event Coordinator | `/coordination/requests` | assigned requests, status transitions, `/venues/search` |
| Event Operations Manager | `/operations/assignments` | assign and reassign coordinators (SCRUM-14) |
| Venue Staff | `/venues` | venue catalogue (SCRUM-30), `/venues/search` (SCRUM-9) |
| Technical Support | `/equipment` | equipment catalogue (SCRUM-45) and status (SCRUM-16) |

Server-side environment variables: `AUTH_SERVICE_URL` (default `http://127.0.0.1:8001`),
`EVENT_REQUEST_API_URL` (8003), `VENUE_API_URL` (8004), `EQUIPMENT_API_URL` (8002).
Venues are held in memory by `venueService` and are lost when it restarts.
```

- [ ] **Step 4: Final full verification**

Run: `npm test && npm run typecheck && npm run lint && npm run test:e2e` (in `frontend/`), then both backend suites with ruff.
Expected: everything green; record the counts in the SCRUM-14 doc's "Latest verification" table with today's commit hash.

- [ ] **Step 5: Commit**

```bash
git add docs/testcases/scrum_14_testcases.md frontend/README.md
git commit -m "docs(scrum-14): trace the operations workspace and document frontend workspaces

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
