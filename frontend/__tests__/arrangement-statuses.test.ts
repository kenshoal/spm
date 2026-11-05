import { describe, expect, test } from "vitest";

import { EQUIPMENT_RECORDING_STATUSES, VENUE_REQUEST_STATUSES } from "@/lib/arrangement-statuses";

// All 13 event statuses, so a status added later has to be placed in or out of each rule on purpose.
const ALL_STATUSES = [
  "Draft", "Submitted", "Under Review", "Changes Requested", "Approved", "Planning", "Safety Review",
  "Confirmed", "Completed", "Cancelled", "Rejected", "Withdrawn", "Postponed",
] as const;
const ALLOWED = ["Approved", "Planning", "Safety Review"];

describe.each([
  ["venue booking panel", "SCRUM-32 AC7", VENUE_REQUEST_STATUSES],
  ["equipment requirements panel", "SCRUM-33 AC6", EQUIPMENT_RECORDING_STATUSES],
] as const)("%s (%s)", (_panel, _ac, statuses) => {
  // AC7-P1 to AC7-P3 (partition): Approved, Planning and Safety Review offer the form
  test.each(ALLOWED)("%s offers it", (status) => {
    expect(statuses.has(status)).toBe(true);
  });

  // AC7-N1 to AC7-N10 (negative): every other status does not
  test.each(ALL_STATUSES.filter((status) => !ALLOWED.includes(status)))("%s does not", (status) => {
    expect(statuses.has(status)).toBe(false);
  });
});
