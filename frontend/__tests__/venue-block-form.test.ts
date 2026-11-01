import { expect, test } from "vitest";

import { parseBlockForm, readBlockFormValues } from "@/lib/venue-block-form";

function form(fields: {
  venue_id?: string;
  start_date?: string;
  end_date?: string;
  start_time?: string;
  end_time?: string;
  reason_category?: string;
  reason_detail?: string;
}): FormData {
  const data = new FormData();
  for (const key of ["venue_id", "start_date", "end_date", "start_time", "end_time", "reason_category", "reason_detail"] as const) {
    if (fields[key] !== undefined) data.set(key, fields[key]);
  }
  return data;
}

const valid = {
  venue_id: "v1",
  start_date: "2026-10-20",
  end_date: "2026-10-21",
  // SCRUM-65: times replace the AM and PM slots.
  start_time: "07:00",
  end_time: "18:00",
  reason_category: "maintenance",
  reason_detail: " Air-con repairs ",
};

// AC1-H1 (happy): a complete block parses to the payload venueService expects
test("parses a complete block into the API payload", () => {
  expect(parseBlockForm(form(valid))).toEqual({
    venueId: "v1",
    payload: {
      start_date: "2026-10-20",
      end_date: "2026-10-21",
      start_minute: 420,
      end_minute: 1080,
      reason_category: "maintenance",
      reason_detail: "Air-con repairs",
    },
    errors: {},
  });
});

// AC1-P1 (partition): every reason category is accepted and sent unchanged
test.each([
  ["AC1-P1", "maintenance"],
  ["AC1-P2", "renovation"],
  ["AC1-P3", "safety"],
  ["AC1-P4", "internal_use"],
  ["AC1-P4b", "equipment_failure"],
  ["AC1-P4c", "other"],
])("%s accepts reason %s", (_id, reason) => {
  const { payload, errors } = parseBlockForm(form({ ...valid, reason_category: reason }));

  expect(errors).toEqual({});
  expect(payload.reason_category).toBe(reason);
});

// AC1-P5 (partition): a short time and the whole day are accepted as minutes (SCRUM-65)
test("accepts a single slot and all slots in canonical order", () => {
  const short = parseBlockForm(form({ ...valid, start_time: "12:00", end_time: "12:15" }));
  expect([short.payload.start_minute, short.payload.end_minute]).toEqual([720, 735]);

  const all = parseBlockForm(form({ ...valid, start_time: "07:00", end_time: "24:00" }));
  expect(all.errors).toEqual({});
  expect([all.payload.start_minute, all.payload.end_minute]).toEqual([420, 1440]);
});

// AC1-B1 (boundary): a one-day block (end date equals start date) is accepted
test("accepts an end date equal to the start date", () => {
  expect(parseBlockForm(form({ ...valid, end_date: "2026-10-20" })).errors).toEqual({});
});

// AC1-B2 (boundary): an end date one day before the start date is refused
test("refuses an end date one day before the start date", () => {
  expect(parseBlockForm(form({ ...valid, end_date: "2026-10-19" })).errors).toEqual({
    end_date: "The end date must be on or after the start date.",
  });
});

// AC1-B3 (boundary): detail of 1000 characters is accepted and 1001 is refused
test("accepts 1000 characters of detail and refuses 1001", () => {
  const atLimit = parseBlockForm(form({ ...valid, reason_detail: "x".repeat(1000) }));
  expect(atLimit.errors).toEqual({});
  expect(atLimit.payload.reason_detail).toHaveLength(1000);

  expect(parseBlockForm(form({ ...valid, reason_detail: "x".repeat(1001) })).errors).toEqual({
    reason_detail: "Keep the detail to 1000 characters or fewer.",
  });
});

// AC1-B3 (boundary): blank detail is omitted rather than sent as an empty string
test("omits blank detail from the payload", () => {
  const { payload, errors } = parseBlockForm(form({ ...valid, reason_detail: "   " }));

  expect(errors).toEqual({});
  expect(payload).not.toHaveProperty("reason_detail");
});

// AC1-N1 (negative): a block without times, or with the end not after the start, is refused (SCRUM-65)
test("refuses a block with no slot", () => {
  expect(parseBlockForm(form({ ...valid, start_time: "", end_time: "" })).errors).toEqual({
    start_time: "Choose a start time.",
    end_time: "Choose an end time.",
  });
  expect(parseBlockForm(form({ ...valid, start_time: "18:00", end_time: "07:00" })).errors).toEqual({
    end_time: "The end must be after the start.",
  });
});

// AC1-N2 (negative): a missing or unknown reason is refused
test.each(["", "holiday"])("refuses reason %j", (reason) => {
  expect(parseBlockForm(form({ ...valid, reason_category: reason })).errors).toEqual({
    reason_category: "Choose a reason.",
  });
});

// AC1-N3 (negative): missing and impossible calendar dates are refused
test("refuses missing and impossible dates", () => {
  expect(parseBlockForm(form({ ...valid, start_date: "", end_date: "2026-02-30" })).errors).toEqual({
    start_date: "Enter a valid start date.",
    end_date: "Enter a valid end date.",
  });
});

// AC1-N4 (negative): a block without a venue is refused
test("refuses a block with no venue", () => {
  expect(parseBlockForm(form({ ...valid, venue_id: " " })).errors).toEqual({
    venue_id: "Choose a venue.",
  });
});

// AC1-N1 (negative): raw values are echoed exactly as typed so a failed submission keeps the input
test("reads the raw form values for echoing back", () => {
  expect(readBlockFormValues(form({ ...valid, start_time: "12:00", end_time: "11:00" }))).toEqual({
    venue_id: "v1",
    start_date: "2026-10-20",
    end_date: "2026-10-21",
    start_time: "12:00",
    end_time: "11:00",
    reason_category: "maintenance",
    reason_detail: " Air-con repairs ",
  });
});
