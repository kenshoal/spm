import { beforeEach, expect, test, vi } from "vitest";

const navigation = vi.hoisted(() => ({ redirect: vi.fn(), revalidatePath: vi.fn() }));
const auth = vi.hoisted(() => ({ requireRole: vi.fn() }));
vi.mock("next/navigation", () => ({ redirect: navigation.redirect }));
vi.mock("next/cache", () => ({ revalidatePath: navigation.revalidatePath }));
vi.mock("@/lib/auth", () => ({
  requireAccessToken: async () => "valid-token",
  requireRole: auth.requireRole,
}));

import {
  assignSupportStaff,
  recordSupportRequirement,
} from "@/app/coordination/requests/[id]/technical-support-actions";

const EVENT_ID = "11111111-1111-4111-8111-111111111111";
const REQ_AV = "aaaa0000-0000-4000-8000-000000000001";

function form(fields: Record<string, string>): FormData {
  const data = new FormData();
  for (const [key, value] of Object.entries(fields)) data.set(key, value);
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
  auth.requireRole.mockResolvedValue({
    id: "coord-1",
    email: "c@example.com",
    role: "event_coordinator",
    roles: ["event_coordinator"],
  });
});

// AC1-H1 (happy): the requirement is posted with exactly the trimmed
// description and tag, against the event's technical-support endpoint.
test("posts the requirement with the trimmed description and tag", async () => {
  const fetchMock = vi.fn().mockResolvedValue(respond(201, { id: "r1" }));
  vi.stubGlobal("fetch", fetchMock);

  const state = await recordSupportRequirement(
    {},
    form({ event_request_id: EVENT_ID, description: "  Two wireless mics  ", skill_tag: "audio_visual" }),
  );

  expect(state).toEqual({});
  expect(auth.requireRole).toHaveBeenCalledWith("event_coordinator");
  expect(fetchMock).toHaveBeenCalledTimes(1);
  expect(fetchMock.mock.calls[0][0]).toBe(
    `http://127.0.0.1:8003/event-requests/${EVENT_ID}/technical-support/requirements`,
  );
  expect(fetchMock.mock.calls[0][1]).toMatchObject({
    method: "POST",
    headers: { Authorization: "Bearer valid-token" },
    body: JSON.stringify({ description: "Two wireless mics", skill_tag: "audio_visual" }),
  });
  expect(navigation.revalidatePath).toHaveBeenCalledWith(`/coordination/requests/${EVENT_ID}`);
});

// AC1-B4 (boundary): a description of exactly 2000 characters is accepted.
test("accepts a description of exactly 2000 characters", async () => {
  const fetchMock = vi.fn().mockResolvedValue(respond(201, { id: "r1" }));
  vi.stubGlobal("fetch", fetchMock);

  const state = await recordSupportRequirement(
    {},
    form({ event_request_id: EVENT_ID, description: "x".repeat(2000), skill_tag: "lighting" }),
  );

  expect(state).toEqual({});
  expect(fetchMock).toHaveBeenCalledTimes(1);
});

// AC1-X3 (cross-cutting): a blank or over-long description is refused before
// the API, so a dead submit can never slip a bad payload through.
test.each([
  ["AC1-X3a", ""],
  ["AC1-X3b", "   \n\t"],
  ["AC1-X3c", "x".repeat(2001)],
])("%s refuses an invalid description before the API", async (_id, description) => {
  const fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);

  const state = await recordSupportRequirement(
    {},
    form({ event_request_id: EVENT_ID, description, skill_tag: "audio_visual" }),
  );

  expect(state.message).toBe("Describe the support needed (1 to 2000 characters).");
  expect(fetchMock).not.toHaveBeenCalled();
  expect(navigation.revalidatePath).not.toHaveBeenCalled();
});

// AC1-N1 (negative): a skill tag outside the fixed vocabulary is refused
// before the API.
test("refuses an unknown skill tag before the API", async () => {
  const fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);

  const state = await recordSupportRequirement(
    {},
    form({ event_request_id: EVENT_ID, description: "Mics", skill_tag: "plumbing" }),
  );

  expect(state.message).toBe("Choose one of the four support skills.");
  expect(fetchMock).not.toHaveBeenCalled();
});

// AC2-H1 (happy): the assignment is posted to the requirement's assignments
// endpoint with only the staff id.
test("posts the assignment with the staff id", async () => {
  const fetchMock = vi.fn().mockResolvedValue(
    respond(201, { id: "a1", requirement_id: REQ_AV, staff_id: "tss-av" }),
  );
  vi.stubGlobal("fetch", fetchMock);

  const state = await assignSupportStaff(
    {},
    form({ event_request_id: EVENT_ID, requirement_id: REQ_AV, staff_id: "tss-av" }),
  );

  expect(state).toEqual({});
  expect(fetchMock.mock.calls[0][0]).toBe(
    `http://127.0.0.1:8003/event-requests/${EVENT_ID}/technical-support/requirements/${REQ_AV}/assignments`,
  );
  expect(fetchMock.mock.calls[0][1]).toMatchObject({
    method: "POST",
    headers: { Authorization: "Bearer valid-token" },
    body: JSON.stringify({ staff_id: "tss-av" }),
  });
  expect(navigation.revalidatePath).toHaveBeenCalledWith(`/coordination/requests/${EVENT_ID}`);
});

// AC2-X6 (cross-cutting): each refusal code has its exact plain-language
// message, agreed in the test catalogue.
test.each([
  [
    "AC2-X6a",
    "support_not_allowed",
    "Technical support can only be arranged for approved, planning or confirmed events",
  ],
  ["AC2-X6b", "staff_not_suitable", "This person doesn't hold the required skill"],
  ["AC2-X6c", "already_assigned", "Already assigned to this requirement"],
])("%s maps %s to its message", async (_id, code, message) => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(respond(409, { detail: { code, message: "raw server text" } })),
  );

  const state = await assignSupportStaff(
    {},
    form({ event_request_id: EVENT_ID, requirement_id: REQ_AV, staff_id: "tss-av" }),
  );

  expect(state.message).toBe(message);
  expect(navigation.redirect).not.toHaveBeenCalled();
  expect(navigation.revalidatePath).not.toHaveBeenCalled();
});

// AC2-X6 (cross-cutting): an unrecognised 409 code still says something
// specific instead of a blank form.
test("explains an unknown refusal code", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(respond(409, { detail: { code: "future_code", message: "raw" } })),
  );

  const state = await assignSupportStaff(
    {},
    form({ event_request_id: EVENT_ID, requirement_id: REQ_AV, staff_id: "tss-av" }),
  );

  expect(state.message).toBe("This assignment was refused. Refresh and try again.");
});

// AC2-X6 (cross-cutting): role, relationship and validation failures keep the
// existing message style.
test.each([
  [
    "AC2-X6d",
    403,
    "Only the event's coordinator can arrange technical support.",
  ],
  [
    "AC2-X6e",
    404,
    "This event or requirement could not be found, or the event is no longer assigned to you.",
  ],
  [
    "AC2-X6f",
    422,
    "The event request service rejected the details. Check them and try again.",
  ],
  [
    "AC2-X6g",
    502,
    "The assignment could not be saved. Please try again.",
  ],
])("%s explains a %i response", async (_id, status, message) => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(respond(status, { detail: "raw" })));

  const state = await assignSupportStaff(
    {},
    form({ event_request_id: EVENT_ID, requirement_id: REQ_AV, staff_id: "tss-av" }),
  );

  expect(state.message).toBe(message);
  expect(navigation.redirect).not.toHaveBeenCalled();
});

// AC2-X6 (cross-cutting): an expired session redirects to the sign-in page.
test("redirects to /auth when the session expired", async () => {
  navigation.redirect.mockImplementation(() => {
    throw new Error("NEXT_REDIRECT");
  });
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(respond(401)));

  await expect(
    assignSupportStaff(
      {},
      form({ event_request_id: EVENT_ID, requirement_id: REQ_AV, staff_id: "tss-av" }),
    ),
  ).rejects.toThrow("NEXT_REDIRECT");
  expect(navigation.redirect).toHaveBeenCalledWith("/auth");
});

// AC2-X6 (cross-cutting): an unreachable event request service gets a retry
// message, never an unhandled error.
test("explains an unreachable service", async () => {
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));

  const state = await assignSupportStaff(
    {},
    form({ event_request_id: EVENT_ID, requirement_id: REQ_AV, staff_id: "tss-av" }),
  );

  expect(state.message).toBe("The assignment could not be saved. Please try again.");
});

// AC1-H1 (happy): ids are encoded into the API path, not pasted into it.
test("encodes the event and requirement ids", async () => {
  const fetchMock = vi.fn().mockResolvedValue(respond(201, {}));
  vi.stubGlobal("fetch", fetchMock);

  await assignSupportStaff(
    {},
    form({ event_request_id: "e/1", requirement_id: "r/2", staff_id: "tss-av" }),
  );

  expect(fetchMock.mock.calls[0][0]).toBe(
    "http://127.0.0.1:8003/event-requests/e%2F1/technical-support/requirements/r%2F2/assignments",
  );
});
