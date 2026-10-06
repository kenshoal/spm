import { expect, test } from "vitest";

import { buildBlockCalendar, currentMonth, parseMonth, type BlockCalendar } from "@/lib/block-calendar";
import type { VenueBlock } from "@/lib/venue-block-options";

const venue = { id: "v1", operating_slots: ["AM", "PM"] as const };

function block(overrides: Partial<VenueBlock> = {}): VenueBlock {
  return {
    id: "b1",
    venue_id: "v1",
    start_date: "2026-10-20",
    end_date: "2026-10-21",
    slots: ["AM", "PM"],
    reason_category: "maintenance",
    reason_detail: "Air-con repairs",
    status: "active",
    created_by: "staff-1",
    created_at: "2026-10-01T02:00:00Z",
    ...overrides,
  };
}

function cell(calendar: BlockCalendar, date: string, slot: string) {
  const day = calendar.days.find((d) => d.date === date);
  if (!day) throw new Error(`${date} is not in ${calendar.month}`);
  const found = day.cells.find((c) => c.slot === slot);
  if (!found) throw new Error(`${slot} missing on ${date}`);
  return found;
}

// AC4-H1 (happy): every covered date and slot is blocked with its reason, and nothing else is
test("marks covered cells blocked with the reason", () => {
  const calendar = buildBlockCalendar({ ...venue, operating_slots: [...venue.operating_slots] }, [block()], "2026-10");

  expect(calendar.month).toBe("2026-10");
  expect(calendar.label).toBe("October 2026");
  expect(calendar.days).toHaveLength(31);
  for (const date of ["2026-10-20", "2026-10-21"]) {
    for (const slot of ["AM", "PM"]) {
      expect(cell(calendar, date, slot)).toEqual({ slot, state: "blocked", reasons: ["Maintenance — Air-con repairs"] });
    }
  }
  const blockedCount = calendar.days.flatMap((d) => d.cells).filter((c) => c.state === "blocked").length;
  expect(blockedCount).toBe(4);
});

// AC4-B1 (boundary): the first and last days are blocked, the days either side are open
test("blocks both boundary dates and leaves the neighbouring days open", () => {
  const calendar = buildBlockCalendar({ ...venue, operating_slots: ["AM", "PM"] }, [block()], "2026-10");

  expect(cell(calendar, "2026-10-19", "AM").state).toBe("open");
  expect(cell(calendar, "2026-10-20", "AM").state).toBe("blocked");
  expect(cell(calendar, "2026-10-21", "AM").state).toBe("blocked");
  expect(cell(calendar, "2026-10-22", "AM").state).toBe("open");
});

// AC4-B2 (boundary): a block spanning two months shows in each month only on its own days
test("shows a month-spanning block in both months", () => {
  const spanning = [block({ start_date: "2026-10-30", end_date: "2026-11-02", slots: ["AM"] })];
  const october = buildBlockCalendar({ ...venue, operating_slots: ["AM", "PM"] }, spanning, "2026-10");
  const november = buildBlockCalendar({ ...venue, operating_slots: ["AM", "PM"] }, spanning, "2026-11");

  expect(cell(october, "2026-10-29", "AM").state).toBe("open");
  expect(cell(october, "2026-10-30", "AM").state).toBe("blocked");
  expect(cell(october, "2026-10-31", "AM").state).toBe("blocked");
  expect(november.days).toHaveLength(30);
  expect(cell(november, "2026-11-01", "AM").state).toBe("blocked");
  expect(cell(november, "2026-11-02", "AM").state).toBe("blocked");
  expect(cell(november, "2026-11-03", "AM").state).toBe("open");
});

// AC4-B3 (boundary): month navigation crosses year boundaries in both directions
test("links to the previous and next months across a year boundary", () => {
  const december = buildBlockCalendar({ ...venue, operating_slots: ["AM"] }, [], "2026-12");
  const january = buildBlockCalendar({ ...venue, operating_slots: ["AM"] }, [], "2027-01");

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
  const calendar = buildBlockCalendar({ ...venue, operating_slots: ["AM", "PM"] }, [block({ status: "lifted" })], "2026-10");

  expect(cell(calendar, "2026-10-20", "AM").state).toBe("open");
  expect(cell(calendar, "2026-10-20", "AM").reasons).toEqual([]);
});

// AC4-P2 (partition): non-operating slots are not offered unless an active block covers them
test("shows non-operating slots as not offered, unless blocked", () => {
  const plain = buildBlockCalendar({ ...venue, operating_slots: ["AM", "PM"] }, [], "2026-10");
  expect(cell(plain, "2026-10-20", "NIGHT")).toEqual({ slot: "NIGHT", state: "not_offered", reasons: [] });

  const nightBlock = [block({ slots: ["NIGHT"], reason_category: "safety", reason_detail: null })];
  const blocked = buildBlockCalendar({ ...venue, operating_slots: ["AM", "PM"] }, nightBlock, "2026-10");
  expect(cell(blocked, "2026-10-20", "NIGHT")).toEqual({ slot: "NIGHT", state: "blocked", reasons: ["Safety"] });
});

// AC4-P3 (partition): overlapping blocks list every reason on the shared cell
test("lists every reason when blocks overlap", () => {
  const calendar = buildBlockCalendar(
    { ...venue, operating_slots: ["AM", "PM"] },
    [block(), block({ id: "b2", start_date: "2026-10-21", end_date: "2026-10-21", slots: ["AM"], reason_category: "internal_use", reason_detail: "Staff training" })],
    "2026-10",
  );

  expect(cell(calendar, "2026-10-21", "AM").reasons).toEqual(["Maintenance — Air-con repairs", "Internal use — Staff training"]);
  expect(cell(calendar, "2026-10-21", "PM").reasons).toEqual(["Maintenance — Air-con repairs"]);
});

// AC4-P6 (partition): a venue blocked in the catalogue is unavailable on every operating slot,
// while its dated blocks keep their reasons and non-operating slots stay not offered
test("shows a catalogue-blocked venue as unavailable on every date", () => {
  const calendar = buildBlockCalendar({ ...venue, operating_slots: ["AM", "PM"], status: "blocked" }, [block()], "2026-10");

  expect(cell(calendar, "2026-10-01", "AM")).toEqual({ slot: "AM", state: "unavailable", reasons: [] });
  expect(cell(calendar, "2026-10-31", "PM").state).toBe("unavailable");
  expect(cell(calendar, "2026-10-20", "AM")).toEqual({ slot: "AM", state: "blocked", reasons: ["Maintenance — Air-con repairs"] });
  expect(cell(calendar, "2026-10-01", "NIGHT").state).toBe("not_offered");
  const open = calendar.days.flatMap((d) => d.cells).filter((c) => c.state === "open");
  expect(open).toEqual([]);
});

// AC4-P6 (partition): an available venue is unaffected by the catalogue rule
test("keeps an available venue's free slots open", () => {
  const calendar = buildBlockCalendar({ ...venue, operating_slots: ["AM", "PM"], status: "available" }, [], "2026-10");

  expect(cell(calendar, "2026-10-01", "AM").state).toBe("open");
});

// AC4-P4 (partition): another venue's block never marks this venue's calendar
test("ignores blocks that belong to another venue", () => {
  const calendar = buildBlockCalendar({ ...venue, operating_slots: ["AM", "PM"] }, [block({ venue_id: "v2" })], "2026-10");

  expect(cell(calendar, "2026-10-20", "AM").state).toBe("open");
});
