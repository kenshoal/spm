import { beforeEach, expect, test, vi } from "vitest";

const navigation = vi.hoisted(() => ({ redirect: vi.fn(), revalidatePath: vi.fn() }));
vi.mock("next/navigation", () => ({ redirect: navigation.redirect }));
vi.mock("next/cache", () => ({ revalidatePath: navigation.revalidatePath }));
vi.mock("@/lib/auth", () => ({
  requireAccessToken: async () => "valid-token",
  requireRole: async () => ({ id: "ops-1", email: "ops@example.com", role: "event_operations_manager", roles: ["event_operations_manager"] }),
}));

import { assignCoordinator } from "@/app/operations/actions";

function form(coordinatorId: string, currentCoordinatorId?: string): FormData {
  const data = new FormData();
  data.set("coordinator_id", coordinatorId);
  if (currentCoordinatorId) data.set("current_coordinator_id", currentCoordinatorId);
  return data;
}

beforeEach(() => {
  vi.restoreAllMocks();
  navigation.redirect.mockReset();
  navigation.revalidatePath.mockReset();
});

// AC2-H2 (happy, SCRUM-14): assigning posts the chosen coordinator for that request
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

// AC6-H5 (happy, SCRUM-14): reassignment says "reassigned", not "assigned"
// Purpose: SCRUM-14 AC6 — reassigning an already-assigned request says "reassigned", not "assigned".
test("reports a reassignment when the request already had a coordinator", async () => {
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 201 });
  vi.stubGlobal("fetch", fetchMock);

  const state = await assignCoordinator("request-1", {}, form("coord-2", "coord-1"));

  expect(state).toEqual({ assigned: true, message: "Coordinator reassigned." });
});

// AC2-N6 (negative, SCRUM-14): an empty choice is caught before any request is sent
// Purpose: Submitting without a choice is caught before any request is sent.
test("requires a coordinator to be chosen", async () => {
  const fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);

  const state = await assignCoordinator("request-1", {}, form("  "));

  expect(state).toEqual({ message: "Choose a coordinator to assign." });
  expect(fetchMock).not.toHaveBeenCalled();
});

// AC2-N7 (negative, SCRUM-14): a refusal shows the backend's reason and does not revalidate
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

// AC2-N8 (negative, SCRUM-14): a request deleted or closed since the page loaded is explained
// Purpose: A request deleted or closed since the page loaded is explained.
test("explains a request that no longer exists", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 404 }));

  const state = await assignCoordinator("request-1", {}, form("coord-1"));

  expect(state).toEqual({ message: "This request no longer exists. Refresh the page." });
});

// AC2-N9 (negative, SCRUM-14): an unreachable API leaves the manager a retryable error
// Purpose: An unreachable API leaves the manager on the page with a retryable error.
test("returns a retryable error when the API cannot be reached", async () => {
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));

  const state = await assignCoordinator("request-1", {}, form("coord-1"));

  expect(state).toEqual({ message: "The coordinator could not be assigned. Please try again." });
});

// AC2-N10 (negative, SCRUM-14): an expired session sends the manager to sign in
// Purpose: An expired session sends the manager to sign in.
test("redirects to sign-in when the session has expired", async () => {
  navigation.redirect.mockImplementation(() => {
    throw new Error("NEXT_REDIRECT");
  });
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 401 }));

  await expect(assignCoordinator("request-1", {}, form("coord-1"))).rejects.toThrow("NEXT_REDIRECT");
});

// AC1-H2 (happy): a refused assignment names the Event Coordinator Lead as the role that may assign
test("tells a caller who cannot assign that only the Event Coordinator Lead can", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 403 }));

  const state = await assignCoordinator("request-1", {}, form("coord-1"));

  expect(state).toEqual({ message: "Only an Event Coordinator Lead can assign coordinators." });
  expect(navigation.revalidatePath).not.toHaveBeenCalled();
});
