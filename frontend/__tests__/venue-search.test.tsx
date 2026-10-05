import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";

import { VenueResults } from "@/app/venues/search/venue-results";
import { buildVenueSearch } from "@/lib/venue-form";
import type { Venue } from "@/lib/venues";

afterEach(cleanup);

// Purpose: SCRUM-9 AC1 — every filter is sent, lists as repeated parameters.
test("builds a query from every filter", () => {
  const { query, errors } = buildVenueSearch({
    required_capacity: "80",
    location: " East ",
    date: "2026-11-14",
    slot: "PM",
    layout: "theatre",
    facility: "Projector, WiFi",
    accessibility: "Ramp access",
  });

  expect(errors).toEqual({});
  expect(new URLSearchParams(query!).getAll("facility")).toEqual(["Projector", "WiFi"]);
  expect(Object.fromEntries(new URLSearchParams(query!))).toMatchObject({
    required_capacity: "80", location: "East", date: "2026-11-14", slot: "PM", layout: "theatre", accessibility: "Ramp access",
  });
});

// Purpose: An untouched form does not search.
test("returns no query when nothing is filled in", () => {
  expect(buildVenueSearch({})).toEqual({ query: null, errors: {} });
});

// Purpose: Review focus 4 — a non-positive or non-integer capacity is reported, not sent.
test.each(["0", "abc", "2.5", "-1"])("rejects capacity %j", (value) => {
  expect(buildVenueSearch({ required_capacity: value })).toEqual({
    query: null,
    errors: { required_capacity: "Enter a whole number greater than zero." },
  });
});

// Purpose: Values outside the backend enums are dropped instead of causing a 422.
test("drops unknown slot and layout values", () => {
  expect(buildVenueSearch({ slot: "MIDNIGHT", layout: "ballroom", location: "East" }).query).toBe("location=East");
});

// Purpose: A date that matches YYYY-MM-DD but isn't a real calendar date
// (e.g. February 30) is dropped instead of causing a 422 from the venue service.
test("drops a date that is not a real calendar date", () => {
  expect(buildVenueSearch({ date: "2026-02-30", location: "East" }).query).toBe("location=East");
});

const venue: Venue = {
  id: "v1", name: "Riverside Hall", location: "East Wing", max_capacity: 120,
  facilities: ["Projector"], accessibility_features: ["Ramp access"], supported_layouts: ["theatre"],
  operating_slots: ["AM", "PM"], status: "available", created_at: "2026-09-13T03:00:00Z", updated_at: "2026-09-13T03:00:00Z",
};

// Purpose: SCRUM-9 AC2 — each result shows the attributes a coordinator shortlists by.
test("shows key attributes for each result", () => {
  render(<VenueResults venues={[venue]} />);

  // Scoped to the attribute list: the card's check form also offers "Theatre" as an option.
  const attributes = screen.getByRole("article", { name: "Riverside Hall" }).querySelector("dl") as HTMLElement;
  for (const text of ["East Wing", "120", "Theatre", "Projector", "Ramp access", "AM, PM"]) {
    expect(within(attributes).getByText(new RegExp(text))).toBeDefined();
  }
  expect(screen.getByText("1 venue matches every filter.")).toBeDefined();
});

// Purpose: No matches is stated plainly so the coordinator can loosen filters.
test("explains when no venue matches", () => {
  render(<VenueResults venues={[]} />);

  expect(screen.getByText("No venue matches every filter. Try removing one.")).toBeDefined();
});
