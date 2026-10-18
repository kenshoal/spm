import { expect, test } from "vitest";
import { parseVenueForm, readVenueFormValues, splitList } from "@/lib/venue-form";

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
    setup_minutes: 0,
    turnaround_minutes: 0,
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

// Purpose: Review finding 2 — an invalid capacity must echo back verbatim, not the
// null parseVenueForm produces for it, so a corrected resubmission never loses it.
test("readVenueFormValues keeps an invalid capacity and the raw comma text untouched", () => {
  const values = readVenueFormValues(venueForm({ ...valid, max_capacity: "abc" }));

  expect(values.max_capacity).toBe("abc");
  expect(values.facilities).toBe("Projector, WiFi");
  expect(values.supported_layouts).toEqual(["theatre", "classroom"]);
  expect(values.operating_slots).toEqual(["AM", "PM"]);
});

// Purpose: The create form never submits a status field, so nothing should echo one.
test("readVenueFormValues omits status when the field is absent", () => {
  expect("status" in readVenueFormValues(venueForm(valid))).toBe(false);
  expect(readVenueFormValues(venueForm({ ...valid, status: "blocked" })).status).toBe("blocked");
});

// AC1-H4 (happy): SCRUM-59 setup and turnaround minutes are sent as numbers
test("parses setup and turnaround minutes", () => {
  const { payload, errors } = parseVenueForm(
    venueForm({ ...valid, setup_minutes: "30", turnaround_minutes: "45" }),
    { includeStatus: false },
  );

  expect(errors).toEqual({});
  expect(payload.setup_minutes).toBe(30);
  expect(payload.turnaround_minutes).toBe(45);
});

// AC1-P2 (partition): SCRUM-59 a blank time means none and is sent as 0
test("treats blank setup and turnaround minutes as 0", () => {
  const { payload, errors } = parseVenueForm(
    venueForm({ ...valid, setup_minutes: " ", turnaround_minutes: "" }),
    { includeStatus: false },
  );

  expect(errors).toEqual({});
  expect(payload.setup_minutes).toBe(0);
  expect(payload.turnaround_minutes).toBe(0);
});

// AC1-B2 (boundary): SCRUM-59 0, 15, 1005 and 1020 are accepted
test.each(["0", "15", "1005", "1020"])("accepts %s minutes", (minutes) => {
  const { payload, errors } = parseVenueForm(
    venueForm({ ...valid, setup_minutes: minutes, turnaround_minutes: minutes }),
    { includeStatus: false },
  );

  expect(errors).toEqual({});
  expect(payload.setup_minutes).toBe(Number(minutes));
  expect(payload.turnaround_minutes).toBe(Number(minutes));
});

// AC1-N3 (negative, boundary): SCRUM-59 off-step, negative, too large and non-numeric times are reported
test.each(["-15", "14", "20", "1021", "1035", "12.5", "abc"])("rejects %j minutes", (minutes) => {
  const { errors } = parseVenueForm(
    venueForm({ ...valid, setup_minutes: minutes, turnaround_minutes: minutes }),
    { includeStatus: false },
  );

  expect(errors.setup_minutes).toBe("Enter minutes in steps of 15, from 0 to 1020.");
  expect(errors.turnaround_minutes).toBe("Enter minutes in steps of 15, from 0 to 1020.");
});

// AC1-N4 (negative): SCRUM-59 an invalid time is echoed back exactly as typed
test("readVenueFormValues keeps the typed setup and turnaround text", () => {
  const values = readVenueFormValues(venueForm({ ...valid, setup_minutes: "20", turnaround_minutes: "45" }));

  expect(values.setup_minutes).toBe("20");
  expect(values.turnaround_minutes).toBe("45");
});
