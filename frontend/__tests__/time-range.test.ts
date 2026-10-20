import { expect, test } from "vitest";

import { END_TIMES, START_TIMES, readTimeRange, timeLabel, timeRangeLabel } from "@/lib/venue-options";

function form(start?: string, end?: string): FormData {
  const data = new FormData();
  if (start !== undefined) data.set("start_time", start);
  if (end !== undefined) data.set("end_time", end);
  return data;
}

// SCRUM-65 AC6-H1 (happy): minutes after midnight show as HH:MM, 24:00 included
test("labels times and ranges", () => {
  expect(timeLabel(420)).toBe("07:00");
  expect(timeLabel(1440)).toBe("24:00");
  expect(timeRangeLabel(600, 735)).toBe("10:00–12:15");
});

// SCRUM-65 AC6-B1 (boundary): the choices are 15-minute steps inside 07:00-24:00
test("offers start times 07:00-23:45 and end times 07:15-24:00", () => {
  expect(START_TIMES[0]).toBe(420);
  expect(START_TIMES.at(-1)).toBe(1425);
  expect(END_TIMES[0]).toBe(435);
  expect(END_TIMES.at(-1)).toBe(1440);
  expect(START_TIMES.every((m) => m % 15 === 0)).toBe(true);
});

// SCRUM-65 AC6-H2 (happy): a chosen range parses to the minutes the API takes
test("reads a valid range", () => {
  expect(readTimeRange(form("10:00", "12:15"))).toEqual({ start_minute: 600, end_minute: 735, errors: {} });
  expect(readTimeRange(form("23:45", "24:00")).errors).toEqual({});
});

// SCRUM-65 AC6-N1 (negative): missing, off-step, outside or reversed times are refused with the reason
test.each([
  [undefined, undefined, { start_time: "Choose a start time.", end_time: "Choose an end time." }],
  ["10:10", "12:00", { start_time: "Times must be on a 15-minute step." }],
  ["06:45", "08:00", { start_time: "Times must fall between 07:00 and 24:00." }],
  ["12:00", "12:00", { end_time: "The end must be after the start." }],
  ["13:00", "12:00", { end_time: "The end must be after the start." }],
])("refuses %s to %s", (start, end, errors) => {
  expect(readTimeRange(form(start, end)).errors).toEqual(errors);
});
