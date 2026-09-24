import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

vi.mock("@/app/venues/actions", () => ({ createVenue: vi.fn(), updateVenue: vi.fn() }));

import { VenueForm } from "@/app/venues/venue-form";
import type { Venue } from "@/lib/venues";

afterEach(cleanup);

const venue: Venue = {
  id: "venue-1",
  name: "Riverside Hall",
  location: "Level 2",
  max_capacity: 120,
  facilities: ["Projector", "WiFi"],
  accessibility_features: ["Ramp access"],
  supported_layouts: ["theatre"],
  operating_slots: ["AM", "PM"],
  status: "available",
  created_at: "2026-09-13T03:00:00Z",
  updated_at: "2026-09-14T03:00:00Z",
};

// Purpose: SCRUM-30 AC1 — a new venue form asks for every catalogue attribute.
test("new venue form offers every attribute and no status", () => {
  render(<VenueForm />);

  for (const label of ["Venue name", "Location", "Maximum capacity", "Facilities", "Accessibility features"]) {
    expect(screen.getByLabelText(label)).toBeDefined();
  }
  expect(screen.getByRole("checkbox", { name: "Theatre" })).toBeDefined();
  expect(screen.getByRole("checkbox", { name: "NIGHT" })).toBeDefined();
  expect(screen.queryByLabelText("Availability")).toBeNull();
  expect(screen.getByRole("button", { name: "Add venue" })).toBeDefined();
});

// Purpose: SCRUM-30 AC2 — editing starts from the venue's current attributes.
test("edit form is prefilled with the current attributes", () => {
  render(<VenueForm venue={venue} />);

  expect((screen.getByLabelText("Venue name") as HTMLInputElement).value).toBe("Riverside Hall");
  expect((screen.getByLabelText("Facilities") as HTMLInputElement).value).toBe("Projector, WiFi");
  expect((screen.getByRole("checkbox", { name: "Theatre" }) as HTMLInputElement).checked).toBe(true);
  expect((screen.getByRole("checkbox", { name: "Classroom" }) as HTMLInputElement).checked).toBe(false);
  expect((screen.getByLabelText("Availability") as HTMLSelectElement).value).toBe("available");
  expect(screen.getByRole("button", { name: "Save changes" })).toBeDefined();
});
