import { expect, test } from "vitest";

import { CHANGE_FIELD_LABELS } from "@/lib/change-decision";

// SCRUM-35 AC1-P3 (partition): every value an Organiser can propose has a label for the Coordinator's decision
test.each([
  "proposed_date_times",
  "expected_attendance",
  "venue_requirements",
  "equipment_requirements",
  "registration_needs",
  "accessibility_needs",
])("%s has a label", (field) => {
  expect(CHANGE_FIELD_LABELS[field]).toBeTruthy();
});
