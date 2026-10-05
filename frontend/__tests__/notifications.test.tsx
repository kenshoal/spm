import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

vi.mock("@/app/notifications/actions", () => ({ markNotificationRead: vi.fn().mockResolvedValue({}) }));

import { NotificationList } from "@/app/notifications/notification-list";
import { describeNotification, type AppNotification } from "@/lib/notifications";

afterEach(cleanup);

function makeNotification(overrides: Partial<AppNotification> = {}): AppNotification {
  return {
    id: "n1",
    event_type: "event_request_submitted",
    payload: { event_request_id: "req-1", organiser_id: "org-1", status: "Submitted" },
    read_at: null,
    created_at: "2026-10-02T03:15:00Z",
    ...overrides,
  };
}

// AC1-H1 (happy): SCRUM-37 AC1 — the Organiser's confirmation says the request was submitted and links to it.
test("describes a submission confirmation with a link to the organiser's request", () => {
  expect(describeNotification(makeNotification())).toEqual({
    message: "Your event request was submitted.",
    href: "/event-requests/req-1/edit",
  });
});

// AC2-H1 (happy): SCRUM-37 AC2 — the assigned Coordinator's notification links to their coordination view.
test("describes a coordinator assignment with a link to the coordination view", () => {
  const notification = makeNotification({
    event_type: "coordinator_assigned",
    payload: { event_request_id: "req-2", coordinator_id: "coord-1", assigned_by: "ops-1" },
  });

  expect(describeNotification(notification)).toEqual({
    message: "You've been assigned an event request.",
    href: "/coordination/requests/req-2",
  });
});

// AC3-H1 (happy): SCRUM-37 AC3 — the Organiser is told a clarification was requested, is shown what
// the Coordinator needs, and is linked to the request where they can respond.
test("describes a clarification request with the reason and a link to the request", () => {
  const notification = makeNotification({
    event_type: "clarification_requested",
    payload: { event_request_id: "req-3", reason: "Please clarify the accessibility plan." },
  });

  expect(describeNotification(notification)).toEqual({
    message: "A coordinator has asked for clarification on your event request.",
    href: "/event-requests/req-3/edit",
    detail: "Please clarify the accessibility plan.",
  });
});

// AC3-P3 (partition): A clarification notice with no usable reason still shows and links, without a
// blank or "undefined" detail line.
test.each([{}, { reason: "   " }, { reason: 42 }])(
  "shows a clarification request without a detail line when the reason is %j",
  (extra) => {
    const notification = makeNotification({
      event_type: "clarification_requested",
      payload: { event_request_id: "req-3", ...extra },
    });

    const summary = describeNotification(notification);
    expect(summary.message).toBe("A coordinator has asked for clarification on your event request.");
    expect(summary.href).toBe("/event-requests/req-3/edit");
    expect(summary.detail).toBeUndefined();
  },
);

// AC3-H1 (happy): The inbox card for a clarification request shows the reason the Coordinator gave.
test("shows the clarification the coordinator asked for on the notification", () => {
  render(
    <NotificationList
      notifications={[
        makeNotification({
          event_type: "clarification_requested",
          payload: { event_request_id: "req-3", reason: "Please clarify the accessibility plan." },
        }),
      ]}
    />,
  );

  const card = screen.getByRole("article", {
    name: "A coordinator has asked for clarification on your event request.",
  });
  expect(within(card).getByText("Please clarify the accessibility plan.")).toBeDefined();
  expect(within(card).getByRole("link", { name: "View request" }).getAttribute("href")).toBe(
    "/event-requests/req-3/edit",
  );
});

// AC6-P4 (partition): A type this page doesn't know yet (e.g. a venue booking decision) still shows,
// without guessing which view the recipient can open.
test("falls back to a generic message without a link for an unknown type", () => {
  expect(describeNotification(makeNotification({ event_type: "venue_booking_decided" }))).toEqual({
    message: "There's an update on an event request.",
    href: null,
  });
});

// AC6-N6 (negative): The id is encoded into the path, so an odd payload can't produce a link to another route.
test("encodes the event request id in the link", () => {
  expect(describeNotification(makeNotification({ payload: { event_request_id: "a/b" } })).href).toBe(
    "/event-requests/a%2Fb/edit",
  );
});

// AC6-N6 (negative): Without an event request id there is nothing to link to.
test("omits the link when the payload has no event request id", () => {
  expect(describeNotification(makeNotification({ payload: {} })).href).toBeNull();
});

// AC6-P1 (partition): Unread notifications stand out and offer "Mark as read"; read ones don't.
test("offers mark as read only on unread notifications", () => {
  render(
    <NotificationList
      notifications={[
        makeNotification({ id: "n1" }),
        makeNotification({ id: "n2", event_type: "coordinator_assigned", read_at: "2026-10-02T04:00:00Z" }),
      ]}
    />,
  );

  const unread = screen.getByRole("article", { name: "Your event request was submitted." });
  expect(within(unread).getByText("Unread")).toBeDefined();
  expect(within(unread).getByRole("button", { name: "Mark as read" })).toBeDefined();

  const read = screen.getByRole("article", { name: "You've been assigned an event request." });
  expect(within(read).queryByText("Unread")).toBeNull();
  expect(within(read).queryByRole("button", { name: "Mark as read" })).toBeNull();
});

// AC6-H1 (happy): Each notification shows when it happened, in Singapore time, and links to its request.
test("shows when it happened and links to the request", () => {
  render(<NotificationList notifications={[makeNotification()]} />);

  const card = screen.getByRole("article", { name: "Your event request was submitted." });
  expect(within(card).getByText(/^2 Oct 2026, 11:15\sam$/)).toBeDefined();
  expect(within(card).getByRole("link", { name: "View request" }).getAttribute("href")).toBe(
    "/event-requests/req-1/edit",
  );
});

// AC6-P4 (partition): An unknown type is listed without a dead "View request" link.
test("shows no link for a notification without a destination", () => {
  render(<NotificationList notifications={[makeNotification({ event_type: "venue_booking_decided" })]} />);

  const card = screen.getByRole("article", { name: "There's an update on an event request." });
  expect(within(card).queryByRole("link", { name: "View request" })).toBeNull();
});

// AC6-P5 (partition): A user with no notifications sees that, not a blank page.
test("shows an empty state when there are no notifications", () => {
  render(<NotificationList notifications={[]} />);

  expect(screen.getByText("No notifications yet.")).toBeDefined();
});
