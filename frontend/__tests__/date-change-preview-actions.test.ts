import { afterEach, expect, test, vi } from "vitest";
import { previewEventChangeDatePlan } from "@/app/coordination/actions";
import { revalidatePath } from "next/cache";

vi.mock("@/lib/auth", () => ({ requireAccessToken: async () => "coordinator-test-token", requireRole: async () => ({ id: "coordinator-1", roles: ["event_coordinator"] }) }));
vi.mock("next/cache", () => ({ revalidatePath: vi.fn() }));
afterEach(() => { vi.unstubAllGlobals(); vi.clearAllMocks(); });

// AC3-X9 (cross-cutting): the bound coordinator preview is a single authenticated GET, never a mutation or a request for forged form identities.
test("loads the bound advisory plan without writes or revalidation", async () => {
  const plan = { event_request_id: "event/35", change_request_id: "change/35", advisory: true, bookings: [] };
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(plan), { status: 200 }));
  vi.stubGlobal("fetch", fetchMock);
  const data = new FormData();
  data.set("event_request_id", "untrusted-event");
  data.set("change_request_id", "untrusted-change");
  const state = await previewEventChangeDatePlan("event/35", "change/35", {}, data);
  expect(fetchMock).toHaveBeenCalledTimes(1);
  expect(fetchMock.mock.calls[0][0]).toBe("http://127.0.0.1:8003/event-requests/event%2F35/change-requests/change%2F35/date-plan");
  expect(fetchMock.mock.calls[0][1]).toMatchObject({ method: "GET", headers: { Authorization: "Bearer coordinator-test-token" } });
  expect(fetchMock.mock.calls[0][1].body).toBeUndefined();
  expect(state).toEqual({ plan });
  expect(revalidatePath).not.toHaveBeenCalled();
});
