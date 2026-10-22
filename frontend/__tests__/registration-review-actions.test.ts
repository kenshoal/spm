import { afterEach, expect, test, vi } from "vitest";
import { acknowledgeRegistrationReview } from "@/app/coordination/actions";
import { revalidatePath } from "next/cache";

vi.mock("@/lib/auth", () => ({ requireAccessToken: async () => "coordinator-test-token", requireRole: async () => ({ id: "coordinator-1", roles: ["event_coordinator"] }) }));
vi.mock("next/cache", () => ({ revalidatePath: vi.fn() }));
afterEach(() => { vi.unstubAllGlobals(); vi.clearAllMocks(); });

// AC3-X19 (cross-cutting): the acknowledgement action posts only to the bound review with verified credentials and refreshes the affected views.
test("acknowledges bound registration review with bodyless authenticated POST", async () => {
  const eventId = "35000000-0000-4000-8000-000000000001";
  const reviewId = "35000000-0000-4000-8000-000000000011";
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ id: reviewId, event_request_id: eventId,
    event_updated_at: "2026-10-22T10:00:00Z", changed_fields: ["expected_attendance"], reason: "Attendance changed from 25 to 40",
    raised_at: "2026-10-22T10:00:01Z", cleared_at: "2026-10-22T11:00:00Z", cleared_by: "35000000-0000-4000-8000-000000000099" }), { status: 200 }));
  vi.stubGlobal("fetch", fetchMock);
  const data = new FormData();
  data.set("event_request_id", "untrusted-event"); data.set("review_id", "untrusted-review"); data.set("actor_id", "untrusted-actor");
  const state = await acknowledgeRegistrationReview(eventId, reviewId, {}, data);
  expect(fetchMock).toHaveBeenCalledTimes(1);
  expect(fetchMock.mock.calls[0][0]).toBe(`http://127.0.0.1:8003/event-requests/${eventId}/registration-reviews/${reviewId}/acknowledge`);
  expect(fetchMock.mock.calls[0][1]).toMatchObject({ method: "POST", headers: { Authorization: "Bearer coordinator-test-token" } });
  expect(fetchMock.mock.calls[0][1].body).toBeUndefined();
  expect(state).toEqual({ acknowledged: true });
  expect(revalidatePath).toHaveBeenCalledWith(`/coordination/requests/${eventId}`);
  expect(revalidatePath).toHaveBeenCalledWith(`/event-requests/${eventId}/edit`);
});
