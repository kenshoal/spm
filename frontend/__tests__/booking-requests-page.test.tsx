import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

const auth = vi.hoisted(() => ({ requireRole: vi.fn() }));
const data = vi.hoisted(() => ({ listBookingRequests: vi.fn(), listVenues: vi.fn() }));
vi.mock("@/lib/auth", () => ({ requireRole: auth.requireRole }));
vi.mock("@/lib/booking-requests", () => ({ listBookingRequests: data.listBookingRequests }));
vi.mock("@/lib/venues", () => ({ listVenues: data.listVenues }));
vi.mock("@/app/booking-requests/actions", () => ({ decideBookingRequest: vi.fn() }));
vi.mock("@/app/auth/actions", () => ({ logout: vi.fn() }));

import BookingRequestsPage from "@/app/booking-requests/page";
import type { BookingRequestItem } from "@/lib/booking-decision-form";

afterEach(cleanup);

const pending: BookingRequestItem = {
  id: "b1",
  venue_id: "v1",
  requested_by: "c1",
  event_request_id: "e1",
  event_name: "Open day",
  expected_attendance: 80,
  requirements_note: "Projector and ramp",
  start_date: "2026-10-20",
  end_date: "2026-10-21",
  start_minute: 420,
  end_minute: 1080,
  slots: ["AM", "PM"],
  status: "pending",
  decision_reason: null,
  suggested_alternative: null,
  decided_by: null,
  decided_at: null,
  created_at: "2026-10-05T02:00:00Z",
};

async function openPage(params: Record<string, string> = {}) {
  render(await BookingRequestsPage({ searchParams: Promise.resolve(params) }));
}

beforeEach(() => {
  auth.requireRole.mockReset();
  auth.requireRole.mockResolvedValue({ id: "staff-1", email: "s@example.com", role: "venue_staff", roles: ["venue_staff"] });
  data.listBookingRequests.mockReset();
  data.listBookingRequests.mockResolvedValue([pending]);
  data.listVenues.mockReset();
  data.listVenues.mockResolvedValue([{ id: "v1", name: "Riverside Hall" }]);
});

// AC1-H6 (happy): the pending queue shows each request's details with approve and reject controls
test("lists pending requests with their details and decision controls", async () => {
  await openPage();

  expect(data.listBookingRequests).toHaveBeenCalledWith("pending");
  const card = screen.getByRole("article", { name: "Open day" });
  for (const text of ["Riverside Hall", "20 Oct 2026 – 21 Oct 2026", "07:00–18:00", "80 attendees", "Projector and ramp"]) {
    expect(within(card).getByText(new RegExp(text))).toBeDefined();
  }
  expect(within(card).getByRole("button", { name: "Approve" })).toBeDefined();
  expect(within(card).getByRole("button", { name: "Reject" })).toBeDefined();
  expect(within(card).getByLabelText("Reason for rejecting")).toBeDefined();
  expect(within(card).getByLabelText(/Suggested alternative/)).toBeDefined();
});

// AC1-H7 (happy): decided requests show the outcome without decision controls
test("shows a rejected request's reason and alternative without controls", async () => {
  data.listBookingRequests.mockResolvedValue([
    { ...pending, status: "rejected", decision_reason: "Hall under repair", suggested_alternative: "Try Orchard Studio", decided_at: "2026-10-07T03:00:00Z" },
  ]);

  await openPage({ status: "rejected" });

  expect(data.listBookingRequests).toHaveBeenCalledWith("rejected");
  const card = screen.getByRole("article", { name: "Open day" });
  expect(within(card).getByText(/Hall under repair/)).toBeDefined();
  expect(within(card).getByText(/Try Orchard Studio/)).toBeDefined();
  expect(within(card).queryByRole("button")).toBeNull();
  expect(screen.getByRole("link", { name: "Rejected" }).getAttribute("aria-current")).toBe("page");
});

// AC1-H8 (happy): a saved decision is confirmed on return to the queue
test("confirms a saved decision", async () => {
  await openPage({ decided: "approved" });

  expect(screen.getByRole("status").textContent).toBe("Booking approved. The requesting Coordinator has been notified.");
});

// AC1-P1 (partition): an unknown status falls back to the pending queue
test("falls back to the pending queue for an unknown status", async () => {
  await openPage({ status: "cancelled" });

  expect(data.listBookingRequests).toHaveBeenCalledWith("pending");
});

// AC1-P2 (partition): an empty queue is stated plainly
test("explains an empty queue", async () => {
  data.listBookingRequests.mockResolvedValue([]);

  await openPage();

  expect(screen.getByText("No pending booking requests.")).toBeDefined();
});

// AC1-X3 (cross-cutting): the page checks the Venue Staff role before loading any data
test("requires the Venue Staff role before loading data", async () => {
  auth.requireRole.mockRejectedValue(new Error("NEXT_REDIRECT"));

  await expect(BookingRequestsPage({ searchParams: Promise.resolve({}) })).rejects.toThrow("NEXT_REDIRECT");

  expect(auth.requireRole).toHaveBeenCalledWith("venue_staff");
  expect(data.listBookingRequests).not.toHaveBeenCalled();
});

// AC1-N8 (negative): an unavailable venue service is reported, never shown as an empty queue
test("reports an unavailable venue service", async () => {
  data.listBookingRequests.mockRejectedValue(new Error("down"));

  await openPage();

  expect(screen.getByRole("alert").textContent).toContain("The venue service is unavailable.");
  expect(screen.queryByText("No pending booking requests.")).toBeNull();
});
