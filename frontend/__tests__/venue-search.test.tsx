import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";

import { VenueResults } from "@/app/venues/search/venue-results";
import { buildVenueSearch } from "@/lib/venue-form";
import type { Venue } from "@/lib/venues";

afterEach(cleanup);

// SCRUM-9 AC1-H1 (happy): every filter is sent to the search, lists as repeated parameters
// Purpose: SCRUM-9 AC1 — every filter is sent, lists as repeated parameters.
test("builds a query from every filter", () => {
  const { query, errors } = buildVenueSearch({
    required_capacity: "80",
    location: " East ",
    date: "2026-11-14",
    // SCRUM-65: a time range replaces the slot.
    start_time: "12:00",
    end_time: "18:00",
    layout: "theatre",
    facility: "Projector, WiFi",
    accessibility: "Ramp access",
  });

  expect(errors).toEqual({});
  expect(new URLSearchParams(query!).getAll("facility")).toEqual(["Projector", "WiFi"]);
  expect(Object.fromEntries(new URLSearchParams(query!))).toMatchObject({
    required_capacity: "80", location: "East", date: "2026-11-14", start_minute: "720", end_minute: "1080", layout: "theatre", accessibility: "Ramp access",
  });
});

// Purpose: An untouched form does not search.
// SCRUM-9 AC1-P1 (partition): an untouched form sends no query
test("returns no query when nothing is filled in", () => {
  expect(buildVenueSearch({})).toEqual({ query: null, errors: {} });
});

// Purpose: Review focus 4 — a non-positive or non-integer capacity is reported, not sent.
// SCRUM-9 AC1-N1 (negative): a non-positive or non-integer capacity is reported, not sent
test.each(["0", "abc", "2.5", "-1"])("rejects capacity %j", (value) => {
  expect(buildVenueSearch({ required_capacity: value })).toEqual({
    query: null,
    errors: { required_capacity: "Enter a whole number greater than zero." },
  });
});

// Purpose: Values outside the backend enums are dropped instead of causing a 422.
// SCRUM-9 AC1-P7 (partition): a layout outside the enum is dropped instead of causing a 422
test("drops unknown slot and layout values", () => {
  expect(buildVenueSearch({ layout: "ballroom", location: "East" }).query).toBe("location=East");
});

// SCRUM-65 AC4-N3 (negative): an invalid time range, or times without a date, are reported, not sent
test.each([
  [{ date: "2026-11-14", start_time: "12:10", end_time: "13:00" }, { start_time: "Times must be on a 15-minute step." }],
  [{ date: "2026-11-14", start_time: "13:00", end_time: "12:00" }, { end_time: "The end must be after the start." }],
  [{ date: "2026-11-14", start_time: "12:00" }, { end_time: "Choose an end time." }],
  [{ start_time: "12:00", end_time: "13:00" }, { date: "Choose a date to search by time." }],
])("refuses search times %j", (input, errors) => {
  expect(buildVenueSearch(input)).toEqual({ query: null, errors });
});

// Purpose: A date that matches YYYY-MM-DD but isn't a real calendar date
// (e.g. February 30) is dropped instead of causing a 422 from the venue service.
// SCRUM-9 AC1-N2 (negative): a date that is not a real calendar day is dropped, not sent
test("drops a date that is not a real calendar date", () => {
  expect(buildVenueSearch({ date: "2026-02-30", location: "East" }).query).toBe("location=East");
});

const venue: Venue = {
  id: "v1", name: "Riverside Hall", location: "East Wing", max_capacity: 120,
  facilities: ["Projector"], accessibility_features: ["Ramp access"], supported_layouts: ["theatre"],
  operating_slots: ["AM", "PM"], setup_minutes: 30, turnaround_minutes: 45,
  status: "available", created_at: "2026-09-13T03:00:00Z", updated_at: "2026-09-13T03:00:00Z",
};

// SCRUM-9 AC2-H2 (happy): each result shows the attributes a coordinator shortlists by
// Purpose: SCRUM-9 AC2 — each result shows the attributes a coordinator shortlists by.
test("shows key attributes for each result", () => {
  render(<VenueResults venues={[venue]} />);

  // Scoped to the attribute list: the card's check form also offers "Theatre" as an option.
  const attributes = screen.getByRole("article", { name: "Riverside Hall" }).querySelector("dl") as HTMLElement;
  for (const text of ["East Wing", "120", "Theatre", "Projector", "Ramp access"]) {
    expect(within(attributes).getByText(new RegExp(text))).toBeDefined();
  }
  expect(screen.getByText("1 venue matches every filter.")).toBeDefined();
});

// Purpose: No matches is stated plainly so the coordinator can loosen filters.
// SCRUM-9 AC2-N1 (negative): no match is stated plainly so the coordinator can loosen filters
test("explains when no venue matches", () => {
  render(<VenueResults venues={[]} />);

  expect(screen.getByText("No venue matches every filter. Try removing one.")).toBeDefined();
});

// AC2-H2 (happy): SCRUM-59 coordinators see each result's setup and turnaround time
test("shows setup and turnaround time for each result", () => {
  render(<VenueResults venues={[venue]} />);

  const attributes = screen.getByRole("article", { name: "Riverside Hall" }).querySelector("dl") as HTMLElement;
  expect(within(attributes).getByText("Setup").nextElementSibling?.textContent).toBe("30 min");
  expect(within(attributes).getByText("Turnaround").nextElementSibling?.textContent).toBe("45 min");
});

// AC4-H2 (happy): SCRUM-59 a time that was never set reads "None"
test("shows None when a venue has no setup or turnaround time", () => {
  render(<VenueResults venues={[{ ...venue, setup_minutes: 0, turnaround_minutes: 0 }]} />);

  const attributes = screen.getByRole("article", { name: "Riverside Hall" }).querySelector("dl") as HTMLElement;
  expect(within(attributes).getByText("Setup").nextElementSibling?.textContent).toBe("None");
  expect(within(attributes).getByText("Turnaround").nextElementSibling?.textContent).toBe("None");
});
