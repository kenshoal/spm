import { expect, test } from "vitest";
import { describeNotification, type AppNotification } from "@/lib/notifications";

const REQUEST = "36000000-0000-4000-8000-000000000001";

function notice(event_type: string, payload: Record<string, unknown> = {}): AppNotification {
  return {
    id: `notice-${event_type}`, event_type, read_at: null, created_at: "2026-10-23T03:00:00Z",
    payload: { event_request_id: REQUEST, ...payload },
  };
}

// AC1-H4 (happy): the Organiser is told their request was approved and can open it.
test("describes an approved event request with the organiser's link", () => {
  const summary = describeNotification(notice("event_request_approved"), ["event_organiser"]);
  expect(summary.message).toMatch(/event request.*approved/i);
  expect(summary.href).toBe(`/event-requests/${REQUEST}/edit`);
});

// AC1-H4 (happy): a rejection shows the Coordinator's reason under the message.
test("describes a rejected event request with its reason", () => {
  const summary = describeNotification(
    notice("event_request_rejected", { reason: "Outside the programme scope." }),
    ["event_organiser"],
  );
  expect(summary.message).toMatch(/event request.*rejected/i);
  expect(summary.detail).toBe("Outside the programme scope.");
  expect(summary.href).toBe(`/event-requests/${REQUEST}/edit`);
});

// AC1-N5 (negative): a missing request id gives no guessed link, and a blank reason no empty detail line.
test("shows no link without a request id and no detail for a blank reason", () => {
  const summary = describeNotification(
    { ...notice("event_request_rejected", { reason: "   " }), payload: { reason: "   " } },
    ["event_organiser"],
  );
  expect(summary.href).toBeNull();
  expect(summary.detail).toBeUndefined();
});

// AC3-H3 (happy): the Organiser is told their event is confirmed and can open it.
test("describes a confirmed event with the organiser's link", () => {
  const summary = describeNotification(notice("event_confirmed"), ["event_organiser"]);
  expect(summary.message).toMatch(/event.*confirmed/i);
  expect(summary.href).toBe(`/event-requests/${REQUEST}/edit`);
});

// AC2-H2 (happy): the Organiser is told which venue was refused for their event, and the
// link goes to their own request page, not the Coordinator's view they cannot open.
test("describes a rejected venue booking for the organiser with their own link", () => {
  const summary = describeNotification(
    notice("venue_booking_rejected", {
      event_name: "Open day",
      venue_name: "Riverside Hall",
      decision_reason: "Hall under repair",
      suggested_alternative: "Try Orchard Studio",
    }),
    ["event_organiser"],
  );
  expect(summary.message).toBe("A venue for your event Open day was rejected.");
  expect(summary.href).toBe(`/event-requests/${REQUEST}/edit`);
  expect(summary.detail).toBe(
    "Riverside Hall. Reason: Hall under repair. Suggested alternative: Try Orchard Studio",
  );
});

// AC2-X2 (cross-cutting): the Coordinator's wording and link are unchanged, including
// for someone who is both Organiser and Coordinator.
test("keeps the coordinator's rejected-booking wording and link", () => {
  const summary = describeNotification(
    notice("venue_booking_rejected", { event_name: "Open day" }),
    ["event_organiser", "event_coordinator"],
  );
  expect(summary.message).toBe("Your venue booking request for Open day was rejected.");
  expect(summary.href).toBe(`/coordination/requests/${REQUEST}`);
});
