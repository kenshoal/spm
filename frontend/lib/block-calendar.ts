// Pure month-calendar model for SCRUM-23 AC4. Dates are plain YYYY-MM-DD
// strings compared lexically, so no time zone can shift a block by a day.
import { blockReasonText, type VenueBlock } from "./venue-block-options";
import { SLOTS, type Slot } from "./venue-options";

// "unavailable": the venue is blocked as a whole in the catalogue (status "blocked").
export type CellState = "blocked" | "open" | "unavailable" | "not_offered";

export interface CalendarCell {
  slot: Slot;
  state: CellState;
  reasons: string[];
}

export interface CalendarDay {
  date: string;
  cells: CalendarCell[];
}

export interface BlockCalendar {
  month: string;
  label: string;
  previousMonth: string;
  nextMonth: string;
  days: CalendarDay[];
}

const MONTH_PATTERN = /^(\d{4})-(0[1-9]|1[0-2])$/;

export function parseMonth(value: string | undefined, fallback: string): string {
  return value && MONTH_PATTERN.test(value) ? value : fallback;
}

// The venues are in Singapore, so "this month" follows Singapore time.
export function currentMonth(now: Date = new Date()): string {
  return now.toLocaleDateString("en-CA", { timeZone: "Asia/Singapore" }).slice(0, 7);
}

function shiftMonth(month: string, delta: number): string {
  const [year, monthNumber] = month.split("-").map(Number);
  const shifted = new Date(Date.UTC(year, monthNumber - 1 + delta, 1));
  return shifted.toISOString().slice(0, 7);
}

export function buildBlockCalendar(
  venue: { id: string; operating_slots: readonly Slot[]; status?: "available" | "blocked" },
  blocks: readonly VenueBlock[],
  month: string,
): BlockCalendar {
  const [year, monthNumber] = month.split("-").map(Number);
  const dayCount = new Date(Date.UTC(year, monthNumber, 0)).getUTCDate();
  const active = blocks.filter((block) => block.status === "active" && block.venue_id === venue.id);

  const days: CalendarDay[] = [];
  for (let day = 1; day <= dayCount; day += 1) {
    const date = `${month}-${String(day).padStart(2, "0")}`;
    const cells = SLOTS.map((slot): CalendarCell => {
      const reasons = active
        .filter((block) => block.start_date <= date && date <= block.end_date && block.slots.includes(slot))
        .map(blockReasonText);
      // An active block always shows, even on a slot the venue does not operate.
      if (reasons.length) return { slot, state: "blocked", reasons };
      if (!venue.operating_slots.includes(slot)) return { slot, state: "not_offered", reasons: [] };
      return { slot, state: venue.status === "blocked" ? "unavailable" : "open", reasons: [] };
    });
    days.push({ date, cells });
  }

  return {
    month,
    label: new Date(Date.UTC(year, monthNumber - 1, 1)).toLocaleDateString("en-GB", { month: "long", year: "numeric", timeZone: "UTC" }),
    previousMonth: shiftMonth(month, -1),
    nextMonth: shiftMonth(month, 1),
    days,
  };
}
