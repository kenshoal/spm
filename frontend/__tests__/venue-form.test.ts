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
};

// SCRUM-30 AC1-P2 (partition): comma lists are trimmed, blank-free and de-duplicated
// Purpose: Review focus 5 — comma lists are trimmed, blank-free and de-duplicated.
test("splitList trims, drops blanks and de-duplicates case-insensitively", () => {
  expect(splitList("Projector, , projector ,WiFi")).toEqual(["Projector", "WiFi"]);
  expect(splitList("   ")).toEqual([]);
});

// SCRUM-30 AC1-H4 (happy): every catalogue attribute is captured from the form
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
    layout_capacities: {},
    setup_minutes: 0,
    turnaround_minutes: 0,
    operating_start_minute: 420,
    operating_end_minute: 1440,
  });
});

// SCRUM-30 AC1-N4 (negative): a non-positive or non-integer capacity is reported, not sent
// Purpose: Review focus 4 — capacity must be a whole number above zero.
test.each(["abc", "0", "-3", "12.5", ""])("rejects capacity %j", (capacity) => {
  const { errors } = parseVenueForm(venueForm({ ...valid, max_capacity: capacity }), { includeStatus: false });

  expect(errors.max_capacity).toBe("Enter a whole number greater than zero.");
});

// SCRUM-30 AC1-N5 (negative): missing name and location are reported instead of sent
// Purpose: A venue needs a name and a location (operating slots retired by SCRUM-65:
// every venue runs 07:00-24:00).
test("reports missing required fields", () => {
  const { errors } = parseVenueForm(venueForm({ max_capacity: "10" }), { includeStatus: false });

  expect(errors).toEqual({
    name: "Enter the venue name.",
    location: "Enter the venue location.",
  });
});

// SCRUM-30 AC1-P3 (partition): values outside the backend enums are dropped, not sent
// Purpose: Values outside the backend enums are dropped rather than sent; operating
// slots are no longer sent at all (SCRUM-65).
test("ignores unknown layouts, slots and statuses", () => {
  const { payload } = parseVenueForm(
    venueForm({ ...valid, supported_layouts: ["theatre", "ballroom"], operating_slots: ["AM", "MIDNIGHT"], status: "gone" }),
    { includeStatus: true },
  );

  expect(payload.supported_layouts).toEqual(["theatre"]);
  expect("operating_slots" in payload).toBe(false);
  expect(payload.status).toBe("available");
});

// SCRUM-30 AC1-P4 (partition): the status field is sent only when editing
// Purpose: Editing can take a venue out of service; creating cannot set status.
test("includes status only when editing", () => {
  expect(parseVenueForm(venueForm({ ...valid, status: "blocked" }), { includeStatus: true }).payload.status).toBe("blocked");
  expect("status" in parseVenueForm(venueForm({ ...valid, status: "blocked" }), { includeStatus: false }).payload).toBe(false);
});

// SCRUM-30 AC1-N7 (negative): an invalid capacity is echoed verbatim so a correction never loses it
// Purpose: Review finding 2 — an invalid capacity must echo back verbatim, not the
// null parseVenueForm produces for it, so a corrected resubmission never loses it.
test("readVenueFormValues keeps an invalid capacity and the raw comma text untouched", () => {
  const values = readVenueFormValues(venueForm({ ...valid, max_capacity: "abc" }));

  expect(values.max_capacity).toBe("abc");
  expect(values.facilities).toBe("Projector, WiFi");
  expect(values.supported_layouts).toEqual(["theatre", "classroom"]);
});

// SCRUM-30 AC1-P5 (partition): no status is echoed when the create form omits the field
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


// SCRUM-30 H12 AC1-H6 (happy): the opening and closing times are sent as minutes after midnight
test("parses the operating hours", () => {
  const { payload, errors } = parseVenueForm(
    venueForm({ ...valid, operating_start_minute: "540", operating_end_minute: "1080" }),
    { includeStatus: false },
  );

  expect(errors).toEqual({});
  expect(payload.operating_start_minute).toBe(540);
  expect(payload.operating_end_minute).toBe(1080);
});

// SCRUM-30 H12 AC1-P6 (partition): blank hours mean the whole day, 07:00 to 24:00
test("blank operating hours mean the whole day", () => {
  const { payload } = parseVenueForm(venueForm(valid), { includeStatus: false });

  expect([payload.operating_start_minute, payload.operating_end_minute]).toEqual([420, 1440]);
});

// SCRUM-30 H12 AC1-B4, AC1-B5 (boundary): the first and last quarter hours of the day are valid on their own
test.each([["420", "435"], ["1425", "1440"]])("accepts %s to %s", (start, end) => {
  const { errors } = parseVenueForm(
    venueForm({ ...valid, operating_start_minute: start, operating_end_minute: end }),
    { includeStatus: false },
  );

  expect(errors).toEqual({});
});

// SCRUM-30 H12 AC6-N1 to AC6-N7 (negative): an invalid range is reported, not sent
test.each([
  ["405", "1080"], ["540", "1455"], ["545", "1080"], ["540", "1085"], ["600", "600"], ["900", "600"], ["abc", "1080"],
])("rejects operating hours %s to %s", (start, end) => {
  const { errors } = parseVenueForm(
    venueForm({ ...valid, operating_start_minute: start, operating_end_minute: end }),
    { includeStatus: false },
  );

  expect(errors.operating_hours).toMatch(/opening time before the closing time/i);
});

// SCRUM-30 H12 AC6-X1 (cross-cutting): the raw hours are echoed back untouched after a refusal
test("readVenueFormValues echoes the hours as typed", () => {
  const values = readVenueFormValues(venueForm({ ...valid, operating_start_minute: "900", operating_end_minute: "600" }));

  expect([values.operating_start_minute, values.operating_end_minute]).toEqual(["900", "600"]);
});
