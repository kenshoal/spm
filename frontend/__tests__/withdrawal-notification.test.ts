import { expect, test } from "vitest";
import { describeNotification, type AppNotification } from "@/lib/notifications";

const EVENT = "22000000-0000-4000-8000-000000000001";

function notice(payload: Record<string, unknown> = {}): AppNotification {
  return {
    id: "notice-registration_withdrawn", event_type: "registration_withdrawn", read_at: null,
    created_at: "2026-10-26T03:00:00Z",
    payload: { event_request_id: EVENT, event_name: "Community Dinner", ...payload },
  };
}

// AC5-H3 (happy): the Attendee is told which event they withdrew from. There is no
// Attendee event page yet, so no link is guessed.
test("describes a withdrawal for the attendee without a link", () => {
  const summary = describeNotification(notice(), ["attendee"]);
  expect(summary.message).toBe("You've withdrawn from Community Dinner.");
  expect(summary.href).toBeNull();
});

// AC5-N6 (negative): a withdrawal notice without an event name still reads well.
test("describes a withdrawal when the event has no name", () => {
  const summary = describeNotification(notice({ event_name: null }), ["attendee"]);
  expect(summary.message).toBe("Your registration has been withdrawn.");
  expect(summary.href).toBeNull();
});
