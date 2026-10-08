import { expect, test } from "vitest";

import { describeNotification, type AppNotification } from "@/lib/notifications";

function bookingNotification(eventType: string, payload: Record<string, unknown> = {}): AppNotification {
  return {
    id: "n1",
    event_type: eventType,
    payload: {
      booking_request_id: "b1",
      event_request_id: "e1",
      event_name: "Open day",
      venue_name: "Riverside Hall",
      start_date: "2026-10-20",
      end_date: "2026-10-21",
      slots: ["AM", "PM"],
      decision_reason: null,
      suggested_alternative: null,
      ...payload,
    },
    read_at: null,
    created_at: "2026-10-08T02:00:00Z",
  };
}

// AC4-H4 (happy): an approval reads as a booked venue and links to the Coordinator's request
test("describes an approved venue booking", () => {
  expect(describeNotification(bookingNotification("venue_booking_approved"))).toEqual({
    message: "Your venue booking for Open day was approved.",
    href: "/coordination/requests/e1",
    detail: "Riverside Hall · 2026-10-20 to 2026-10-21 · AM, PM",
  });
});

// AC4-H5 (happy): a rejection shows the reason and the suggested alternative
test("describes a rejected venue booking with its reason and alternative", () => {
  const notification = bookingNotification("venue_booking_rejected", {
    decision_reason: "Hall under repair",
    suggested_alternative: "Try Orchard Studio",
  });

  expect(describeNotification(notification)).toEqual({
    message: "Your venue booking request for Open day was rejected.",
    href: "/coordination/requests/e1",
    detail: "Reason: Hall under repair. Suggested alternative: Try Orchard Studio",
  });
});

// AC4-P1 (partition): a rejection without an alternative and an event without a name still read well
test("omits a missing alternative and event name", () => {
  const notification = bookingNotification("venue_booking_rejected", {
    event_name: null,
    decision_reason: "Hall under repair",
  });

  expect(describeNotification(notification)).toEqual({
    message: "Your venue booking request was rejected.",
    href: "/coordination/requests/e1",
    detail: "Reason: Hall under repair",
  });
});

// AC4-N5 (negative): a missing or odd event id gives no link rather than a broken one
test("encodes the event request id and drops a missing one", () => {
  expect(describeNotification(bookingNotification("venue_booking_approved", { event_request_id: "a/b" })).href).toBe(
    "/coordination/requests/a%2Fb",
  );
  expect(describeNotification(bookingNotification("venue_booking_approved", { event_request_id: null })).href).toBeNull();
});
