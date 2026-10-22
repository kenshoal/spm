import { expect, test } from "vitest";
import { describeNotification, type AppNotification } from "@/lib/notifications";

// AC6-X2 (cross-cutting): an approved outcome remains understandable without an optional note and links only to the organiser's own event route.
test("describes the approved change and constructs its organiser destination", () => {
  const notification: AppNotification = {
    id: "notice-approval", event_type: "event_change_approved", read_at: null,
    created_at: "2026-10-21T03:00:00Z",
    payload: { event_request_id: "35000000-0000-4000-8000-000000000001", change_request_id: "35000000-0000-4000-8000-000000000002", reason: null, href: "https://attacker.invalid/do-not-follow" },
  };
  const before = structuredClone(notification);
  const summary = describeNotification(notification, ["event_organiser"]);
  expect(summary.message).toMatch(/change.*approved/i);
  expect(summary.href).toBe("/event-requests/35000000-0000-4000-8000-000000000001/edit");
  expect(summary.detail ?? "").not.toMatch(/null|undefined/i);
  expect(notification).toEqual(before);
});
