import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { revalidatePath } from "next/cache";
import { checkInAttendee } from "@/app/coordination/actions";
import { CheckInButton } from "@/app/coordination/requests/[id]/check-in-button";
import { isEventDay } from "@/lib/registration-info";

const navigation = vi.hoisted(() => ({ refresh: vi.fn() }));
vi.mock("next/navigation", async (original) => ({ ...await original<typeof import("next/navigation")>(), useRouter: () => navigation }));
vi.mock("@/lib/auth", () => ({ requireAccessToken: async () => "coordinator-test-token", requireRole: async () => ({ id: "coordinator-1", roles: ["event_coordinator"] }) }));
vi.mock("next/cache", () => ({ revalidatePath: vi.fn() }));
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.clearAllMocks(); });

const eventId = "25000000-0000-4000-8000-000000000001";
const registrationId = "25000000-0000-4000-8000-0000000000b1";
// 1 Feb 2030 18:00 Singapore
const dates = ["2030-02-01T10:00:00Z"];

// AC1-B1, AC1-B2, AC1-B3 (boundary): the button's event-day rule matches the database: Singapore calendar days
test.each([
  ["2030-01-31T15:59:59Z", false], // 31 Jan 23:59:59 SGT
  ["2030-01-31T16:00:00Z", true],  // 1 Feb 00:00:00 SGT
  ["2030-02-01T16:00:00Z", false], // 2 Feb 00:00:00 SGT
])("isEventDay at %s is %s", (now, expected) => {
  expect(isEventDay(dates, new Date(now))).toBe(expected);
});

// AC1-N3 (negative): an event with no dates has no event day
test("isEventDay is false without dates", () => {
  expect(isEventDay([], new Date("2030-02-01T04:00:00Z"))).toBe(false);
});

// AC1-X3 (cross-cutting): the action posts to the bound registration and refreshes the views
test("checkInAttendee posts and revalidates", async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ id: registrationId }), { status: 200 }));
  vi.stubGlobal("fetch", fetchMock);
  const state = await checkInAttendee(eventId, registrationId, {}, new FormData());
  expect(fetchMock.mock.calls[0][0]).toBe(`http://127.0.0.1:8003/event-requests/${eventId}/registrations/${registrationId}/check-in`);
  expect(fetchMock.mock.calls[0][1]).toMatchObject({ method: "POST", headers: { Authorization: "Bearer coordinator-test-token" } });
  expect(state).toEqual({ checkedIn: true });
  expect(revalidatePath).toHaveBeenCalledWith(`/coordination/requests/${eventId}`);
});

// AC1-N2, AC4-N1, AC4-N3, AC1-N4 (negative): each refusal code becomes its own message and nothing is revalidated
test.each([
  [409, "not_event_day", /event's days/i],
  [409, "already_checked_in", /already checked in/i],
  [404, "registration_not_found", /no longer registered/i],
  [404, "event_not_found", /no longer assigned/i],
])("checkInAttendee maps %i %s", async (status, code, message) => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ code }), { status })));
  const state = await checkInAttendee(eventId, registrationId, {}, new FormData());
  expect(state.checkedIn).toBeUndefined();
  expect(state.message).toMatch(message);
  expect(revalidatePath).not.toHaveBeenCalled();
});

// AC1-X2 (cross-cutting): the button shows a refusal, then refreshes on success
test("check-in button shows the refusal and refreshes after success", async () => {
  vi.stubGlobal("fetch", vi.fn()
    .mockResolvedValueOnce(new Response(JSON.stringify({ code: "not_event_day" }), { status: 409 }))
    .mockResolvedValueOnce(new Response(JSON.stringify({ id: registrationId }), { status: 200 })));
  render(<CheckInButton eventRequestId={eventId} registrationId={registrationId} />);
  const cell = screen.getByRole("button", { name: "Check in" }).closest("form")!;
  await act(async () => { fireEvent.click(within(cell).getByRole("button", { name: "Check in" })); });
  await waitFor(() => expect(screen.getByRole("alert").textContent).toMatch(/event's days/i));
  expect(navigation.refresh).not.toHaveBeenCalled();
  await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Check in" })); });
  await waitFor(() => expect(navigation.refresh).toHaveBeenCalledTimes(1));
});
