import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

vi.mock("@/app/venues/actions", () => ({ createVenue: vi.fn(), updateVenue: vi.fn() }));

import { VenueForm } from "@/app/venues/venue-form";
import { updateVenue } from "@/app/venues/actions";
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
  setup_minutes: 30,
  turnaround_minutes: 45,
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
  // SCRUM-65: operating slots are retired; every venue runs 07:00-24:00.
  expect(screen.queryByRole("checkbox", { name: "NIGHT" })).toBeNull();
  expect(screen.getByText("Every venue is bookable from 07:00 to 24:00 in 15-minute steps.")).toBeDefined();
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

// Purpose: Review finding 2 — an echoed invalid capacity must never fall back to the
// venue's stored value. This drives useActionState with a real form submission
// (fireEvent.click on the "Save changes" button, matching the pattern already used
// for server-action forms in __tests__/coordination.test.tsx) rather than a pure
// helper, because the bug is specifically about what ends up in the rendered
// defaultValue after a resolved action — a pure function can't observe that.
// Uses "-3" rather than "abc": a number input sanitizes non-numeric text to "" in
// the DOM regardless of which value set it, so only a syntactically-numeric-but-
// invalid string can distinguish "echoed the typed text" from "fell back to venue".
test("an invalid capacity echoed after a failed edit submission overrides the stored value", async () => {
  vi.mocked(updateVenue).mockResolvedValue({
    message: "Check the highlighted fields.",
    errors: { max_capacity: "Enter a whole number greater than zero." },
    values: {
      name: venue.name,
      location: venue.location,
      max_capacity: "-3",
      facilities: venue.facilities.join(", "),
      accessibility_features: venue.accessibility_features.join(", "),
      supported_layouts: venue.supported_layouts,
      setup_minutes: String(venue.setup_minutes),
      turnaround_minutes: String(venue.turnaround_minutes),
      status: venue.status,
    },
  });

  render(<VenueForm venue={venue} />);
  fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

  await waitFor(() =>
    expect(screen.getByText("Enter a whole number greater than zero.")).toBeDefined(),
  );
  // Not an exact-string getByLabelText: the field's error message renders inside
  // its <label>, so once it's showing, the label's accessible name is "Maximum
  // capacityEnter a whole number greater than zero." — matched with a substring.
  expect((screen.getByLabelText(/Maximum capacity/) as HTMLInputElement).value).toBe("-3");
});

// AC1-H5 (happy): SCRUM-59 the new venue form asks for setup and turnaround minutes, starting at 0
test("new venue form offers setup and turnaround minutes in steps of 15", () => {
  render(<VenueForm />);

  for (const label of ["Setup time (minutes)", "Turnaround time (minutes)"]) {
    const input = screen.getByLabelText(label) as HTMLInputElement;
    expect(input.type).toBe("number");
    expect(input.step).toBe("15");
    expect(input.min).toBe("0");
    expect(input.max).toBe("1020");
    expect(input.value).toBe("0");
  }
});

// AC1-H6 (happy): SCRUM-59 editing starts from the venue's current setup and turnaround minutes
test("edit form is prefilled with the setup and turnaround minutes", () => {
  render(<VenueForm venue={venue} />);

  expect((screen.getByLabelText("Setup time (minutes)") as HTMLInputElement).value).toBe("30");
  expect((screen.getByLabelText("Turnaround time (minutes)") as HTMLInputElement).value).toBe("45");
});
