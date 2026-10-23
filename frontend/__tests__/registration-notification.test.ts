import { expect, test } from "vitest";
import { formatDateTime } from "@/lib/event-requests";
import { describeNotification, type AppNotification } from "@/lib/notifications";

const EVENT = "38000000-0000-4000-8000-000000000001";

function notice(event_type: string, payload: Record<string, unknown> = {}): AppNotification {
  return {
    id: `notice-${event_type}`, event_type, read_at: null, created_at: "2026-10-23T03:00:00Z",
    payload: { event_request_id: EVENT, event_name: "Community Dinner", ...payload },
  };
}

// AC1-H3 (happy): the Attendee is told which event they are registered for. There is no
// Attendee event page yet, so no link is guessed.
test("describes a confirmed registration for the attendee without a link", () => {
  const summary = describeNotification(notice("registration_confirmed"), ["attendee"]);
  expect(summary.message).toBe("You're registered for Community Dinner.");
  expect(summary.href).toBeNull();
});

// AC1-N6 (negative): a registration notice without an event name still reads well.
test("describes a confirmed registration when the event has no name", () => {
  const summary = describeNotification(notice("registration_confirmed", { event_name: null }), ["attendee"]);
  expect(summary.message).toBe("Your registration is confirmed.");
});

// AC2-H3 (happy): the Organiser is told registration is full and opens their own request page.
test("describes full registration for the organiser with their link", () => {
  const summary = describeNotification(notice("registration_full", { capacity: 10 }), ["event_organiser"]);
  expect(summary.message).toBe("Registration for Community Dinner is full.");
  expect(summary.detail).toBe("All 10 places are taken.");
  expect(summary.href).toBe(`/event-requests/${EVENT}/edit`);
});

// AC2-H3 (happy): the Coordinator gets the same notice linking to the coordination page,
// including when they are also an Organiser.
test("describes full registration for the coordinator with the coordination link", () => {
  const summary = describeNotification(
    notice("registration_full", { capacity: 10 }),
    ["event_organiser", "event_coordinator"],
  );
  expect(summary.href).toBe(`/coordination/requests/${EVENT}`);
});

// AC4-H5 (happy): a registered Attendee is told the event is cancelled. There is no
// Attendee event page, so no link is guessed.
test("describes a cancelled event for the attendee without a link", () => {
  const summary = describeNotification(notice("event_cancelled"), ["attendee"]);
  expect(summary.message).toBe("Community Dinner has been cancelled.");
  expect(summary.href).toBeNull();
});

// AC4-N7 (negative): a cancellation without an event name still reads well.
test("describes a cancelled event when the event has no name", () => {
  const summary = describeNotification(notice("event_cancelled", { event_name: null }), ["attendee"]);
  expect(summary.message).toBe("An event you registered for has been cancelled.");
});

// AC4-H6 (happy): the Attendee sees that the dates changed and what they are now.
test("describes changed event dates with the new dates", () => {
  const summary = describeNotification(
    notice("event_changed", { proposed_date_times: ["2026-11-22T11:00:00+08:00", "2026-11-24T16:00:00+08:00"] }),
    ["attendee"],
  );
  expect(summary.message).toBe("The dates of Community Dinner have changed.");
  expect(summary.detail).toBe(
    `New dates: ${formatDateTime("2026-11-22T11:00:00+08:00")}; ${formatDateTime("2026-11-24T16:00:00+08:00")}`,
  );
  expect(summary.href).toBeNull();
});

// AC4-N8 (negative): a date-change notice with no usable dates still tells them to check, with no detail line.
test("shows no detail line when the new dates are missing", () => {
  const summary = describeNotification(notice("event_changed", { proposed_date_times: [] }), ["attendee"]);
  expect(summary.message).toBe("The dates of Community Dinner have changed.");
  expect(summary.detail).toBeUndefined();
});
