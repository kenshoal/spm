import { expect, test } from "vitest";
import { describeNotification, type AppNotification } from "@/lib/notifications";

// AC6-X1 (cross-cutting): the organiser can understand the rejected outcome and follow only a constructed internal event link.
test("describes the rejected change with its retained reason and organiser destination", () => {
  const notification: AppNotification = {
    id: "notice-rejection", event_type: "event_change_rejected", read_at: null,
    created_at: "2026-10-19T03:00:00Z",
    payload: {
      event_request_id: "35000000-0000-4000-8000-000000000001",
      change_request_id: "35000000-0000-4000-8000-000000000002",
      reason: "The current booked capacity cannot accommodate the proposal.",
      href: "https://attacker.invalid/do-not-follow",
    },
  };
  const before = structuredClone(notification);
  const summary = describeNotification(notification, ["event_organiser"]);
  expect(summary.message).toMatch(/change.*reject/i);
  expect(summary.detail).toContain(notification.payload.reason);
  expect(summary.href).toBe("/event-requests/35000000-0000-4000-8000-000000000001/edit");
  expect(notification).toEqual(before);
});
