import { expect, test } from "vitest";
import { describeNotification, type AppNotification } from "@/lib/notifications";

const EVENT = "57000000-0000-4000-8000-000000000001";

function notice(payload: Record<string, unknown> = {}): AppNotification {
  return {
    id: "notice-1", event_type: "event_cancellation_recorded", read_at: null, created_at: "2026-11-01T03:00:00Z",
    payload: { event_request_id: EVENT, event_name: "Community Dinner", ...payload },
  };
}

// AC1-X2 (cross-cutting): the Organiser sees which event was cancelled and is linked to it.
test("describes a recorded cancellation for the organiser with a link", () => {
  const summary = describeNotification(notice(), ["event_organiser"]);
  expect(summary.message).toBe("Community Dinner has been cancelled.");
  expect(summary.href).toBe(`/event-requests/${EVENT}/edit`);
});

// AC1-X2 (cross-cutting): the Coordinator is linked to the coordination page instead.
test("describes a recorded cancellation for the coordinator with their own link", () => {
  const summary = describeNotification(notice(), ["event_coordinator"]);
  expect(summary.message).toBe("Community Dinner has been cancelled.");
  expect(summary.href).toBe(`/coordination/requests/${EVENT}`);
});

// AC1-X2 (cross-cutting): a notice without an event name still reads well.
test("describes a recorded cancellation when the event has no name", () => {
  const summary = describeNotification(notice({ event_name: null }), ["event_organiser"]);
  expect(summary.message).toBe("Your event has been cancelled.");
});
