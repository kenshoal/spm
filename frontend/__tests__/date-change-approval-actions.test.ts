import { afterEach, expect, test, vi } from "vitest";
import { decideEventChangeRequest, loadEventChangeBookingPlan } from "@/app/coordination/actions";
import { revalidatePath } from "next/cache";

vi.mock("@/lib/auth", () => ({ requireAccessToken: async () => "coordinator-test-token", requireRole: async () => ({ id: "coordinator-1", roles: ["event_coordinator"] }) }));
vi.mock("next/cache", () => ({ revalidatePath: vi.fn() }));
afterEach(() => { vi.unstubAllGlobals(); vi.clearAllMocks(); });

// AC3-X31 (cross-cutting): the editor loads only its bound current batch and posts the exact selected plan; a safe conflict retains evidence without announcing or revalidating success.
test("loads and decides the bound date plan with safe conflict recovery", async () => {
  const plan = [{ booking_id: "35000000-0000-4000-8000-000000000001", start_date: "2026-11-22", end_date: "2026-11-22", start_minute: 660, end_minute: 750 }];
  const context = { event_request_id: "event/35", change_request_id: "change/35", event_updated_at: "2026-10-22T01:00:00Z", bookings: [], automatic_plan: plan, automatic_plan_error: null };
  const bookings = [{ booking_id: plan[0].booking_id, refusal_codes: ["active_block"], conflicting_booking_ids: [], conflicting_block_ids: ["35000000-0000-4000-8000-000000000999"] }];
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(new Response(JSON.stringify(context), { status: 200 }))
    .mockResolvedValueOnce(new Response(JSON.stringify({ detail: { code: "BOOKING_CONFLICT", message: "Review conflicting booking ranges.", bookings } }), { status: 409 }))
    .mockResolvedValueOnce(new Response("{}", { status: 200 }));
  vi.stubGlobal("fetch", fetchMock);
  const data = new FormData();
  data.set("event_request_id", "forged-event");
  data.set("change_request_id", "forged-change");
  data.set("actor", "forged-coordinator");
  const loaded = await loadEventChangeBookingPlan("event/35", "change/35", {}, data);
  expect(loaded).toEqual({ plan: context });
  expect(fetchMock.mock.calls[0][0]).toBe("http://127.0.0.1:8003/event-requests/event%2F35/change-requests/change%2F35/booking-plan");
  expect(fetchMock.mock.calls[0][1]).toMatchObject({ method: "GET", headers: { Authorization: "Bearer coordinator-test-token" } });
  expect(fetchMock.mock.calls[0][1].body).toBeUndefined();
  expect(revalidatePath).not.toHaveBeenCalled();
  data.set("booking_plan", JSON.stringify(plan));
  data.set("reason", "Checked each venue range");
  const refused = await decideEventChangeRequest("event/35", "change/35", "Approved", {}, data);
  expect(refused.message).toBeTruthy();
  expect(refused.bookingConflicts).toEqual(bookings);
  expect(revalidatePath).not.toHaveBeenCalled();
  const accepted = await decideEventChangeRequest("event/35", "change/35", "Approved", {}, data);
  expect(accepted).toEqual({});
  for (const [url, options] of fetchMock.mock.calls.slice(1)) {
    expect(url).toBe("http://127.0.0.1:8003/event-requests/event%2F35/change-requests/change%2F35/decision");
    expect(options).toMatchObject({ method: "POST", headers: { Authorization: "Bearer coordinator-test-token", "Content-Type": "application/json" } });
    expect(JSON.parse(options.body)).toEqual({ decision: "Approved", reason: "Checked each venue range", booking_plan: plan });
  }
  expect(revalidatePath).toHaveBeenCalledWith("/coordination/requests/event/35");
  expect(revalidatePath).toHaveBeenCalledWith("/event-requests/event/35/edit");
  expect(fetchMock).toHaveBeenCalledTimes(3);
});
