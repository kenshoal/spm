import { expect, test } from "vitest";
import { parseVenueForm, splitList } from "@/lib/venue-form";

function venueForm(fields: Record<string, string | string[]>): FormData {
  const data = new FormData();
  for (const [key, value] of Object.entries(fields)) {
    for (const item of Array.isArray(value) ? value : [value]) data.append(key, item);
  }
  return data;
}

const valid = {
  name: "Riverside Hall",
  location: "Level 2, East Wing",
  max_capacity: "120",
  facilities: "Projector, WiFi",
  accessibility_features: "Ramp access",
  supported_layouts: ["theatre", "classroom"],
  operating_slots: ["AM", "PM"],
};

// Purpose: Review focus 5 — comma lists are trimmed, blank-free and de-duplicated.
test("splitList trims, drops blanks and de-duplicates case-insensitively", () => {
  expect(splitList("Projector, , projector ,WiFi")).toEqual(["Projector", "WiFi"]);
  expect(splitList("   ")).toEqual([]);
});

// Purpose: SCRUM-30 AC1 — every catalogue attribute is captured from the form.
test("parses a complete venue", () => {
  const { payload, errors } = parseVenueForm(venueForm(valid), { includeStatus: false });

  expect(errors).toEqual({});
  expect(payload).toEqual({
    name: "Riverside Hall",
    location: "Level 2, East Wing",
    max_capacity: 120,
    facilities: ["Projector", "WiFi"],
    accessibility_features: ["Ramp access"],
    supported_layouts: ["theatre", "classroom"],
    operating_slots: ["AM", "PM"],
  });
});

// Purpose: Review focus 4 — capacity must be a whole number above zero.
test.each(["abc", "0", "-3", "12.5", ""])("rejects capacity %j", (capacity) => {
  const { errors } = parseVenueForm(venueForm({ ...valid, max_capacity: capacity }), { includeStatus: false });

  expect(errors.max_capacity).toBe("Enter a whole number greater than zero.");
});

// Purpose: A venue needs a name, a location and at least one bookable slot.
test("reports missing required fields", () => {
  const { errors } = parseVenueForm(venueForm({ max_capacity: "10" }), { includeStatus: false });

  expect(errors).toMatchObject({
    name: "Enter the venue name.",
    location: "Enter the venue location.",
    operating_slots: "Choose at least one operating slot.",
  });
});

// Purpose: Values outside the backend enums are dropped rather than sent.
test("ignores unknown layouts, slots and statuses", () => {
  const { payload } = parseVenueForm(
    venueForm({ ...valid, supported_layouts: ["theatre", "ballroom"], operating_slots: ["AM", "MIDNIGHT"], status: "gone" }),
    { includeStatus: true },
  );

  expect(payload.supported_layouts).toEqual(["theatre"]);
  expect(payload.operating_slots).toEqual(["AM"]);
  expect(payload.status).toBe("available");
});

// Purpose: Editing can take a venue out of service; creating cannot set status.
test("includes status only when editing", () => {
  expect(parseVenueForm(venueForm({ ...valid, status: "blocked" }), { includeStatus: true }).payload.status).toBe("blocked");
  expect("status" in parseVenueForm(venueForm({ ...valid, status: "blocked" }), { includeStatus: false }).payload).toBe(false);
});
