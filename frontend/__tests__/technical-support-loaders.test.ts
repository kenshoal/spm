import { afterEach, beforeEach, expect, test, vi } from "vitest";

// SCRUM-19 increment-2 review follow-ups (loaders): a vanished requirement is
// an error, not "nobody holds the skill"; an expired session still reaches the
// login redirect; and the description limit counts characters like the API.

vi.mock("@/lib/auth", () => ({ requireAccessToken: async () => "valid-token" }));

import {
  listCandidates,
  listTechnicalSupportStaff,
  validateDescription,
} from "@/lib/technical-support";

const fetchMock = vi.fn();
beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

function respond(status: number, body: unknown = {}) {
  fetchMock.mockResolvedValue(
    new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
}

const EVENT_ID = "11111111-1111-4111-8111-111111111111";
const REQ_AV = "aaaa0000-0000-4000-8000-000000000001";

// AC3-N1 (F): a requirement the API no longer finds (404) rejects, so the
// panel shows its load alert instead of the misleading empty-candidate state.
test("a missing requirement's candidates reject instead of returning []", async () => {
  respond(404, { detail: { code: "requirement_not_found", message: "not found" } });
  await expect(listCandidates(EVENT_ID, REQ_AV)).rejects.toThrow();
});

// AC3-H1 (F): a real candidate list is passed through unchanged.
test("candidates load as returned", async () => {
  respond(200, [{ staff_id: "tss-av", already_assigned: false }]);
  await expect(listCandidates(EVENT_ID, REQ_AV)).resolves.toEqual([
    { staff_id: "tss-av", already_assigned: false },
  ]);
});

// AC4-X1 (F): a refused staff listing (403) still falls back to id labels.
test("a refused staff listing falls back to []", async () => {
  respond(403, { detail: "Insufficient permissions" });
  await expect(listTechnicalSupportStaff()).resolves.toEqual([]);
});

// Cross-cutting 401: an expired session is not swallowed by the fallback —
// the login redirect still propagates.
test("an expired session still redirects to /auth", async () => {
  respond(401, { detail: "Invalid token" });
  await expect(listTechnicalSupportStaff()).rejects.toMatchObject({
    digest: expect.stringContaining("/auth"),
  });
});

// AC1-B* (boundary): the action's check counts characters after trimming.
test("validateDescription counts characters, not UTF-16 units", () => {
  expect(validateDescription("🎤".repeat(2000))).toBe("🎤".repeat(2000));
  expect(validateDescription("🎤".repeat(2001))).toBeNull();
  expect(validateDescription(`  ${"x".repeat(2000)}  `)).toBe("x".repeat(2000));
});
