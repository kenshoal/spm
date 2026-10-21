import { beforeEach, expect, test, vi } from "vitest";

const navigation = vi.hoisted(() => ({ redirect: vi.fn(), revalidatePath: vi.fn() }));
const auth = vi.hoisted(() => ({ requireRole: vi.fn() }));
vi.mock("next/navigation", () => ({ redirect: navigation.redirect }));
vi.mock("next/cache", () => ({ revalidatePath: navigation.revalidatePath }));
vi.mock("@/lib/auth", () => ({ requireAccessToken: async () => "valid-token", requireRole: auth.requireRole }));

import { decideBookingRequest } from "@/app/booking-requests/actions";
import { parseDecisionForm, refusalMessages } from "@/lib/booking-decision-form";

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
  auth.requireRole.mockResolvedValue({ id: "staff-1", email: "s@example.com", role: "venue_staff", roles: ["venue_staff"] });
});

// AC1-H4 (happy): an approval sends only the decision, even if reason fields were filled in
test("an approval sends only the decision", () => {
  expect(parseDecisionForm(form({ decision: "approved", reason: "typed", suggested_alternative: "x" }))).toEqual({
    payload: { decision: "approved" },
    errors: {},
  });
});

// AC1-H5 (happy): a rejection sends the trimmed reason and drops a blank alternative
test("a rejection sends the trimmed reason and optional alternative", () => {
  expect(parseDecisionForm(form({ decision: "rejected", reason: " Hall under repair ", suggested_alternative: " " }))).toEqual({
    payload: { decision: "rejected", reason: "Hall under repair" },
    errors: {},
  });
  expect(
    parseDecisionForm(form({ decision: "rejected", reason: "No", suggested_alternative: " Try Orchard " })).payload,
  ).toEqual({ decision: "rejected", reason: "No", suggested_alternative: "Try Orchard" });
});

// AC2-N4 (negative): a rejection without a reason or an unknown decision is refused before the API
test.each([
  ["AC2-N4a", { decision: "rejected", reason: "   " }, { reason: "Enter a reason for rejecting." }],
  ["AC2-N4b", { decision: "maybe" }, { decision: "Choose approve or reject." }],
])("%s refuses an invalid decision", (_id, fields, errors) => {
  expect(parseDecisionForm(form(fields)).errors).toEqual(errors);
});

// AC5-H3 (happy): every refusal code has a plain-language explanation
test("explains each refusal code", () => {
  expect(
    refusalMessages([
      "venue_unavailable",
      "outside_operating_slots",
      "active_block",
      "setup_outside_window",
      "turnaround_outside_window",
      "booking_conflict",
      "new_code",
    ]),
  ).toEqual([
    "The venue is blocked in the catalogue.",
    "The venue does not operate one of the requested slots.",
    "The venue is blocked for part of this period.",
    "The venue's setup time would start before 07:00.",
    "The venue's turnaround time would end after 24:00.",
    "Another approved booking, including the venue's setup and turnaround time, already holds part of this period.",
    "The venue is not available for this period.",
  ]);
});

// AC1-H4 (happy): a saved decision is posted once and the queue reloads with a confirmation
test("posts the decision and returns to the queue", async () => {
  navigation.redirect.mockImplementation(() => { throw new Error("NEXT_REDIRECT"); });
  const fetchMock = vi.fn().mockResolvedValue(respond(200, { id: "b1", status: "approved" }));
  vi.stubGlobal("fetch", fetchMock);

  await expect(decideBookingRequest("b1", {}, form({ decision: "approved" }))).rejects.toThrow("NEXT_REDIRECT");

  expect(auth.requireRole).toHaveBeenCalledWith("venue_staff");
  expect(fetchMock).toHaveBeenCalledTimes(1);
  expect(fetchMock.mock.calls[0][0]).toBe("http://127.0.0.1:8004/booking-requests/b1/decision");
  expect(fetchMock.mock.calls[0][1]).toMatchObject({ method: "POST", body: JSON.stringify({ decision: "approved" }) });
  expect(navigation.revalidatePath).toHaveBeenCalledWith("/booking-requests");
  expect(navigation.redirect).toHaveBeenCalledWith("/booking-requests?decided=approved");
});

// AC2-N4 (negative): an invalid rejection never reaches the API and keeps what was typed
test("an invalid rejection never calls the API", async () => {
  const fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);

  const state = await decideBookingRequest("b1", {}, form({ decision: "rejected", reason: " ", suggested_alternative: "Hall B" }));

  expect(state).toEqual({
    message: "Check the highlighted fields.",
    errors: { reason: "Enter a reason for rejecting." },
    values: { reason: " ", suggested_alternative: "Hall B" },
  });
  expect(fetchMock).not.toHaveBeenCalled();
  expect(navigation.redirect).not.toHaveBeenCalled();
});

// AC5-H3 (happy): a refused approval explains why and stays on the page
test("explains a refused approval", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      respond(409, {
        detail: {
          message: "Approval refused",
          refusal_codes: ["active_block", "booking_conflict"],
          conflicting_block_ids: ["k1"],
          conflicting_booking_ids: ["b2"],
        },
      }),
    ),
  );

  const state = await decideBookingRequest("b1", {}, form({ decision: "approved" }));

  expect(state.message).toBe(
    "Approval refused. The venue is blocked for part of this period. Another approved booking, including the venue's setup and turnaround time, already holds part of this period. The refusal has been recorded.",
  );
  expect(navigation.redirect).not.toHaveBeenCalled();
  expect(navigation.revalidatePath).not.toHaveBeenCalled();
});

// AC1-N6 (negative): API refusals and outages each get a specific message
test.each([
  ["AC1-N6a", 409, { detail: "Booking request has already been decided" }, "This request has already been decided. Refresh to see its status."],
  ["AC1-N6b", 403, { detail: "Insufficient permissions" }, "Only Venue Staff can decide booking requests."],
  ["AC1-N6c", 404, { detail: "Booking request not found" }, "This booking request no longer exists."],
  ["AC1-N6d", 422, { detail: [] }, "The venue service rejected this decision. Check it and try again."],
  ["AC1-N6e", 502, { detail: "Venue store unavailable" }, "The decision could not be saved. Please try again."],
])("%s explains a %i response", async (_id, status, body, message) => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(respond(status, body)));

  const state = await decideBookingRequest("b1", {}, form({ decision: "rejected", reason: "No" }));

  expect(state.message).toBe(message);
  expect(navigation.redirect).not.toHaveBeenCalled();
});

// AC1-N6 (negative): an unreachable service and an expired session are handled
test("handles an unreachable service and an expired session", async () => {
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
  expect((await decideBookingRequest("b1", {}, form({ decision: "approved" }))).message).toBe(
    "The decision could not be saved. Please try again.",
  );

  navigation.redirect.mockImplementation(() => { throw new Error("NEXT_REDIRECT"); });
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(respond(401)));
  await expect(decideBookingRequest("b1", {}, form({ decision: "approved" }))).rejects.toThrow("NEXT_REDIRECT");
  expect(navigation.redirect).toHaveBeenCalledWith("/auth");
});

// AC1-X3 (cross-cutting): the Venue Staff role is checked before any API call
test("checks the Venue Staff role before calling the API", async () => {
  auth.requireRole.mockRejectedValue(new Error("NEXT_REDIRECT"));
  const fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);

  await expect(decideBookingRequest("b1", {}, form({ decision: "approved" }))).rejects.toThrow("NEXT_REDIRECT");

  expect(fetchMock).not.toHaveBeenCalled();
});

// AC1-N7 (negative): the booking id is encoded into the API path
test("encodes the booking id", async () => {
  navigation.redirect.mockImplementation(() => { throw new Error("NEXT_REDIRECT"); });
  const fetchMock = vi.fn().mockResolvedValue(respond(200, {}));
  vi.stubGlobal("fetch", fetchMock);

  await expect(decideBookingRequest("a/b", {}, form({ decision: "approved" }))).rejects.toThrow("NEXT_REDIRECT");

  expect(fetchMock.mock.calls[0][0]).toBe("http://127.0.0.1:8004/booking-requests/a%2Fb/decision");
});
