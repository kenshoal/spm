import { afterEach, expect, test, vi } from "vitest";
import { createEventChangeRequest } from "@/app/event-requests/actions";
import { revalidatePath } from "next/cache";

vi.mock("@/lib/auth", () => ({ requireAccessToken: async () => "organiser-test-token", requireRole: async () => ({ id: "organiser-1", roles: ["event_organiser"] }) }));
vi.mock("next/cache", () => ({ revalidatePath: vi.fn() }));
afterEach(() => { vi.unstubAllGlobals(); vi.clearAllMocks(); });

// AC1-X4 (cross-cutting): all submitted replacement event anchors retain their input order and Singapore instants rather than silently truncating to the first date.
test("submits every replacement date in order with supported mixed details", async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response("{}", { status: 201 }));
  vi.stubGlobal("fetch", fetchMock);
  const form = new FormData();
  form.set("explanation", "Move both programme sessions.");
  form.append("proposed_date_time", "2026-11-22T11:00");
  form.append("proposed_date_time", "2026-11-24T16:00");
  form.set("expected_attendance", "40");
  const result = await createEventChangeRequest("event/35", {}, form);
  expect(result).toEqual({ submitted: true });
  expect(fetchMock).toHaveBeenCalledTimes(1);
  const [url, options] = fetchMock.mock.calls[0];
  expect(url).toBe("http://127.0.0.1:8003/event-requests/event%2F35/change-requests");
  expect(options).toMatchObject({ method: "POST", headers: { Authorization: "Bearer organiser-test-token", "Content-Type": "application/json" } });
  expect(JSON.parse(options.body)).toEqual({ explanation: "Move both programme sessions.", proposed_date_times: ["2026-11-22T03:00:00.000Z", "2026-11-24T08:00:00.000Z"], expected_attendance: 40 });
  expect(revalidatePath).toHaveBeenCalledWith("/event-requests/event/35/edit");
});

// AC1-N5 (negative): an invalid submitted date refuses the whole mixed proposal instead of dropping that date and applying only another valid field.
test("does not silently omit an invalid date from a mixed proposal", async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response("{}", { status: 201 }));
  vi.stubGlobal("fetch", fetchMock);
  const form = new FormData();
  form.set("explanation", "Move both sessions and update attendance.");
  form.append("proposed_date_time", "2026-11-22T11:00");
  form.append("proposed_date_time", "invalid-date");
  form.set("expected_attendance", "40");
  const result = await createEventChangeRequest("event-35", {}, form);
  expect(result.submitted).not.toBe(true);
  expect(result.errors?.proposed_changes).toBeTruthy();
  expect(result.message).toBeTruthy();
  expect(fetchMock).not.toHaveBeenCalled();
  expect(revalidatePath).not.toHaveBeenCalled();
});

// SCRUM-35 AC1-P3 (partition): accessibility needs are a supported value, sent trimmed with the other fields
test("sends the proposed accessibility needs", async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response("{}", { status: 201 }));
  vi.stubGlobal("fetch", fetchMock);
  const form = new FormData();
  form.set("explanation", "A guest now uses a wheelchair.");
  form.set("accessibility_needs", "  Step-free access and a hearing loop  ");
  const result = await createEventChangeRequest("event-35", {}, form);
  expect(result).toEqual({ submitted: true });
  expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
    explanation: "A guest now uses a wheelchair.",
    accessibility_needs: "Step-free access and a hearing loop",
  });
});
