import { beforeEach, expect, test, vi } from "vitest";

const navigation = vi.hoisted(() => ({
  redirect: vi.fn(),
  revalidatePath: vi.fn(),
}));

vi.mock("next/navigation", () => ({ redirect: navigation.redirect }));
vi.mock("next/cache", () => ({ revalidatePath: navigation.revalidatePath }));
vi.mock("@/lib/auth", () => ({
  requireAccessToken: async () => "valid-token",
  requireRole: async () => ({
    id: "coordinator-1",
    email: "coordinator@example.com",
    role: "event_coordinator",
    roles: ["event_coordinator"],
  }),
}));

import {
  cancelEventRequest,
  completeEventRequest,
  decideEventRequest,
  decideEventChangeRequest,
  resumeEventRequestReview,
  startEventRequestReview,
} from "@/app/coordination/actions";

beforeEach(() => {
  vi.restoreAllMocks();
  navigation.redirect.mockReset();
  navigation.revalidatePath.mockReset();
});

// Purpose: Starting review posts the coordinator's session to the review endpoint.
test("starts review through the event request API", async () => {
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200 });
  vi.stubGlobal("fetch", fetchMock);

  const state = await startEventRequestReview("request-1", {}, new FormData());

  expect(fetchMock).toHaveBeenCalledOnce();
  expect(fetchMock.mock.calls[0][0]).toBe(
    "http://127.0.0.1:8003/event-requests/request-1/review",
  );
  expect(fetchMock.mock.calls[0][1]).toMatchObject({
    method: "POST",
    headers: { Authorization: "Bearer valid-token" },
  });
  expect(state).toEqual({});
  expect(navigation.revalidatePath).toHaveBeenCalledWith("/coordination/requests");
  expect(navigation.revalidatePath).toHaveBeenCalledWith("/coordination/requests/request-1");
});

// Purpose: Continuing after clarification calls the guarded resume-review endpoint.
test("resumes review after clarification", async () => {
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200 });
  vi.stubGlobal("fetch", fetchMock);

  const state = await resumeEventRequestReview("request-1", {}, new FormData());

  expect(fetchMock.mock.calls[0][0]).toBe(
    "http://127.0.0.1:8003/event-requests/request-1/resume-review",
  );
  expect(state).toEqual({});
});

// Purpose: Cancelling targets the cancellation endpoint the backend enforces.
test("cancels through the event request API", async () => {
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200 });
  vi.stubGlobal("fetch", fetchMock);

  const state = await cancelEventRequest("request/2", {}, new FormData());

  expect(fetchMock.mock.calls[0][0]).toBe(
    "http://127.0.0.1:8003/event-requests/request%2F2/cancellation",
  );
  expect(state).toEqual({});
});

// Purpose: Completion targets the completion endpoint the backend enforces.
test("completes through the event request API", async () => {
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200 });
  vi.stubGlobal("fetch", fetchMock);

  const state = await completeEventRequest("request-3", {}, new FormData());

  expect(fetchMock.mock.calls[0][0]).toBe(
    "http://127.0.0.1:8003/event-requests/request-3/completion",
  );
  expect(state).toEqual({});
});

// Purpose: An approval sends the selected outcome and optional reason to the decision API.
test("approves through the review decision endpoint", async () => {
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200 });
  vi.stubGlobal("fetch", fetchMock);
  const formData = new FormData();
  formData.set("reason", "Ready for planning");

  const state = await decideEventRequest(
    "request-4",
    "Approved",
    {},
    formData,
  );

  expect(fetchMock.mock.calls[0][0]).toBe(
    "http://127.0.0.1:8003/event-requests/request-4/decision",
  );
  expect(fetchMock.mock.calls[0][1]).toMatchObject({
    method: "POST",
    body: JSON.stringify({
      decision: "Approved",
      reason: "Ready for planning",
    }),
  });
  expect(state).toEqual({});
});

// Purpose: Requesting changes without guidance is stopped before any API mutation.
test("requires a reason before requesting changes", async () => {
  const fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);

  const state = await decideEventRequest(
    "request-4",
    "Changes Requested",
    {},
    new FormData(),
  );

  expect(state).toEqual({
    message: "Explain the decision before continuing.",
    errors: { reason: "Enter a reason for the organiser." },
  });
  expect(fetchMock).not.toHaveBeenCalled();
});

// Purpose: A stale decision tells the coordinator to reload instead of implying success.
test("reports when a request is no longer under review", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({ ok: false, status: 409 }),
  );

  const state = await decideEventRequest(
    "request-4",
    "Approved",
    {},
    new FormData(),
  );

  expect(state).toEqual({
    message:
      "This request is no longer under review. Refresh the page to see where it stands.",
  });
  expect(navigation.revalidatePath).not.toHaveBeenCalled();
});

// Purpose: Losing the assignment between page load and action is explained, not silent.
test("explains that only the assigned coordinator may act", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({ ok: false, status: 403 }),
  );

  const state = await cancelEventRequest("request-1", {}, new FormData());

  expect(state).toEqual({
    message: "Only the coordinator currently assigned to this request can do that.",
  });
  expect(navigation.revalidatePath).not.toHaveBeenCalled();
});

// Purpose: A status that moved before the action is reported as refreshable, not a failure.
test("reports an already-changed status without mutating anything", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({ ok: false, status: 409 }),
  );

  const state = await startEventRequestReview("request-1", {}, new FormData());

  expect(state).toEqual({
    message:
      "This request's status has already changed. Refresh the page to see where it stands.",
  });
  expect(navigation.revalidatePath).not.toHaveBeenCalled();
});

// Purpose: An unreachable API leaves the coordinator on the page with a recoverable error.
test("returns an actionable error when the API cannot be reached", async () => {
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));

  const state = await completeEventRequest("request-1", {}, new FormData());

  expect(state).toEqual({ message: "That could not be done. Please try again." });
  expect(navigation.revalidatePath).not.toHaveBeenCalled();
});

// Purpose: An expired session sends the coordinator to sign in, never the workspace.
test("redirects to sign-in when the session is no longer valid", async () => {
  navigation.redirect.mockImplementation(() => {
    throw new Error("NEXT_REDIRECT");
  });
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({ ok: false, status: 401 }),
  );

  await expect(
    cancelEventRequest("request-1", {}, new FormData()),
  ).rejects.toThrow("NEXT_REDIRECT");
});

// AC3-H1 (happy): the coordinator decision targets the exact retained change request
test("approves an event change request", async () => {
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200 });
  vi.stubGlobal("fetch", fetchMock);

  const state = await decideEventChangeRequest(
    "request/1", "change/1", "Approved", {}, new FormData(),
  );

  expect(fetchMock.mock.calls[0][0]).toBe(
    "http://127.0.0.1:8003/event-requests/request%2F1/change-requests/change%2F1/decision",
  );
  expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body))).toEqual({
    decision: "Approved",
    reason: null,
  });
  expect(state).toEqual({});
});

// AC4-N1 (negative): a blank rejection reason never reaches the API
test("requires a reason before rejecting an event change", async () => {
  const fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);

  const state = await decideEventChangeRequest(
    "request-1", "change-1", "Rejected", {}, new FormData(),
  );

  expect(state.errors?.reason).toBe("Enter a reason for the organiser.");
  expect(fetchMock).not.toHaveBeenCalled();
});
