import { expect, test } from "vitest";
import { parseEquipmentForm, parseQuantity } from "@/lib/equipment-form";
import { statusLabel } from "@/lib/equipment";

function form(fields: Record<string, string>): FormData {
  const data = new FormData();
  for (const [key, value] of Object.entries(fields)) data.set(key, value);
  return data;
}

// Purpose: SCRUM-45 AC1 — every catalogue attribute is captured.
test("parses a complete equipment record", () => {
  const { payload, errors } = parseEquipmentForm(form({
    type: "Wireless microphone", description: "  Handheld  ", total_owned_quantity: "12",
    home_location: "Store B", operational_status: "UNDER_MAINTENANCE",
  }));

  expect(errors).toEqual({});
  expect(payload).toEqual({
    type: "Wireless microphone", description: "Handheld", total_owned_quantity: 12,
    home_location: "Store B", operational_status: "UNDER_MAINTENANCE",
  });
});

// Purpose: Review focus 4 — quantity is a whole number, zero allowed (all retired).
test("accepts zero and rejects non-whole quantities", () => {
  expect(parseQuantity("0")).toBe(0);
  for (const bad of ["", "abc", "-1", "2.5"]) expect(parseQuantity(bad)).toBeNull();
});

// Purpose: Type and home location are required; blank description is stored as null.
test("reports missing fields and defaults the status", () => {
  const { payload, errors } = parseEquipmentForm(form({ total_owned_quantity: "x", operational_status: "LOST" }));

  expect(errors).toEqual({
    type: "Enter the equipment type.",
    home_location: "Enter the home location.",
    total_owned_quantity: "Enter a whole number of zero or more.",
  });
  expect(payload.description).toBeNull();
  expect(payload.operational_status).toBe("AVAILABLE");
});

// Purpose: Statuses read as words, not enum constants.
test("labels every operational status", () => {
  expect(statusLabel("UNDER_REPAIR")).toBe("Under repair");
  expect(statusLabel("AVAILABLE")).toBe("Available");
});
