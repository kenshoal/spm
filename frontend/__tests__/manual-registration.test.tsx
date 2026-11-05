import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { revalidatePath } from "next/cache";
import { registerAttendee } from "@/app/coordination/actions";
import { ManualRegistrationForm } from "@/app/coordination/requests/[id]/manual-registration-form";

const navigation = vi.hoisted(() => ({ refresh: vi.fn() }));
vi.mock("next/navigation", async (original) => ({ ...await original<typeof import("next/navigation")>(), useRouter: () => navigation }));
vi.mock("@/lib/auth", () => ({ requireAccessToken: async () => "coordinator-test-token", requireRole: async () => ({ id: "coordinator-1", roles: ["event_coordinator"] }) }));
vi.mock("next/cache", () => ({ revalidatePath: vi.fn() }));
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.clearAllMocks(); vi.restoreAllMocks(); });

const eventId = "41000000-0000-4000-8000-000000000001";
const form = (email: string) => { const data = new FormData(); data.set("attendee_email", email); return data; };

// AC1-H1 (happy): the action posts the trimmed email for the bound event and refreshes both registration views
test("registerAttendee posts the email and revalidates", async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ id: "r1" }), { status: 201 }));
  vi.stubGlobal("fetch", fetchMock);
  const state = await registerAttendee(eventId, {}, form("  vip@test.local "));
  expect(fetchMock).toHaveBeenCalledTimes(1);
  expect(fetchMock.mock.calls[0][0]).toBe(`http://127.0.0.1:8003/event-requests/${eventId}/registrations`);
  expect(fetchMock.mock.calls[0][1]).toMatchObject({ method: "POST", headers: { Authorization: "Bearer coordinator-test-token", "Content-Type": "application/json" } });
  expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ attendee_email: "vip@test.local" });
  expect(state).toEqual({ registered: true });
  expect(revalidatePath).toHaveBeenCalledWith(`/coordination/requests/${eventId}`);
  expect(revalidatePath).toHaveBeenCalledWith(`/event-requests/${eventId}/edit`);
});

// AC1-N1, AC1-N5, AC2-B2, AC2-N1, AC4-N1 (negative): each refusal code becomes its own message and nothing is revalidated
test.each([
  [404, "attendee_not_found", /no attendee account/i],
  [404, "event_not_found", /no longer assigned/i],
  [409, "already_registered", /already registered/i],
  [409, "event_full", /full/i],
  [409, "capacity_not_set", /capacity/i],
])("registerAttendee maps %i %s", async (status, code, message) => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ code }), { status })));
  const state = await registerAttendee(eventId, {}, form("vip@test.local"));
  expect(state.registered).toBeUndefined();
  expect(state.message).toMatch(message);
  expect(revalidatePath).not.toHaveBeenCalled();
});

// AC1-N4 (negative): a blank email never reaches the API
test("registerAttendee refuses a blank email without calling the API", async () => {
  const fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  const state = await registerAttendee(eventId, {}, form("   "));
  expect(state.message).toMatch(/enter the attendee's email/i);
  expect(fetchMock).not.toHaveBeenCalled();
});

// AC1-X1 (cross-cutting): the form shows a refusal, then refreshes on success
test("form shows the refusal and refreshes after success", async () => {
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(new Response(JSON.stringify({ code: "already_registered" }), { status: 409 }))
    .mockResolvedValueOnce(new Response(JSON.stringify({ id: "r1" }), { status: 201 }));
  vi.stubGlobal("fetch", fetchMock);
  render(<ManualRegistrationForm eventRequestId={eventId} />);
  fireEvent.change(screen.getByLabelText("Attendee email"), { target: { value: "vip@test.local" } });
  await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Add attendee" })); });
  await waitFor(() => expect(screen.getByRole("alert").textContent).toMatch(/already registered/i));
  expect(navigation.refresh).not.toHaveBeenCalled();
  await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Add attendee" })); });
  await waitFor(() => expect(navigation.refresh).toHaveBeenCalledTimes(1));
  expect(fetchMock.mock.calls[0][0]).toBe(`http://127.0.0.1:8003/event-requests/${eventId}/registrations`);
});
