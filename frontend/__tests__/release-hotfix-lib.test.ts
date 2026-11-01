import { expect, test } from "vitest";
import { isFull, isRegistrationOpen } from "@/lib/attendee";
import { singaporeInstant, singaporeLocalValue } from "@/lib/singapore-time";
import { singaporeDate } from "@/lib/equipment-requests";
import { parseVenueForm } from "@/lib/venue-form";

// AC4-P3 (partition, hotfix 4): a datetime-local value is read as Singapore time
test("reads a local value as Singapore time and rejects other shapes", () => {
  expect(singaporeInstant("2026-12-01T09:00")).toBe("2026-12-01T09:00:00+08:00");
  expect(singaporeInstant("2026-12-01")).toBeNull();
  expect(singaporeInstant("")).toBeNull();
});

// AC4-P4 (partition, hotfix 4): a stored instant shows in Singapore time, across midnight
test("shows an instant in Singapore time", () => {
  expect(singaporeLocalValue("2026-12-01T01:00:00Z")).toBe("2026-12-01T09:00");
  expect(singaporeLocalValue("2026-12-01T17:00:00Z")).toBe("2026-12-02T01:00");
  expect(singaporeLocalValue(null)).toBe("");
  expect(singaporeDate("2026-12-01T17:00:00Z")).toBe("2026-12-02");
});

const window_ = { registration_opens_at: "2026-12-01T00:00:00Z", registration_closes_at: "2026-12-05T00:00:00Z" };

// AC5-B1, AC5-B2, AC5-B3 (boundary, hotfix 5): open from the start, closed at exactly the end
test.each([
  ["just before it opens", Date.parse("2026-11-30T23:59:59Z"), false],
  ["exactly when it opens", Date.parse("2026-12-01T00:00:00Z"), true],
  ["exactly when it closes", Date.parse("2026-12-05T00:00:00Z"), false],
])("registration window %s", (_name, at, open) => {
  expect(isRegistrationOpen(window_, at)).toBe(open);
});

// AC5-P1 (partition, hotfix 5): an event with no window set is never open
test("no window means not open", () => {
  expect(isRegistrationOpen({ registration_opens_at: null, registration_closes_at: null }, 0)).toBe(false);
});

// AC5-B4, AC5-B5 (boundary, hotfix 5): full at zero places, not at one; unlimited is never full
test("an event is full only when no place is left", () => {
  expect(isFull({ places_remaining: 0 })).toBe(true);
  expect(isFull({ places_remaining: 1 })).toBe(false);
  expect(isFull({ places_remaining: null })).toBe(false);
});

function venueForm(fields: Record<string, string>): FormData {
  const data = new FormData();
  data.set("name", "Hall");
  data.set("location", "Marina");
  data.set("max_capacity", "200");
  for (const [key, value] of Object.entries(fields)) data.set(key, value);
  return data;
}

// AC12-P3 (partition, hotfix 12): filled layout capacities are sent, blanks are left out
test("keeps only the layout capacities that were filled in", () => {
  const { payload, errors } = parseVenueForm(
    venueForm({ layout_capacity_theatre: "150", layout_capacity_classroom: "" }),
    { includeStatus: false },
  );

  expect(payload.layout_capacities).toEqual({ theatre: 150 });
  expect(errors.layout_capacities).toBeUndefined();
});

// AC12-N2 (negative, hotfix 12): zero or text is a field error, never silently dropped
test.each(["0", "-5", "abc"])("layout capacity %s is refused", (value) => {
  const { errors } = parseVenueForm(venueForm({ layout_capacity_theatre: value }), { includeStatus: false });

  expect(errors.layout_capacities).toBe("Enter a whole number greater than zero, or leave it blank.");
});
