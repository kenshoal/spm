import { expect, test } from "vitest";
import { formatDateTime } from "@/lib/event-requests";
import { describeNotification, type AppNotification } from "@/lib/notifications";

const EVENT = "38000000-0000-4000-8000-000000000001";
const DEADLINE = "2030-01-13T09:00:00+00:00";

function notice(event_type: string, payload: Record<string, unknown> = {}): AppNotification {
  return {
    id: `notice-${event_type}`, event_type, read_at: null, created_at: "2026-10-27T03:00:00Z",
    payload: { event_request_id: EVENT, event_name: "Community Dinner", ...payload },
  };
}

// AC5-H5 (happy): each waiting-list type reads as one sentence, with the
// deadline shown for an offer and its warning. There is no Attendee event
// page yet, so no link is guessed.
test.each([
  ["waitlist_offered", "You're offered a place at Community Dinner."],
  ["waitlist_offer_expiring", "Your place offer for Community Dinner expires soon."],
  ["waitlist_offer_expired", "Your place offer for Community Dinner expired; you're back in the queue."],
  ["waitlist_offer_revoked", "The place offer for Community Dinner went to someone else; you keep your place in the queue."],
  ["waitlist_closed", "The waiting list for Community Dinner has closed."],
  ["waitlist_event_cancelled", "Community Dinner has been cancelled, so you're off its waiting list."],
])("describes %s with the event name and no link", (type, message) => {
  const summary = describeNotification(
    notice(type, { expires_at: DEADLINE }),
    ["attendee"],
  );
  expect(summary.message).toBe(message);
  expect(summary.href).toBeNull();
});

// AC5-H5 (happy): offered and expiring show the acceptance deadline.
test.each([
  "waitlist_offered",
  "waitlist_offer_expiring",
])("shows the deadline for %s", (type) => {
  const summary = describeNotification(notice(type, { expires_at: DEADLINE }), ["attendee"]);
  expect(summary.detail).toBe(`Accept by ${formatDateTime(DEADLINE)}.`);
});

// AC5-H5 (happy): the other types carry no deadline line (the closed list's
// detail is where a freed place goes, asserted above).
test.each([
  "waitlist_offer_expired",
  "waitlist_offer_revoked",
  "waitlist_event_cancelled",
])("shows no deadline for %s", (type) => {
  const summary = describeNotification(notice(type, { expires_at: DEADLINE }), ["attendee"]);
  expect(summary.detail).toBeUndefined();
});

// AC5-H5 (happy): the closed list says where a freed place goes instead.
test("says a freed place opens to registration when the list closes", () => {
  const summary = describeNotification(notice("waitlist_closed"), ["attendee"]);
  expect(summary.detail).toBe("Any place that frees up will open to registration.");
});

// AC5-H5 (happy): a notice without an event name still reads well, with no
// empty deadline line.
test.each([
  "waitlist_offered",
  "waitlist_offer_expiring",
  "waitlist_offer_expired",
  "waitlist_offer_revoked",
  "waitlist_closed",
  "waitlist_event_cancelled",
])("describes %s when the event has no name", (type) => {
  const summary = describeNotification(notice(type, { event_name: null }), ["attendee"]);
  expect(summary.message).not.toMatch(/undefined|null/);
  expect(summary.href).toBeNull();
  expect(summary.detail).toBeUndefined();
});
