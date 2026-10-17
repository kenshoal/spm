import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

const navigation = vi.hoisted(() => ({ redirect: vi.fn(), revalidatePath: vi.fn() }));
vi.mock("next/navigation", () => ({ redirect: navigation.redirect }));
vi.mock("next/cache", () => ({ revalidatePath: navigation.revalidatePath }));
const data = vi.hoisted(() => ({ bookings: vi.fn(), venues: vi.fn() }));
vi.mock("@/lib/event-bookings", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/event-bookings")>()),
  listEventBookings: data.bookings,
}));
vi.mock("@/lib/venues", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/venues")>()),
  listVenues: data.venues,
}));
vi.mock("@/lib/auth", () => ({
  requireAccessToken: async () => "valid-token",
  requireRole: async () => ({ id: "coord-1", email: "c@example.com", role: "event_coordinator", roles: ["event_coordinator"] }),
}));

import { cancelVenueBooking } from "@/app/coordination/requests/[id]/venue-booking-actions";
import { VenueBookingsList, VenueBookingsPanel } from "@/app/coordination/requests/[id]/venue-bookings-panel";
import type { EventBooking } from "@/lib/event-bookings";

afterEach(cleanup);
beforeEach(() => {
  vi.restoreAllMocks();
  navigation.redirect.mockReset();
  navigation.revalidatePath.mockReset();
  data.bookings.mockReset();
  data.venues.mockReset();
});

const EVENT_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const names = new Map([["v-a", "Hall A"], ["v-b", "Hall B"]]);

function booking(overrides: Partial<EventBooking>): EventBooking {
  return {
    id: "b1", venue_id: "v-a", start_date: "2030-01-10", end_date: "2030-01-10",
    slots: ["AM"], status: "pending", created_at: "2030-01-01T00:00:00Z", cancelled_at: null, ...overrides,
  };
}

const three: EventBooking[] = [
  booking({ id: "b1", venue_id: "v-a", status: "pending" }),
  booking({ id: "b2", venue_id: "v-b", status: "approved", start_date: "2030-01-10", end_date: "2030-01-12", slots: ["AM", "PM"] }),
  booking({ id: "b3", venue_id: "v-a", status: "cancelled", cancelled_at: "2030-01-05T00:00:00Z" }),
];

// AC3-U1 (happy): each booking shows its venue, dates, slots and status in words
test("lists each booking with venue, dates, slots and status", () => {
  render(<VenueBookingsList bookings={three} venueNames={names} eventRequestId={EVENT_ID} />);

  const rows = screen.getAllByRole("listitem");
  expect(rows).toHaveLength(3);
  expect(within(rows[0]).getByText("Hall A")).toBeDefined();
  expect(within(rows[0]).getByText("10 Jan 2030")).toBeDefined();
  expect(within(rows[0]).getByText("AM")).toBeDefined();
  expect(within(rows[0]).getByText("Pending")).toBeDefined();
  expect(within(rows[1]).getByText("10 Jan 2030 – 12 Jan 2030")).toBeDefined();
  expect(within(rows[1]).getByText("AM, PM")).toBeDefined();
  expect(within(rows[1]).getByText("Approved")).toBeDefined();
  expect(within(rows[2]).getByText("Cancelled")).toBeDefined();
});

// AC3-U1 (happy): a venue that cannot be named is still listed, not dropped
test("lists a booking whose venue name is unknown", () => {
  render(<VenueBookingsList bookings={[booking({ venue_id: "v-gone" })]} venueNames={names} eventRequestId={EVENT_ID} />);

  expect(screen.getByText("Unknown venue")).toBeDefined();
});

// AC3-U2 (boundary): an event with no bookings says so
test("says when the event has no venue bookings", () => {
  render(<VenueBookingsList bookings={[]} venueNames={names} eventRequestId={EVENT_ID} />);

  expect(screen.getByText("No venue bookings yet.")).toBeDefined();
});

// AC4-U1 (partition): Cancel is offered only for pending and approved bookings
test("offers Cancel only on pending and approved bookings", () => {
  render(<VenueBookingsList bookings={[...three, booking({ id: "b4", status: "rejected" })]} venueNames={names} eventRequestId={EVENT_ID} />);

  const rows = screen.getAllByRole("listitem");
  expect(within(rows[0]).getByRole("button", { name: /Cancel booking/ })).toBeDefined();
  expect(within(rows[1]).getByRole("button", { name: /Cancel booking/ })).toBeDefined();
  expect(within(rows[2]).queryByRole("button")).toBeNull();
  expect(within(rows[3]).queryByRole("button")).toBeNull();
});

// AC3-U1 (happy): the panel loads the bookings and venue names and renders them
test("the panel loads bookings and venue names", async () => {
  data.bookings.mockResolvedValue(three);
  data.venues.mockResolvedValue([{ id: "v-a", name: "Hall A" }, { id: "v-b", name: "Hall B" }]);

  render(await VenueBookingsPanel({ eventRequestId: EVENT_ID }));

  expect(data.bookings).toHaveBeenCalledWith(EVENT_ID);
  expect(screen.getAllByRole("listitem")).toHaveLength(3);
  expect(screen.getAllByText("Hall A").length).toBeGreaterThan(0);
});

// AC3-U3 (negative): a failed load shows an error and never an empty list
test("a failed load shows an alert, not an empty list", async () => {
  data.bookings.mockRejectedValue(new Error("down"));
  data.venues.mockResolvedValue([]);

  render(await VenueBookingsPanel({ eventRequestId: EVENT_ID }));

  expect(screen.getByRole("alert").textContent).toContain("could not be loaded");
  expect(screen.queryByText("No venue bookings yet.")).toBeNull();
});

// AC3-U3 (negative): venue names failing still lists the bookings
test("a venue-name failure still lists the bookings", async () => {
  data.bookings.mockResolvedValue(three);
  data.venues.mockRejectedValue(new Error("down"));

  render(await VenueBookingsPanel({ eventRequestId: EVENT_ID }));

  expect(screen.getAllByRole("listitem")).toHaveLength(3);
  expect(screen.getAllByText("Unknown venue").length).toBe(3);
});

function respond(status: number, body: unknown = {}) {
  const fetchMock = vi.fn().mockResolvedValue({ ok: status >= 200 && status < 300, status, json: async () => body });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function form(bookingId: string): FormData {
  const data = new FormData();
  data.set("booking_id", bookingId);
  data.set("event_request_id", EVENT_ID);
  return data;
}

// AC4-U2 (happy): cancelling sends one POST to the cancel path and refreshes the event page
test("cancel sends one POST and revalidates the event page", async () => {
  const fetchMock = respond(200, { id: "b1", status: "cancelled" });

  const state = await cancelVenueBooking({}, form("b1"));

  expect(fetchMock).toHaveBeenCalledTimes(1);
  const [url, init] = fetchMock.mock.calls[0];
  expect(String(url)).toMatch(/\/booking-requests\/b1\/cancel$/);
  expect(init.method).toBe("POST");
  expect(navigation.revalidatePath).toHaveBeenCalledWith(`/coordination/requests/${EVENT_ID}`);
  expect(state.message).toBeUndefined();
});

// AC4-U3 (negative): each failure is explained and nothing is revalidated
test.each([
  [404, "This booking could not be found, or the event is no longer assigned to you."],
  [409, "This booking can no longer be cancelled."],
  [403, "Only the event's coordinator can cancel a booking."],
  [502, "The booking could not be cancelled. Please try again."],
])("cancel explains a %i response", async (status, message) => {
  respond(status, { detail: "x" });

  const state = await cancelVenueBooking({}, form("b1"));

  expect(state.message).toBe(message);
  expect(navigation.revalidatePath).not.toHaveBeenCalled();
});

// AC4-U3 (negative): a network failure is explained
test("cancel explains a network failure", async () => {
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("down")));

  const state = await cancelVenueBooking({}, form("b1"));

  expect(state.message).toBe("The booking could not be cancelled. Please try again.");
});

// AC4-U3 (negative): an expired session goes to sign-in
test("cancel redirects to sign-in on 401", async () => {
  respond(401, { detail: "Invalid session" });
  navigation.redirect.mockImplementation(() => { throw new Error("NEXT_REDIRECT"); });

  await expect(cancelVenueBooking({}, form("b1"))).rejects.toThrow("NEXT_REDIRECT");

  expect(navigation.redirect).toHaveBeenCalledWith("/auth");
  expect(navigation.revalidatePath).not.toHaveBeenCalled();
});

// AC4-U3 (negative): a missing booking or event id sends nothing
test("cancel without ids sends no request", async () => {
  const fetchMock = respond(200);

  const state = await cancelVenueBooking({}, new FormData());

  expect(fetchMock).not.toHaveBeenCalled();
  expect(state.message).toBe("The booking could not be cancelled. Please try again.");
});
