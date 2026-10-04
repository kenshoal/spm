import { beforeEach, expect, test, vi } from "vitest";

const navigation = vi.hoisted(() => ({ redirect: vi.fn(), revalidatePath: vi.fn() }));
const auth = vi.hoisted(() => ({ requireRole: vi.fn() }));
vi.mock("next/navigation", () => ({ redirect: navigation.redirect }));
vi.mock("next/cache", () => ({ revalidatePath: navigation.revalidatePath }));
vi.mock("@/lib/auth", () => ({
  requireAccessToken: async () => "valid-token",
  requireRole: auth.requireRole,
}));

import { createVenueBlock } from "@/app/venue-blocks/actions";

function form(fields: Record<string, string | string[]>): FormData {
  const data = new FormData();
  for (const [key, value] of Object.entries(fields)) {
    for (const item of Array.isArray(value) ? value : [value]) data.append(key, item);
  }
  return data;
}

const valid = {
  venue_id: "v1",
  start_date: "2026-10-20",
  end_date: "2026-10-21",
  slots: ["AM", "PM"],
  reason_category: "maintenance",
  reason_detail: "Air-con repairs",
};

const echoed = { ...valid, reason_detail: "Air-con repairs" };

beforeEach(() => {
  vi.restoreAllMocks();
  navigation.redirect.mockReset();
  navigation.revalidatePath.mockReset();
  auth.requireRole.mockReset();
  auth.requireRole.mockResolvedValue({ id: "staff-1", email: "staff@example.com", role: "venue_staff", roles: ["venue_staff"] });
});

// AC1-H1 (happy): a valid block is posted once and the staffer lands on that venue's month
test("posts the block and opens the venue's month", async () => {
  navigation.redirect.mockImplementation(() => { throw new Error("NEXT_REDIRECT"); });
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 201, json: async () => ({ id: "b1" }) });
  vi.stubGlobal("fetch", fetchMock);

  await expect(createVenueBlock({}, form(valid))).rejects.toThrow("NEXT_REDIRECT");

  expect(auth.requireRole).toHaveBeenCalledWith("venue_staff");
  expect(fetchMock).toHaveBeenCalledTimes(1);
  expect(fetchMock.mock.calls[0][0]).toBe("http://127.0.0.1:8004/venues/v1/blocks");
  expect(fetchMock.mock.calls[0][1]).toMatchObject({
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: "Bearer valid-token" },
    body: JSON.stringify({
      start_date: "2026-10-20",
      end_date: "2026-10-21",
      slots: ["AM", "PM"],
      reason_category: "maintenance",
      reason_detail: "Air-con repairs",
    }),
  });
  expect(navigation.revalidatePath).toHaveBeenCalledWith("/venue-blocks");
  expect(navigation.redirect).toHaveBeenCalledWith("/venue-blocks?venue=v1&month=2026-10&created=1");
});

// AC1-H1 (happy): the venue id is encoded into the API path and the redirect
test("encodes the venue id in the request path and redirect", async () => {
  navigation.redirect.mockImplementation(() => { throw new Error("NEXT_REDIRECT"); });
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 201 });
  vi.stubGlobal("fetch", fetchMock);

  await expect(createVenueBlock({}, form({ ...valid, venue_id: "a/b" }))).rejects.toThrow("NEXT_REDIRECT");

  expect(fetchMock.mock.calls[0][0]).toBe("http://127.0.0.1:8004/venues/a%2Fb/blocks");
  expect(navigation.redirect).toHaveBeenCalledWith("/venue-blocks?venue=a%2Fb&month=2026-10&created=1");
});

// AC1-B2 (boundary): an end date before the start date never reaches the API and keeps the input
test("an invalid block never calls the API and echoes the typed values", async () => {
  const fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);

  const state = await createVenueBlock({}, form({ ...valid, end_date: "2026-10-19" }));

  expect(state).toEqual({
    message: "Check the highlighted fields.",
    errors: { end_date: "The end date must be on or after the start date." },
    values: { ...echoed, end_date: "2026-10-19" },
  });
  expect(fetchMock).not.toHaveBeenCalled();
  expect(navigation.revalidatePath).not.toHaveBeenCalled();
  expect(navigation.redirect).not.toHaveBeenCalled();
});

// AC1-N5 (negative): a 403 from venueService explains the role requirement and saves nothing
// AC1-N6 (negative): a 404 explains that the venue was removed
// AC1-N7 (negative): a 422 does not claim that a field is highlighted
// AC1-N8 (negative): a 5xx gives a retryable error
test.each([
  ["AC1-N5", 403, "Only Venue Staff can block venues."],
  ["AC1-N6", 404, "This venue no longer exists."],
  ["AC1-N7", 422, "The venue service rejected these details. Check them and try again."],
  ["AC1-N8", 502, "The block could not be saved. Please try again."],
])("%s explains a %i response and keeps the input", async (_id, status, message) => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status }));

  const state = await createVenueBlock({}, form(valid));

  expect(state).toEqual({ message, values: echoed });
  expect(navigation.revalidatePath).not.toHaveBeenCalled();
  expect(navigation.redirect).not.toHaveBeenCalled();
});

// AC1-N8 (negative): an unreachable venue service gives a retryable error
test("returns a retryable error when the venue service cannot be reached", async () => {
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));

  const state = await createVenueBlock({}, form(valid));

  expect(state).toEqual({ message: "The block could not be saved. Please try again.", values: echoed });
  expect(navigation.redirect).not.toHaveBeenCalled();
});

// AC1-N9 (negative): an expired session is sent to sign in without revalidating
test("redirects to sign-in when the session has expired", async () => {
  navigation.redirect.mockImplementation(() => { throw new Error("NEXT_REDIRECT"); });
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 401 }));

  await expect(createVenueBlock({}, form(valid))).rejects.toThrow("NEXT_REDIRECT");

  expect(navigation.redirect).toHaveBeenCalledWith("/auth");
  expect(navigation.revalidatePath).not.toHaveBeenCalled();
});

// AC1-X1 (cross-cutting): a caller without the Venue Staff role is stopped before any API call
test("checks the Venue Staff role before calling the API", async () => {
  auth.requireRole.mockRejectedValue(new Error("NEXT_REDIRECT"));
  const fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);

  await expect(createVenueBlock({}, form(valid))).rejects.toThrow("NEXT_REDIRECT");

  expect(auth.requireRole).toHaveBeenCalledWith("venue_staff");
  expect(fetchMock).not.toHaveBeenCalled();
});
