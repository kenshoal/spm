import { expect, test } from "vitest";

import { bookingsAffectedBy, buildBlockCalendar, currentMonth, parseMonth, type BlockCalendar } from "@/lib/block-calendar";
import type { VenueBlock } from "@/lib/venue-block-options";
import type { VenueBooking } from "@/lib/venue-booking-options";

// SCRUM-65: the calendar lists blocked and booked times per date instead of
// AM / PM / NIGHT cells. Case IDs are those of SCRUM-23 and SCRUM-15.
const venue = { id: "v1" };

function block(overrides: Partial<VenueBlock> = {}): VenueBlock {
  return {
    id: "b1",
    venue_id: "v1",
    start_date: "2026-10-20",
    end_date: "2026-10-21",
    start_minute: 420,
    end_minute: 1080,
    slots: ["AM", "PM"],
    reason_category: "maintenance",
    reason_detail: "Air-con repairs",
    status: "active",
    created_by: "staff-1",
    created_at: "2026-10-01T02:00:00Z",
    ...overrides,
  };
}

function booking(overrides: Partial<VenueBooking> = {}): VenueBooking {
  return {
    id: "r1",
    venue_id: "v1",
    event_name: "Open day",
    start_date: "2026-10-20",
    end_date: "2026-10-21",
    start_minute: 420,
    end_minute: 720,
    slots: ["AM"],
    status: "approved",
    ...overrides,
  };
}

function day(calendar: BlockCalendar, date: string) {
  const found = calendar.days.find((d) => d.date === date);
  if (!found) throw new Error(`${date} is not in ${calendar.month}`);
  return found;
}

const texts = (calendar: BlockCalendar, date: string) => day(calendar, date).entries.map((e) => `${e.time} ${e.state} ${e.text}`);

// AC4-H1 (happy): every covered date lists the blocked time with its reason, and nothing else does
test("marks covered cells blocked with the reason", () => {
  const calendar = buildBlockCalendar(venue, [block()], "2026-10");

  expect(calendar.month).toBe("2026-10");
  expect(calendar.label).toBe("October 2026");
  expect(calendar.days).toHaveLength(31);
  for (const date of ["2026-10-20", "2026-10-21"]) {
    expect(texts(calendar, date)).toEqual(["07:00–18:00 blocked Maintenance — Air-con repairs"]);
  }
  expect(calendar.days.filter((d) => d.entries.length > 0)).toHaveLength(2);
});

// AC4-B1 (boundary): the first and last days are blocked, the days either side are open
test("blocks both boundary dates and leaves the neighbouring days open", () => {
  const calendar = buildBlockCalendar(venue, [block()], "2026-10");

  expect(day(calendar, "2026-10-19").entries).toEqual([]);
  expect(day(calendar, "2026-10-20").entries).toHaveLength(1);
  expect(day(calendar, "2026-10-21").entries).toHaveLength(1);
  expect(day(calendar, "2026-10-22").entries).toEqual([]);
});

// AC4-B2 (boundary): a block spanning two months shows in each month only on its own days
test("shows a month-spanning block in both months", () => {
  const spanning = [block({ start_date: "2026-10-30", end_date: "2026-11-02" })];
  const october = buildBlockCalendar(venue, spanning, "2026-10");
  const november = buildBlockCalendar(venue, spanning, "2026-11");

  expect(day(october, "2026-10-29").entries).toEqual([]);
  expect(day(october, "2026-10-30").entries).toHaveLength(1);
  expect(day(october, "2026-10-31").entries).toHaveLength(1);
  expect(november.days).toHaveLength(30);
  expect(day(november, "2026-11-02").entries).toHaveLength(1);
  expect(day(november, "2026-11-03").entries).toEqual([]);
});

// AC4-B3 (boundary): month navigation crosses year boundaries in both directions
test("links to the previous and next months across a year boundary", () => {
  const december = buildBlockCalendar(venue, [], "2026-12");
  const january = buildBlockCalendar(venue, [], "2027-01");

  expect(december.nextMonth).toBe("2027-01");
  expect(december.previousMonth).toBe("2026-11");
  expect(january.previousMonth).toBe("2026-12");
  expect(january.label).toBe("January 2027");
});

// AC4-B3 (boundary): only a real YYYY-MM month is accepted; anything else falls back
test.each([
  ["2026-10", "2026-10"],
  ["2026-12", "2026-12"],
  ["2026-13", "2026-01"],
  ["2026-00", "2026-01"],
  ["abc", "2026-01"],
  [undefined, "2026-01"],
])("parses month %j as %j", (value, expected) => {
  expect(parseMonth(value, "2026-01")).toBe(expected);
});

// AC4-B3 (boundary): the default month follows Singapore time, not UTC
test("uses the Singapore calendar month by default", () => {
  // 31 Oct 2026 17:30 UTC is already 1 Nov 2026 in Singapore (UTC+8).
  expect(currentMonth(new Date("2026-10-31T17:30:00Z"))).toBe("2026-11");
});

// AC4-P1 (partition): a lifted block is never shown as blocked
test("ignores lifted blocks", () => {
  expect(day(buildBlockCalendar(venue, [block({ status: "lifted" })], "2026-10"), "2026-10-20").entries).toEqual([]);
});

// AC4-P2 (partition): a block shows its own time, whatever the hour (no "not offered" in the fixed 07:00-24:00 window)
test("shows non-operating slots as not offered, unless blocked", () => {
  const night = [block({ start_minute: 1080, end_minute: 1440, reason_category: "safety", reason_detail: null })];

  expect(texts(buildBlockCalendar(venue, night, "2026-10"), "2026-10-20")).toEqual(["18:00–24:00 blocked Safety"]);
});

// AC4-P3 (partition): overlapping blocks are each listed, earliest first
test("lists every reason when blocks overlap", () => {
  const calendar = buildBlockCalendar(
    venue,
    [block(), block({ id: "b2", start_date: "2026-10-21", end_date: "2026-10-21", start_minute: 420, end_minute: 600, reason_category: "internal_use", reason_detail: "Staff training" })],
    "2026-10",
  );

  expect(texts(calendar, "2026-10-21")).toEqual([
    "07:00–10:00 blocked Internal use — Staff training",
    "07:00–18:00 blocked Maintenance — Air-con repairs",
  ]);
  expect(texts(calendar, "2026-10-20")).toEqual(["07:00–18:00 blocked Maintenance — Air-con repairs"]);
});

// AC4-P6 (partition): a venue blocked in the catalogue is unavailable on every date
test("shows a catalogue-blocked venue as unavailable on every date", () => {
  const calendar = buildBlockCalendar({ ...venue, status: "blocked" }, [block()], "2026-10");

  expect(calendar.days.every((d) => d.unavailable)).toBe(true);
  expect(day(calendar, "2026-10-20").entries).toHaveLength(1);
});

// AC4-P6 (partition): an available venue is unaffected by the catalogue rule
test("keeps an available venue's free slots open", () => {
  const calendar = buildBlockCalendar({ ...venue, status: "available" }, [], "2026-10");

  expect(day(calendar, "2026-10-01")).toEqual({ date: "2026-10-01", unavailable: false, entries: [] });
});

// AC4-P4 (partition): another venue's block never marks this venue's calendar
test("ignores blocks that belong to another venue", () => {
  expect(day(buildBlockCalendar(venue, [block({ venue_id: "v2" })], "2026-10"), "2026-10-20").entries).toEqual([]);
});

// AC3-H3 (happy): an approved booking shows as booked with its event and time on every covered date
test("marks approved bookings as booked with the event name", () => {
  const calendar = buildBlockCalendar(venue, [], "2026-10", [booking()]);

  expect(texts(calendar, "2026-10-20")).toEqual(["07:00–12:00 booked Open day"]);
  expect(texts(calendar, "2026-10-21")).toEqual(["07:00–12:00 booked Open day"]);
  expect(day(calendar, "2026-10-22").entries).toEqual([]);
});

// AC3-P4 (partition): pending or rejected requests and other venues' bookings are not shown as booked
test("ignores unapproved requests and other venues", () => {
  const calendar = buildBlockCalendar(venue, [], "2026-10", [
    booking({ status: "pending" }),
    booking({ id: "r2", status: "rejected" }),
    booking({ id: "r3", venue_id: "v2" }),
  ]);

  expect(day(calendar, "2026-10-20").entries).toEqual([]);
});

// AC3-P5 (partition): a block over a booking lists both, earliest first
test("shows a block over a booking as blocked with both reasons", () => {
  const calendar = buildBlockCalendar(venue, [block({ start_minute: 600 })], "2026-10", [booking({ event_name: null })]);

  expect(texts(calendar, "2026-10-20")).toEqual([
    "07:00–12:00 booked event",
    "10:00–18:00 blocked Maintenance — Air-con repairs",
  ]);
});

// SCRUM-65 AC3-X1 (cross-cutting): only bookings that overlap a new block in time are affected
test("finds the bookings a block overlaps in time", () => {
  const affected = bookingsAffectedBy(block({ start_minute: 720, end_minute: 840 }), [
    booking({ id: "hit", start_minute: 780, end_minute: 900 }),
    booking({ id: "adjacent", start_minute: 420, end_minute: 720 }),
  ], "2026-10-01");

  expect(affected.map((b) => b.id)).toEqual(["hit"]);
});
