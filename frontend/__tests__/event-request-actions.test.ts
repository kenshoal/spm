import { beforeEach, expect, test, vi } from "vitest";

const navigation = vi.hoisted(() => ({
  redirect: vi.fn(),
  revalidatePath: vi.fn(),
}));

vi.mock("next/navigation", () => ({ redirect: navigation.redirect }));
vi.mock("next/cache", () => ({ revalidatePath: navigation.revalidatePath }));
vi.mock("@/lib/auth", () => ({ requireAccessToken: async () => "valid-token" }));

import {
  createEventRequest,
  deleteEventRequest,
  updateEventRequest,
} from "@/app/event-requests/actions";

beforeEach(() => {
  vi.restoreAllMocks();
  navigation.redirect.mockReset();
  navigation.revalidatePath.mockReset();
});

// Purpose: Proves the create form sends incomplete values to the draft endpoint and returns to the list.
test("creates an incomplete draft through the event request API", async () => {
  const response = { ok: true, json: vi.fn().mockResolvedValue({ id: "draft-1" }) };
  const fetchMock = vi.fn().mockResolvedValue(response);
  vi.stubGlobal("fetch", fetchMock);
  const formData = new FormData();
  formData.set("event_name", "Community Dinner");

  await createEventRequest({}, formData);

  expect(fetchMock).toHaveBeenCalledOnce();
  expect(fetchMock.mock.calls[0][0]).toBe("http://127.0.0.1:8003/event-requests");
  expect(fetchMock.mock.calls[0][1]).toMatchObject({ method: "POST" });
  expect(fetchMock.mock.calls[0][1]?.headers).toMatchObject({ Authorization: "Bearer valid-token" });
  expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body))).toMatchObject({
    event_name: "Community Dinner",
    purpose: null,
    proposed_date_times: [],
    expected_attendance: null,
  });
  expect(navigation.redirect).toHaveBeenCalledWith("/event-requests");
});

// Purpose: Proves continuing a draft updates its existing identifier instead of creating a second record.
test("updates the same draft through the event request API", async () => {
  const fetchMock = vi.fn().mockResolvedValue({ ok: true });
  vi.stubGlobal("fetch", fetchMock);
  const formData = new FormData();
  formData.set("purpose", "Updated purpose");

  await updateEventRequest("draft-1", {}, formData);

  expect(fetchMock.mock.calls[0][0]).toBe(
    "http://127.0.0.1:8003/event-requests/draft-1",
  );
  expect(fetchMock.mock.calls[0][1]).toMatchObject({ method: "PATCH" });
  expect(navigation.redirect).toHaveBeenCalledWith("/event-requests");
});

// Purpose: Ensures invalid optional attendance is rejected before an unusable draft reaches the API.
test("rejects non-positive attendance without calling the API", async () => {
  const fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  const formData = new FormData();
  formData.set("expected_attendance", "0");

  const state = await createEventRequest({}, formData);

  expect(state.errors?.expected_attendance).toBe(
    "Enter a whole number greater than zero.",
  );
  expect(fetchMock).not.toHaveBeenCalled();
});

// Purpose: Proves deleting a draft sends the authenticated session, not a caller identity.
test("deletes the selected draft through the event request API", async () => {
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 204 });
  vi.stubGlobal("fetch", fetchMock);

  const state = await deleteEventRequest("draft/1", {}, new FormData());

  expect(fetchMock).toHaveBeenCalledWith(
    "http://127.0.0.1:8003/event-requests/draft%2F1",
    {
      method: "DELETE",
      headers: { Authorization: "Bearer valid-token" },
    },
  );
  expect(navigation.revalidatePath).toHaveBeenCalledWith("/event-requests");
  expect(state).toEqual({ deleted: true });
});

// Purpose: Keeps a failed deletion visible and avoids presenting the draft as successfully removed.
test("returns an actionable error when the API rejects draft deletion", async () => {
  const fetchMock = vi.fn().mockResolvedValue({ ok: false, status: 409 });
  vi.stubGlobal("fetch", fetchMock);

  const state = await deleteEventRequest("submitted-1", {}, new FormData());

  expect(state).toEqual({ message: "Only draft requests can be deleted." });
  expect(navigation.revalidatePath).not.toHaveBeenCalled();
});
