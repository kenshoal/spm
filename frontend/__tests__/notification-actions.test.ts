import { beforeEach, expect, test, vi } from "vitest";

const navigation = vi.hoisted(() => ({ redirect: vi.fn(), revalidatePath: vi.fn() }));
vi.mock("next/navigation", () => ({ redirect: navigation.redirect }));
vi.mock("next/cache", () => ({ revalidatePath: navigation.revalidatePath }));
vi.mock("@/lib/auth", () => ({ requireAccessToken: async () => "valid-token" }));

import { markNotificationRead } from "@/app/notifications/actions";
import { listNotifications } from "@/lib/notifications";

beforeEach(() => {
  vi.restoreAllMocks();
  navigation.redirect.mockReset();
  navigation.revalidatePath.mockReset();
});

// AC6-H1 (happy): The inbox shows the signed-in user's own notifications from notificationService.
test("lists the signed-in user's notifications from the notification API", async () => {
  const notifications = [
    { id: "n1", event_type: "event_request_submitted", payload: {}, read_at: null, created_at: "2026-10-02T03:15:00Z" },
  ];
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => notifications });
  vi.stubGlobal("fetch", fetchMock);

  expect(await listNotifications()).toEqual(notifications);
  expect(fetchMock.mock.calls[0][0]).toBe("http://127.0.0.1:8005/notifications");
  expect(fetchMock.mock.calls[0][1]).toMatchObject({ headers: { Authorization: "Bearer valid-token" } });
});

// AC6-H2 (happy): Marking as read updates that notification on notificationService and refreshes the inbox.
test("marks the notification as read through the notification API", async () => {
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200 });
  vi.stubGlobal("fetch", fetchMock);

  const state = await markNotificationRead("n/1", {});

  expect(fetchMock.mock.calls[0][0]).toBe("http://127.0.0.1:8005/notifications/n%2F1/read");
  expect(fetchMock.mock.calls[0][1]).toMatchObject({ method: "PATCH" });
  expect(state).toEqual({});
  expect(navigation.revalidatePath).toHaveBeenCalledWith("/notifications");
});

// AC6-N4 (negative): An expired session goes back to sign in rather than showing an error.
test("sends an expired session back to sign in", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 401 }));

  await markNotificationRead("n1", {});

  expect(navigation.redirect).toHaveBeenCalledWith("/auth");
});

// AC6-N5 (negative): A notification that is gone (or someone else's) gets a clear message, not a silent no-op.
test("reports a notification that no longer exists", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 404 }));

  const state = await markNotificationRead("n1", {});

  expect(state).toEqual({ message: "This notification no longer exists. Refresh the page." });
  expect(navigation.revalidatePath).not.toHaveBeenCalled();
});

// AC6-N3 (negative): An unreachable notification service is reported so the user can retry.
test("reports a failure when the notification service is unreachable", async () => {
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("fetch failed")));

  const state = await markNotificationRead("n1", {});

  expect(state).toEqual({ message: "Couldn't mark this as read. Please try again." });
});
