import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, onTestFinished, test, vi } from "vitest";

const auth = vi.hoisted(() => ({ requireRole: vi.fn() }));
const data = vi.hoisted(() => ({ listVenues: vi.fn(), listVenueBlocks: vi.fn(), listApprovedBookings: vi.fn() }));
vi.mock("@/lib/auth", () => ({ requireRole: auth.requireRole }));
vi.mock("@/lib/venues", () => ({ listVenues: data.listVenues }));
vi.mock("@/lib/venue-blocks", () => ({ listVenueBlocks: data.listVenueBlocks }));
vi.mock("@/lib/venue-bookings", () => ({ listApprovedBookings: data.listApprovedBookings }));
vi.mock("@/app/venue-blocks/actions", () => ({ createVenueBlock: vi.fn() }));
vi.mock("@/app/auth/actions", () => ({ logout: vi.fn() }));

import VenueBlocksPage from "@/app/venue-blocks/page";
import type { VenueBlock } from "@/lib/venue-block-options";
import type { Venue } from "@/lib/venues";

afterEach(cleanup);

const hall: Venue = {
  id: "v1",
  name: "Riverside Hall",
  location: "Level 2",
  max_capacity: 120,
  facilities: [],
  accessibility_features: [],
  supported_layouts: ["theatre"],
  operating_slots: ["AM", "PM"],
  status: "available",
  created_at: "2026-09-13T03:00:00Z",
  updated_at: "2026-09-13T03:00:00Z",
};
const studio: Venue = { ...hall, id: "v2", name: "Orchard Studio" };

const repairs: VenueBlock = {
  id: "b1",
  venue_id: "v1",
  start_date: "2026-10-20",
  end_date: "2026-10-21",
  slots: ["AM", "PM"],
  reason_category: "maintenance",
  reason_detail: "Air-con repairs",
  status: "active",
  created_by: "staff-1",
  created_at: "2026-10-01T02:00:00Z",
};

async function openPage(params: Record<string, string> = {}) {
  render(await VenueBlocksPage({ searchParams: Promise.resolve({ month: "2026-10", ...params }) }));
}

beforeEach(() => {
  auth.requireRole.mockReset();
  auth.requireRole.mockResolvedValue({ id: "staff-1", email: "staff@example.com", role: "venue_staff", roles: ["venue_staff"] });
  data.listVenues.mockReset();
  data.listVenues.mockResolvedValue([hall, studio]);
  data.listVenueBlocks.mockReset();
  data.listVenueBlocks.mockResolvedValue([repairs]);
  data.listApprovedBookings.mockReset();
  data.listApprovedBookings.mockResolvedValue([]);
});

// AC4-H1 (happy): the selected venue's covered cells read "Blocked" with the reason
test("shows the selected venue's blocked cells with their reason", async () => {
  await openPage({ venue: "v1" });

  expect(data.listVenueBlocks).toHaveBeenCalledWith("v1");
  const table = screen.getByRole("table", { name: "Riverside Hall availability, October 2026" });
  const row = within(table).getByRole("row", { name: /Tue 20 Oct/ });
  expect(within(row).getAllByText("Blocked")).toHaveLength(2);
  expect(within(row).getAllByText("Maintenance — Air-con repairs")).toHaveLength(2);
  expect(within(row).getByText("Not offered")).toBeDefined();
  const nextDay = within(table).getByRole("row", { name: /Thu 22 Oct/ });
  expect(within(nextDay).queryByText("Blocked")).toBeNull();
  expect(within(nextDay).getAllByText("Available")).toHaveLength(2);
  expect(screen.getByRole("link", { name: "Next month" }).getAttribute("href")).toBe("/venue-blocks?venue=v1&month=2026-11");
  expect(screen.getByRole("link", { name: "Previous month" }).getAttribute("href")).toBe("/venue-blocks?venue=v1&month=2026-09");
});

// AC4-P6 (partition): a venue blocked in the catalogue is flagged and never shown as available
test("flags a venue that is blocked in the catalogue", async () => {
  data.listVenues.mockResolvedValue([{ ...hall, status: "blocked" }, studio]);

  await openPage({ venue: "v1" });

  expect(screen.getByRole("note").textContent).toContain("This venue is blocked in the catalogue, so it is unavailable on every date.");
  const table = screen.getByRole("table", { name: "Riverside Hall availability, October 2026" });
  expect(within(table).queryByText("Available")).toBeNull();
  const row = within(table).getByRole("row", { name: /Thu 22 Oct/ });
  expect(within(row).getAllByText("Unavailable")).toHaveLength(2);
  expect(within(table).getAllByText("Maintenance — Air-con repairs")).toHaveLength(4);
  expect(screen.getByRole("form", { name: "Block a venue" })).toBeDefined();
});

// AC4-P6 (partition): an available venue shows no catalogue warning
test("shows no catalogue warning for an available venue", async () => {
  await openPage({ venue: "v1" });

  expect(screen.queryByRole("note")).toBeNull();
});

// AC1-H2 (happy): after saving, the staffer sees a confirmation and the block in the recorded list
test("confirms a saved block and lists it", async () => {
  await openPage({ venue: "v1", created: "1" });

  expect(screen.getByRole("status").textContent).toBe("Block saved.");
  const list = screen.getByRole("list", { name: "Recorded blocks" });
  const item = within(list).getByRole("listitem");
  expect(item.textContent).toContain("20 Oct 2026 – 21 Oct 2026");
  expect(item.textContent).toContain("AM, PM");
  expect(item.textContent).toContain("Maintenance — Air-con repairs");
  expect(item.textContent).toContain("Active");
});

// AC1-H1 (happy): the form offers every field and preselects the venue being viewed
test("offers every block field with the viewed venue preselected", async () => {
  await openPage({ venue: "v2" });

  const form = screen.getByRole("form", { name: "Block a venue" });
  expect((within(form).getByLabelText("Venue") as HTMLSelectElement).value).toBe("v2");
  expect(within(form).getByLabelText("Start date")).toBeDefined();
  expect(within(form).getByLabelText("End date")).toBeDefined();
  for (const slot of ["AM", "PM", "NIGHT"]) {
    expect(within(form).getByRole("checkbox", { name: slot })).toBeDefined();
  }
  const reason = within(form).getByLabelText("Reason") as HTMLSelectElement;
  expect([...reason.options].map((o) => o.textContent)).toEqual(["Choose a reason", "Maintenance", "Renovation", "Safety", "Internal use"]);
  expect(within(form).getByLabelText(/Detail/)).toBeDefined();
  expect(within(form).getByRole("button", { name: "Block venue" })).toBeDefined();
});

// AC4-H1 (happy): without a venue in the URL the first catalogue venue is shown
test("defaults to the first venue in the catalogue", async () => {
  await openPage();

  expect(data.listVenueBlocks).toHaveBeenCalledWith("v1");
  expect(screen.getByRole("table", { name: "Riverside Hall availability, October 2026" })).toBeDefined();
});

// AC1-X1 (cross-cutting): the page checks the Venue Staff role before loading any venue data
test("requires the Venue Staff role before loading data", async () => {
  auth.requireRole.mockRejectedValue(new Error("NEXT_REDIRECT"));

  await expect(VenueBlocksPage({ searchParams: Promise.resolve({}) })).rejects.toThrow("NEXT_REDIRECT");

  expect(auth.requireRole).toHaveBeenCalledWith("venue_staff");
  expect(data.listVenues).not.toHaveBeenCalled();
  expect(data.listVenueBlocks).not.toHaveBeenCalled();
});

// AC4-N1 (negative): an unavailable venue service is reported instead of an empty page
test("reports an unavailable venue service", async () => {
  data.listVenues.mockRejectedValue(new Error("down"));

  await openPage({ venue: "v1" });

  expect(screen.getByRole("alert").textContent).toContain("The venue service is unavailable.");
  expect(screen.queryByRole("form", { name: "Block a venue" })).toBeNull();
  expect(screen.queryByRole("table")).toBeNull();
});

// AC4-N2 (negative): a venue id that is not in the catalogue is reported as not found
test("reports a venue that is not in the catalogue", async () => {
  await openPage({ venue: "missing" });

  expect(screen.getByRole("heading", { name: "Venue not found" })).toBeDefined();
  expect(data.listVenueBlocks).not.toHaveBeenCalled();
  expect(screen.queryByRole("form", { name: "Block a venue" })).toBeNull();
});

// AC4-N2 (negative): a venue removed after the catalogue loaded is reported as not found
test("reports a venue whose blocks lookup returns not found", async () => {
  data.listVenueBlocks.mockResolvedValue(null);

  await openPage({ venue: "v1" });

  expect(screen.getByRole("heading", { name: "Venue not found" })).toBeDefined();
  expect(screen.queryByRole("table")).toBeNull();
});

// AC4-N3 (negative): a failed blocks lookup never shows an all-available calendar
test("never shows an open calendar when blocks could not be loaded", async () => {
  data.listVenueBlocks.mockRejectedValue(new Error("down"));

  await openPage({ venue: "v1" });

  expect(screen.getByRole("alert").textContent).toContain("Blocks for this venue could not be loaded.");
  expect(screen.queryByRole("table")).toBeNull();
  expect(screen.queryByText("Available")).toBeNull();
});

// AC4-P5 (partition): an empty catalogue is stated plainly
test("explains when the catalogue has no venues", async () => {
  data.listVenues.mockResolvedValue([]);

  await openPage();

  expect(screen.getByText("No venues in the catalogue yet.")).toBeDefined();
  expect(data.listVenueBlocks).not.toHaveBeenCalled();
  expect(screen.queryByRole("form", { name: "Block a venue" })).toBeNull();
});

// AC3-H4 (happy): the calendar shows the selected venue's approved bookings as booked
test("shows approved bookings for the selected venue as booked", async () => {
  data.listApprovedBookings.mockResolvedValue([
    { id: "r1", venue_id: "v1", event_name: "Open day", start_date: "2026-10-22", end_date: "2026-10-22", slots: ["PM"], status: "approved" },
    { id: "r2", venue_id: "v2", event_name: "Other venue", start_date: "2026-10-22", end_date: "2026-10-22", slots: ["AM"], status: "approved" },
  ]);

  await openPage({ venue: "v1" });

  const row = within(screen.getByRole("table")).getByRole("row", { name: /Thu 22 Oct/ });
  expect(within(row).getByText("Booked")).toBeDefined();
  expect(within(row).getByText("Booked — Open day")).toBeDefined();
  expect(within(row).getAllByText("Available")).toHaveLength(1);
  expect(screen.queryByText("Booked — Other venue")).toBeNull();
});

// AC3-N1 (negative): a failed booking lookup never shows an all-available calendar
test("never shows an open calendar when bookings could not be loaded", async () => {
  data.listApprovedBookings.mockRejectedValue(new Error("down"));

  await openPage({ venue: "v1" });

  expect(screen.getByRole("alert").textContent).toContain("Bookings for this venue could not be loaded.");
  expect(screen.queryByRole("table")).toBeNull();
});

// AC3-H6 (happy): after saving a block, Venue Staff see which confirmed bookings it affects
test("lists the confirmed bookings a new block affects", async () => {
  // "Affected" means the booking has not ended, so fix today's date.
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-10-08T02:00:00Z"));
  onTestFinished(() => {
    vi.useRealTimers();
  });
  data.listApprovedBookings.mockResolvedValue([
    { id: "r1", venue_id: "v1", event_name: "Open day", start_date: "2026-10-21", end_date: "2026-10-22", slots: ["AM"], status: "approved" },
    { id: "r2", venue_id: "v1", event_name: "Evening talk", start_date: "2026-10-20", end_date: "2026-10-20", slots: ["NIGHT"], status: "approved" },
    { id: "r3", venue_id: "v2", event_name: "Elsewhere", start_date: "2026-10-20", end_date: "2026-10-20", slots: ["AM"], status: "approved" },
  ]);

  await openPage({ venue: "v1", created: "1", block: "b1" });

  expect(screen.getByRole("status").textContent).toBe(
    "Block saved. It affects 1 confirmed booking: Open day (21 Oct 2026 – 22 Oct 2026). Its Coordinator has been notified.",
  );
});

// AC3-P7 (partition): a block that affects no booking just confirms the save
test("confirms a block that affects no booking", async () => {
  await openPage({ venue: "v1", created: "1", block: "b1" });

  expect(screen.getByRole("status").textContent).toBe("Block saved.");
});
