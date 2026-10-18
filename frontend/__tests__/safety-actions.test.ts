import { beforeEach, expect, test, vi } from "vitest";

const navigation = vi.hoisted(() => ({ redirect: vi.fn(), revalidatePath: vi.fn() }));
const auth = vi.hoisted(() => ({ requireRole: vi.fn() }));
vi.mock("next/navigation", () => ({ redirect: navigation.redirect }));
vi.mock("next/cache", () => ({ revalidatePath: navigation.revalidatePath }));
vi.mock("@/lib/auth", () => ({ requireAccessToken: async () => "valid-token", requireRole: auth.requireRole }));

import { decideSafety } from "@/app/safety/actions";

function form(fields: [string, string][]): FormData {
  const data = new FormData();
  for (const [key, value] of fields) data.append(key, value);
  return data;
}

function respond(status: number, body?: unknown) {
  return { ok: status >= 200 && status < 300, status, json: async () => body };
}

beforeEach(() => {
  vi.restoreAllMocks();
  navigation.redirect.mockReset();
  navigation.revalidatePath.mockReset();
  auth.requireRole.mockReset();
  auth.requireRole.mockResolvedValue({ id: "officer-1", email: null, role: "safety_officer", roles: ["safety_officer"] });
});

// AC3-H3 (happy): an approval posts the decision and returns to the queue with a notice.
test("posts an approval and returns to the queue", async () => {
  const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(respond(200, {}) as Response);

  await decideSafety("event-1", {}, form([["decision", "approved"]]));

  const [url, init] = fetchMock.mock.calls[0];
  expect(String(url)).toMatch(/\/event-requests\/event-1\/safety-decision$/);
  expect(JSON.parse(String(init?.body))).toEqual({ decision: "approved", targets: [] });
  expect(auth.requireRole).toHaveBeenCalledWith("safety_officer");
  expect(navigation.revalidatePath).toHaveBeenCalledWith("/safety");
  expect(navigation.redirect).toHaveBeenCalledWith("/safety?decided=approved");
});

// AC6-N5 (negative): a refused approval explains what is still marked for review.
test("explains what blocks an approval", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    respond(409, {
      detail: "Event request event-1 cannot be approved yet",
      outstanding: [{ kind: "arrangement_needs_review", message: "Still marked for review: Attendance changed." }],
    }) as Response,
  );

  const state = await decideSafety("event-1", {}, form([["decision", "approved"]]));

  expect(state.message).toBe("Approval refused. Still marked for review: Attendance changed.");
  expect(navigation.redirect).not.toHaveBeenCalled();
});

// AC6-N6 (negative): an event already decided says so instead of a generic failure.
test("reports an event that is no longer waiting", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(respond(409, { detail: "not waiting" }) as Response);

  const state = await decideSafety("event-1", {}, form([["decision", "approved"]]));

  expect(state.message).toBe("This event is no longer waiting for a safety check. Refresh the queue.");
});

// AC4a-N5 (negative): an invalid form never reaches the API.
test("does not call the API for an invalid form", async () => {
  const fetchMock = vi.spyOn(globalThis, "fetch");

  const state = await decideSafety("event-1", {}, form([["decision", "changes_requested"], ["reason", " "]]));

  expect(fetchMock).not.toHaveBeenCalled();
  expect(state.errors).toEqual({ reason: "Say what needs to change." });
});
