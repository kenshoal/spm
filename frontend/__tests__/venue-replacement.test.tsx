import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

const navigation = vi.hoisted(() => ({ redirect: vi.fn(), revalidatePath: vi.fn() }));
vi.mock("next/navigation", () => ({ redirect: navigation.redirect }));
vi.mock("next/cache", () => ({ revalidatePath: navigation.revalidatePath }));
const data = vi.hoisted(() => ({ bookings: vi.fn(), venues: vi.fn(), reviews: vi.fn() }));
vi.mock("@/lib/event-bookings", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/event-bookings")>()),
  listEventBookings: data.bookings,
}));
vi.mock("@/lib/venues", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/venues")>()),
  listVenues: data.venues,
}));
vi.mock("@/lib/arrangement-reviews", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/arrangement-reviews")>()),
  listEventArrangementReviews: data.reviews,
}));
vi.mock("@/lib/auth", () => ({
  requireAccessToken: async () => "valid-token",
  requireRole: async () => ({ id: "coord-1", email: "c@example.com", role: "event_coordinator", roles: ["event_coordinator"] }),
}));

import { ConflictWarning } from "@/app/coordination/requests/[id]/conflict-warning";
import { requestReplacementVenue } from "@/app/coordination/requests/[id]/venue-booking-actions";
import { VenueBookingsList, VenueBookingsPanel } from "@/app/coordination/requests/[id]/venue-bookings-panel";
import type { ArrangementReview } from "@/lib/arrangement-reviews";
import { needsNewVenue, type EventBooking } from "@/lib/event-bookings";

afterEach(cleanup);
beforeEach(() => {
  vi.restoreAllMocks();
  for (const mock of [navigation.redirect, navigation.revalidatePath, data.bookings, data.venues, data.reviews]) mock.mockReset();
});

const EVENT_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const names = new Map([["v-a", "Blocked Hall"], ["v-b", "Second Hall"], ["v-c", "Third Hall"]]);
const venues = [
  { id: "v-a", name: "Blocked Hall", status: "available" },
  { id: "v-b", name: "Second Hall", status: "available" },
  { id: "v-c", name: "Third Hall", status: "blocked" },
  { id: "v-d", name: "Fourth Hall", status: "available" },
];

function booking(overrides: Partial<EventBooking>): EventBooking {
  return {
    id: "b1", venue_id: "v-a", start_date: "2030-03-10", end_date: "2030-03-10",
    start_minute: 540, end_minute: 720, slots: ["AM"], status: "approved", created_at: "2030-03-01T00:00:00Z",
    cancelled_at: null, replaces_booking_id: null, ...overrides,
  };
}

function review(overrides: Partial<ArrangementReview>): ArrangementReview {
  return {
    id: "r1", event_request_id: EVENT_ID, arrangement: "venue_booking", arrangement_id: "b1", trigger_id: "t1",
    trigger_type: "venue_block", changed_fields: [], reason: "Venue Blocked Hall is blocked from 2030-03-10 to 2030-03-10, 10:00 to 11:00; this booking needs a new venue.",
    raised_at: "2030-03-02T00:00:00Z", cleared_at: null, cleared_by: null, ...overrides,
  };
}

const flags = needsNewVenue([review({})]);

// AC3-H1 (happy): a flagged booking shows "Needs a new venue" and its reason beside its status
test("a flagged booking says it needs a new venue, with the reason", () => {
  render(<VenueBookingsList bookings={[booking({})]} venueNames={names} eventRequestId={EVENT_ID} needsNewVenue={flags} replacementVenues={[]} />);

  const row = screen.getByRole("listitem");
  expect(within(row).getByText("Approved")).toBeDefined();
  expect(within(row).getByText("Needs a new venue")).toBeDefined();
  expect(within(row).getByText(/is blocked from 2030-03-10/)).toBeDefined();
});

// AC3-P1 (partition): an unflagged booking shows nothing extra
test("an unflagged booking shows no flag text and no replacement form", () => {
  render(<VenueBookingsList bookings={[booking({ id: "b2" })]} venueNames={names} eventRequestId={EVENT_ID} needsNewVenue={flags} replacementVenues={venues} />);

  expect(screen.queryByText("Needs a new venue")).toBeNull();
  expect(screen.queryByRole("button", { name: /Request replacement/ })).toBeNull();
});

// AC3-P2 (partition): a cleared flag, a flag of another cause and one for equipment are not shown
test.each([
  ["cleared", review({ cleared_at: "2030-03-03T00:00:00Z", cleared_by: "u1" })],
  ["another cause", review({ trigger_type: "venue_timing_change" })],
  ["equipment", review({ arrangement: "equipment_reservation" })],
])("%s does not count as needing a new venue", (_name, row) => {
  expect(needsNewVenue([row]).size).toBe(0);
});

// AC4-X2 (cross-cutting): the replacement form is offered for a flagged approved booking only
test.each([
  ["pending", "pending", false],
  ["cancelled", "cancelled", false],
  ["approved", "approved", true],
])("a %s flagged booking %s the replacement form", (_label, status, offered) => {
  render(<VenueBookingsList bookings={[booking({ status: status as EventBooking["status"] })]} venueNames={names} eventRequestId={EVENT_ID} needsNewVenue={flags} replacementVenues={venues} />);

  expect(screen.queryByRole("button", { name: /Request replacement/ }) !== null).toBe(offered);
});

// AC4-X2 (cross-cutting): the form lists available venues other than the blocked one, with accessible names
test("the replacement form offers only other available venues", () => {
  render(<VenueBookingsList bookings={[booking({})]} venueNames={names} eventRequestId={EVENT_ID} needsNewVenue={flags} replacementVenues={venues} />);

  const select = screen.getByRole("combobox", { name: /Replacement venue/ }) as HTMLSelectElement;
  expect([...select.options].map((option) => option.text)).toEqual(["Choose a venue", "Second Hall", "Fourth Hall"]);
  expect(screen.getByRole("button", { name: "Request replacement for Blocked Hall" })).toBeDefined();
  expect((document.querySelector('input[name="booking_id"]') as HTMLInputElement).value).toBe("b1");
});

// AC4-H2 (happy): a replacement request says which booking it replaces
test("a replacement booking says which venue it replaces", () => {
  render(
    <VenueBookingsList
      bookings={[booking({ id: "b1", status: "approved" }), booking({ id: "b9", venue_id: "v-b", status: "pending", replaces_booking_id: "b1" })]}
      venueNames={names}
      eventRequestId={EVENT_ID}
      needsNewVenue={new Map()}
      replacementVenues={[]}
    />,
  );

  const rows = screen.getAllByRole("listitem");
  expect(within(rows[1]).getByText("Replaces the booking at Blocked Hall")).toBeDefined();
  expect(within(rows[0]).queryByText(/Replaces the booking/)).toBeNull();
});

// AC4-X3 (cross-cutting): once a replacement is pending or approved, its status replaces the form; a rejected one does not
test.each([
  ["pending", "Replacement requested at Second Hall (Pending)", false],
  ["approved", "Replacement requested at Second Hall (Approved)", false],
  ["rejected", null, true],
  ["cancelled", null, true],
])("with a %s replacement the form is %s", (status, text, formShown) => {
  render(
    <VenueBookingsList
      bookings={[booking({ id: "b1" }), booking({ id: "b9", venue_id: "v-b", status: status as EventBooking["status"], replaces_booking_id: "b1" })]}
      venueNames={names}
      eventRequestId={EVENT_ID}
      needsNewVenue={flags}
      replacementVenues={venues}
    />,
  );

  expect(screen.queryByRole("button", { name: /Request replacement for/ }) !== null).toBe(formShown);
  if (text) expect(screen.getByText(text)).toBeDefined();
  else expect(screen.queryByText(/Replacement requested at/)).toBeNull();
});

// AC3-H1 (happy): the panel reads the flags from the event's arrangement reviews
test("the panel marks the flagged booking from the event's reviews", async () => {
  data.bookings.mockResolvedValue([booking({})]);
  data.venues.mockResolvedValue(venues);
  data.reviews.mockResolvedValue([review({})]);

  render(await VenueBookingsPanel({ eventRequestId: EVENT_ID }));

  expect(data.reviews).toHaveBeenCalledWith(EVENT_ID);
  expect(screen.getByText("Needs a new venue")).toBeDefined();
  expect(screen.getByRole("button", { name: "Request replacement for Blocked Hall" })).toBeDefined();
});

// AC3-N1 (negative): a failed flag load is an alert, not "nothing needs a new venue"; the bookings still list
test("a failed flag load shows an alert and still lists the bookings", async () => {
  data.bookings.mockResolvedValue([booking({})]);
  data.venues.mockResolvedValue(venues);
  data.reviews.mockRejectedValue(new Error("down"));

  render(await VenueBookingsPanel({ eventRequestId: EVENT_ID }));

  expect(screen.getByRole("alert").textContent).toMatch(/could not be checked/i);
  expect(screen.getByText("Blocked Hall")).toBeDefined();
  expect(screen.queryByText("Needs a new venue")).toBeNull();
});

function form(fields: Record<string, string | undefined>): FormData {
  const data = new FormData();
  for (const [name, value] of Object.entries(fields)) if (value !== undefined) data.set(name, value);
  return data;
}

function respond(status: number, body: unknown = {}) {
  const fetchMock = vi.fn().mockResolvedValue({ ok: status >= 200 && status < 300, status, json: async () => body });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

// AC4-H1 (happy): the request is one POST with the venue, then the event page refreshes
test("sends one POST to the replacement path and refreshes the event page", async () => {
  const fetchMock = respond(201, { id: "new" });

  const state = await requestReplacementVenue({}, form({ booking_id: "b1", event_request_id: EVENT_ID, venue_id: "v-b" }));

  expect(state).toEqual({});
  expect(fetchMock).toHaveBeenCalledTimes(1);
  const [url, init] = fetchMock.mock.calls[0];
  expect(String(url)).toMatch(/\/booking-requests\/b1\/replacement$/);
  expect(init.method).toBe("POST");
  expect(JSON.parse(init.body)).toEqual({ venue_id: "v-b" });
  expect(navigation.revalidatePath).toHaveBeenCalledWith(`/coordination/requests/${EVENT_ID}`);
});

// AC4-N1 to AC4-N7 (negative): each refusal is explained and nothing is revalidated
test.each([
  [404, { detail: "Event request not found" }, /no longer assigned to you/],
  [403, { detail: "Insufficient permissions" }, /Only the event's coordinator/],
  [409, { detail: "Booking is not flagged as needing a new venue" }, /no longer needs a new venue/],
  [409, { detail: "Booking is not approved" }, /Only an approved booking/],
  [409, { detail: "A replacement has already been requested" }, /already been requested/],
  [409, { detail: "Event request changed; refresh before booking" }, /event changed/i],
  [422, { detail: "A replacement must be at a different venue" }, /different venue/],
  [500, { detail: "boom" }, /could not be requested/],
])("a %s refusal is explained", async (status, body, message) => {
  respond(status, body);

  const state = await requestReplacementVenue({}, form({ booking_id: "b1", event_request_id: EVENT_ID, venue_id: "v-b" }));

  expect(state.message).toMatch(message);
  expect(navigation.revalidatePath).not.toHaveBeenCalled();
});

// AC4-N8 (negative): a network failure is explained
test("explains a network failure", async () => {
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("down")));

  const state = await requestReplacementVenue({}, form({ booking_id: "b1", event_request_id: EVENT_ID, venue_id: "v-b" }));

  expect(state.message).toMatch(/could not be requested/);
});

// AC4-N9 (negative): an expired session goes to sign-in
test("redirects to sign-in on 401", async () => {
  respond(401, { detail: "Authentication required" });
  navigation.redirect.mockImplementation(() => { throw new Error("NEXT_REDIRECT"); });

  await expect(requestReplacementVenue({}, form({ booking_id: "b1", event_request_id: EVENT_ID, venue_id: "v-b" }))).rejects.toThrow("NEXT_REDIRECT");

  expect(navigation.redirect).toHaveBeenCalledWith("/auth");
});

// AC4-N10 (negative): no venue chosen, or missing ids, sends nothing
test.each([
  ["no venue", { booking_id: "b1", event_request_id: EVENT_ID, venue_id: "" }, /Choose a venue/],
  ["no booking", { booking_id: "", event_request_id: EVENT_ID, venue_id: "v-b" }, /could not be requested/],
])("%s sends no request", async (_name, fields, message) => {
  const fetchMock = respond(201);

  const state = await requestReplacementVenue({}, form(fields));

  expect(state.message).toMatch(message);
  expect(fetchMock).not.toHaveBeenCalled();
});


const clash = { start_date: "2030-03-10", end_date: "2030-03-10", start_minute: 540, end_minute: 720 };

// AC1-U1 (happy, SCRUM-67): the warning names each clash by date and time, says the request was still submitted, and uses words
test("the warning names the clash and says the request was submitted", () => {
  render(<ConflictWarning venueName="Second Hall" conflicts={[clash, { ...clash, start_date: "2030-03-11", end_date: "2030-03-12", start_minute: 840, end_minute: 900 }]} />);

  const warning = screen.getByRole("status");
  expect(warning.textContent).toContain("Second Hall already has an approved booking that overlaps this request");
  expect(within(warning).getAllByRole("listitem").map((item) => item.textContent)).toEqual([
    "10 Mar 2030, 09:00–12:00",
    "11 Mar 2030 – 12 Mar 2030, 14:00–15:00",
  ]);
  expect(warning.textContent).toMatch(/setup and turnaround/i);
  expect(warning.textContent).toMatch(/still been submitted/i);
});

// AC1-U3 (partition, SCRUM-67): no clash shows no warning
test("no clash shows no warning", () => {
  const { container } = render(<ConflictWarning venueName="Second Hall" conflicts={[]} />);

  expect(container.textContent).toBe("");
  expect(screen.queryByRole("status")).toBeNull();
});

// AC1-U2 (happy, SCRUM-67): the action hands the clashes from the response to the form
test("returns the clashes listed in the response", async () => {
  respond(201, { id: "new", conflicts: [clash] });

  const state = await requestReplacementVenue({}, form({ booking_id: "b1", event_request_id: EVENT_ID, venue_id: "v-b" }));

  expect(state).toEqual({ conflicts: [clash] });
  expect(navigation.revalidatePath).toHaveBeenCalledWith(`/coordination/requests/${EVENT_ID}`);
});

// AC1-U4 (partition, SCRUM-67): a response with no clash list, or a malformed one, gives none
test.each([
  ["absent", { id: "new" }],
  ["empty", { id: "new", conflicts: [] }],
  ["malformed", { id: "new", conflicts: [{ start_date: 5 }, "x", null] }],
])("a %s clash list gives no warning", async (_name, body) => {
  respond(201, body);

  const state = await requestReplacementVenue({}, form({ booking_id: "b1", event_request_id: EVENT_ID, venue_id: "v-b" }));

  expect(state).toEqual({});
});
