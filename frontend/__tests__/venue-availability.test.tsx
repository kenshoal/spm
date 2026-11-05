import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

const auth = vi.hoisted(() => ({ requireAnyRole: vi.fn() }));
const data = vi.hoisted(() => ({ getVenueCalendar: vi.fn(), listVenues: vi.fn() }));
vi.mock("@/lib/auth", () => ({
  requireAnyRole: auth.requireAnyRole,
  requireAccessToken: async () => "token",
  requireRole: async () => ({ id: "c1", email: "c@example.com", role: "event_coordinator", roles: ["event_coordinator"] }),
}));
vi.mock("@/lib/venue-calendar", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/venue-calendar")>()),
  getVenueCalendar: data.getVenueCalendar,
}));
vi.mock("@/lib/venues", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/venues")>()),
  listVenues: data.listVenues,
}));
vi.mock("@/app/auth/actions", () => ({ logout: vi.fn() }));

import { currentMonth } from "@/lib/block-calendar";
import { AvailabilityCalendarTable } from "@/app/venues/availability/availability-calendar";
import VenueAvailabilityPage from "@/app/venues/availability/page";
import { VenueResults } from "@/app/venues/search/venue-results";
import { buildBlockCalendar } from "@/lib/block-calendar";
import { monthOfDate, type VenueCalendar } from "@/lib/venue-calendar";
import type { Venue } from "@/lib/venues";

afterEach(cleanup);

const hall: Venue = {
  id: "v1", name: "Riverside Hall", location: "Level 2", max_capacity: 120, facilities: [], accessibility_features: [],
  supported_layouts: ["theatre"], operating_slots: ["AM", "PM"], setup_minutes: 0, turnaround_minutes: 0, operating_start_minute: 420, operating_end_minute: 1440, status: "available",
  created_at: "2026-09-13T03:00:00Z", updated_at: "2026-09-13T03:00:00Z",
};
const studio: Venue = { ...hall, id: "v2", name: "Orchard Studio" };

type Entry = { state: "booked" | "blocked"; start_minute: number; end_minute: number };
type Free = { start_minute: number; end_minute: number };
const ALL_DAY: Free[] = [{ start_minute: 420, end_minute: 1440 }];

function calendar(
  month: string,
  days: number,
  overrides: Record<string, { entries?: Entry[]; free?: Free[]; unavailable?: boolean }> = {},
): VenueCalendar {
  return {
    venue_id: "v1",
    month,
    days: Array.from({ length: days }, (_, index) => {
      const date = `${month}-${String(index + 1).padStart(2, "0")}`;
      const { entries = [], free = ALL_DAY, unavailable = false } = overrides[date] ?? {};
      return { date, unavailable, entries, free };
    }),
  };
}

beforeEach(() => {
  auth.requireAnyRole.mockReset();
  auth.requireAnyRole.mockResolvedValue({ id: "c1", email: "c@example.com", role: "event_coordinator", roles: ["event_coordinator"] });
  data.getVenueCalendar.mockReset();
  data.getVenueCalendar.mockResolvedValue(calendar("2026-10", 31));
  data.listVenues.mockReset();
  data.listVenues.mockResolvedValue([hall, studio]);
});

async function openPage(params: Record<string, string> = {}) {
  render(await VenueAvailabilityPage({ searchParams: Promise.resolve({ month: "2026-10", ...params }) }));
}

// AC1-U1 (happy): the table lists each date with its booked, blocked and free times in words
test("shows every date with its booked, blocked and free times in words", () => {
  const table = calendar("2026-10", 3, {
    "2026-10-01": {
      entries: [
        { state: "booked", start_minute: 540, end_minute: 600 },
        { state: "blocked", start_minute: 600, end_minute: 660 },
        { state: "booked", start_minute: 660, end_minute: 720 },
      ],
      free: [{ start_minute: 420, end_minute: 540 }, { start_minute: 720, end_minute: 1440 }],
    },
  });

  render(<AvailabilityCalendarTable calendar={table} venueId="v1" venueName="Riverside Hall" />);

  const grid = screen.getByRole("table", { name: "Riverside Hall availability, October 2026" });
  expect(within(grid).getAllByRole("columnheader").map((cell) => cell.textContent)).toEqual(["Date", "Times"]);
  const rows = within(grid).getAllByRole("row").slice(1);
  expect(rows).toHaveLength(3);
  expect(within(rows[0]).getAllByRole("listitem").map((item) => item.textContent)).toEqual([
    "Booked 09:00–10:00",
    "Blocked 10:00–11:00",
    "Booked 11:00–12:00",
  ]);
  expect(within(rows[0]).getByText("Available 07:00–09:00, 12:00–24:00")).toBeDefined();
  expect(within(rows[1]).queryAllByRole("listitem")).toHaveLength(0);
  expect(within(rows[1]).getByText("Available all day")).toBeDefined();
});

// AC2-U1 (partition): a date with no free time says so and lists no free range
test("a fully booked date says there is no free time", () => {
  const table = calendar("2026-10", 1, {
    "2026-10-01": { entries: [{ state: "blocked", start_minute: 420, end_minute: 1440 }], free: [] },
  });

  render(<AvailabilityCalendarTable calendar={table} venueId="v1" venueName="Hall" />);

  expect(screen.getByText("Blocked 07:00–24:00")).toBeDefined();
  expect(screen.getByText("No free time")).toBeDefined();
  expect(screen.queryByText(/^Available/)).toBeNull();
});

// AC3-U1 (partition): an unavailable date reads "Unavailable" and lists no free time
test("an unavailable date is written as Unavailable with no free time", () => {
  const table = calendar("2026-10", 1, {
    "2026-10-01": { unavailable: true, free: [], entries: [{ state: "blocked", start_minute: 1080, end_minute: 1440 }] },
  });

  render(<AvailabilityCalendarTable calendar={table} venueId="v1" venueName="Hall" />);

  const row = screen.getAllByRole("row")[1];
  expect(within(row).getByText("Unavailable")).toBeDefined();
  expect(within(row).queryByText(/^Available/)).toBeNull();
  expect(within(row).queryByText("No free time")).toBeNull();
});

// AC5-U1 (cross-cutting): no slot vocabulary on the screen
test("the screen shows no AM, PM, Night or Not offered", () => {
  const table = calendar("2026-10", 2, {
    "2026-10-01": { entries: [{ state: "booked", start_minute: 540, end_minute: 720 }], free: [{ start_minute: 420, end_minute: 540 }, { start_minute: 720, end_minute: 1440 }] },
  });

  const { container } = render(<AvailabilityCalendarTable calendar={table} venueId="v1" venueName="Hall" />);

  for (const word of [/\bAM\b/, /\bPM\b/, /night/i, /not offered/i]) {
    expect(container.textContent).not.toMatch(word);
  }
});

// AC6-U1 (cross-cutting): the Venue Staff calendar has free time exactly when this calendar lists a free range
test("agrees with the Venue Staff calendar about which dates have free time", () => {
  const block = { id: "b1", venue_id: "v1", start_date: "2026-10-02", end_date: "2026-10-02", start_minute: 420, end_minute: 1440, reason_category: "maintenance", reason_detail: null, status: "active" } as never;
  const booking = { id: "r1", venue_id: "v1", start_date: "2026-10-03", end_date: "2026-10-03", start_minute: 540, end_minute: 720, status: "approved", event_name: "Gala" } as never;
  const staff = buildBlockCalendar({ id: "v1", status: "available" }, [block], "2026-10", [booking]);
  const mine = calendar("2026-10", 31, {
    "2026-10-02": { entries: [{ state: "blocked", start_minute: 420, end_minute: 1440 }], free: [] },
    "2026-10-03": { entries: [{ state: "booked", start_minute: 540, end_minute: 720 }], free: [{ start_minute: 420, end_minute: 540 }, { start_minute: 720, end_minute: 1440 }] },
  });

  for (const [index, day] of staff.days.entries()) {
    expect(mine.days[index].free.length > 0, day.date).toBe(day.free);
  }
});

// AC1-U2 (boundary): month links go to the previous and next month across year ends
test.each([
  ["2026-12", "2026-11", "2027-01"],
  ["2027-01", "2026-12", "2027-02"],
])("links month %s to %s and %s", (month, previous, next) => {
  render(<AvailabilityCalendarTable calendar={calendar(month, 1)} venueId="v 1" venueName="Hall" />);

  expect(screen.getByRole("link", { name: "Previous month" }).getAttribute("href")).toBe(`/venues/availability?venue=v%201&month=${previous}`);
  expect(screen.getByRole("link", { name: "Next month" }).getAttribute("href")).toBe(`/venues/availability?venue=v%201&month=${next}`);
});

// AC1-U1 (happy): the page shows the venue picker and the selected venue's calendar
test("the page shows the picker and the calendar of the chosen venue", async () => {
  await openPage({ venue: "v2" });

  expect(data.getVenueCalendar).toHaveBeenCalledWith("v2", "2026-10");
  expect((screen.getByLabelText("Show availability for") as HTMLSelectElement).value).toBe("v2");
  expect(screen.getByRole("table", { name: "Orchard Studio availability, October 2026" })).toBeDefined();
});

// AC1-U3 (negative): an unknown venue says so and shows no calendar
test("an unknown venue says so", async () => {
  data.getVenueCalendar.mockResolvedValue(null);

  await openPage({ venue: "v1" });

  expect(screen.getByText("Venue not found")).toBeDefined();
  expect(screen.queryByRole("table")).toBeNull();
});

// AC1-U4 (negative): a failed load shows an error, never an all-open calendar
test.each([
  ["the calendar", () => data.getVenueCalendar.mockRejectedValue(new Error("down"))],
  ["the venue list", () => data.listVenues.mockRejectedValue(new Error("down"))],
])("a failed load of %s shows an alert and no table", async (_name, arrange) => {
  arrange();

  await openPage({ venue: "v1" });

  expect(screen.getByRole("alert").textContent).toMatch(/could not be loaded|unavailable/i);
  expect(screen.queryByRole("table")).toBeNull();
});

// AC1-U5 (cross-cutting): only coordinators, venue staff and safety officers can open the page
test("the page is limited to coordinators, venue staff and safety officers", async () => {
  await openPage({ venue: "v1" });

  expect(auth.requireAnyRole).toHaveBeenCalledWith(["event_coordinator", "venue_staff", "safety_officer"]);
});

// AC1-U5 (cross-cutting): a refused role never reaches the data
test("a refused role fetches nothing", async () => {
  auth.requireAnyRole.mockRejectedValue(new Error("NEXT_REDIRECT"));

  await expect(openPage({ venue: "v1" })).rejects.toThrow("NEXT_REDIRECT");

  expect(data.listVenues).not.toHaveBeenCalled();
  expect(data.getVenueCalendar).not.toHaveBeenCalled();
});

// AC1-U6 (happy): each venue search result links to its availability
test("each search result links to that venue's availability", () => {
  render(<VenueResults venues={[hall]} />);

  const card = screen.getByRole("article", { name: "Riverside Hall" });
  expect(within(card).getByRole("link", { name: /View availability/ }).getAttribute("href")).toBe("/venues/availability?venue=v1");
});


// AC1-U2 (boundary): at the calendar's ends there is no link that would leave it
test("has no Previous link at 0001-01 and no Next link at 9999-12", () => {
  const { unmount } = render(<AvailabilityCalendarTable calendar={calendar("0001-01", 1)} venueId="v1" venueName="Hall" />);
  expect(screen.queryByRole("link", { name: "Previous month" })).toBeNull();
  expect(screen.getByRole("link", { name: "Next month" }).getAttribute("href")).toBe("/venues/availability?venue=v1&month=0001-02");
  unmount();

  render(<AvailabilityCalendarTable calendar={calendar("9999-12", 1)} venueId="v1" venueName="Hall" />);
  expect(screen.queryByRole("link", { name: "Next month" })).toBeNull();
  expect(screen.getByRole("link", { name: "Previous month" }).getAttribute("href")).toBe("/venues/availability?venue=v1&month=9999-11");
});

// AC1-U7 (negative): a month the API would refuse falls back to this month, not "Venue not found"
test.each(["0000-01", "2026-13", "abc"])("falls back to the current month for %j", async (month) => {
  await openPage({ venue: "v1", month });

  expect(data.getVenueCalendar).toHaveBeenCalledWith("v1", currentMonth());
  expect(screen.queryByText("Venue not found")).toBeNull();
});

// AC1-U8 (happy): the search-result link carries the month that was searched
test("the search-result link keeps the searched month", () => {
  render(<VenueResults venues={[hall]} month="2026-11" />);

  const card = screen.getByRole("article", { name: "Riverside Hall" });
  expect(within(card).getByRole("link", { name: /View availability/ }).getAttribute("href")).toBe("/venues/availability?venue=v1&month=2026-11");
});

// AC1-U8 (partition): only a real searched date gives a month
test.each([
  ["2026-11-14", "2026-11"],
  ["", null],
  ["abc", null],
  ["2026-13-01", null],
  ["0000-05-01", null],
])("takes the month of the searched date %j", (value, expected) => {
  expect(monthOfDate(value)).toBe(expected);
});
