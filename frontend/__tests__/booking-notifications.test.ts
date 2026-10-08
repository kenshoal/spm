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

function blockNotification(payload: Record<string, unknown> = {}): AppNotification {
  return {
    id: "n2",
    event_type: "venue_block_affects_booking",
    payload: {
      block_id: "k1",
      booking_request_id: "b1",
      event_request_id: "e1",
      event_name: "Open day",
      venue_name: "Riverside Hall",
      block_start_date: "2026-11-21",
      block_end_date: "2026-11-22",
      block_slots: ["AM"],
      reason_category: "maintenance",
      reason_detail: "Air-con repairs",
      ...payload,
    },
    read_at: null,
    created_at: "2026-10-08T02:00:00Z",
  };
}

// AC3-H5 (happy): a block over the Coordinator's booking explains when, which slots and why
test("describes a block that affects the coordinator's booking", () => {
  expect(describeNotification(blockNotification())).toEqual({
    message: "Riverside Hall has been blocked during your booking for Open day.",
    href: "/coordination/requests/e1",
    detail: "Blocked 2026-11-21 to 2026-11-22 · AM · Maintenance — Air-con repairs. Arrange an alternative venue or time.",
  });
});

// AC3-P6 (partition): missing venue name, event name and reason detail still read well
test("describes a block notification with sparse details", () => {
  expect(describeNotification(blockNotification({ venue_name: null, event_name: null, reason_detail: null, reason_category: "internal_use" }))).toEqual({
    message: "A venue has been blocked during your booking.",
    href: "/coordination/requests/e1",
    detail: "Blocked 2026-11-21 to 2026-11-22 · AM · Internal use. Arrange an alternative venue or time.",
  });
});
