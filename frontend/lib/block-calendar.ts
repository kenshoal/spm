// Pure month-calendar model for SCRUM-23 AC4. Dates are plain YYYY-MM-DD
// strings compared lexically, so no time zone can shift a block by a day.
import { blockReasonText, type VenueBlock } from "./venue-block-options";
import type { VenueBooking } from "./venue-booking-options";
import { CLOSE_MINUTE, OPEN_MINUTE, timeRangeLabel } from "./venue-options";

// SCRUM-65: each date lists the times that are blocked or booked (an approved
// booking request, SCRUM-15), earliest first; any other time in 07:00-24:00
// is open. "unavailable": the venue is blocked as a whole in the catalogue.
export interface CalendarEntry {
  state: "blocked" | "booked";
  start_minute: number;
  end_minute: number;
  time: string;
  text: string;
}

export interface CalendarDay {
  date: string;
  unavailable: boolean;
  entries: CalendarEntry[];
  // Some time in 07:00-24:00 is neither blocked nor booked.
  free: boolean;
}

// entries are sorted by start time.
function hasFreeTime(entries: readonly CalendarEntry[]): boolean {
  let reached = OPEN_MINUTE;
  for (const entry of entries) {
    if (entry.start_minute > reached) return true;
    reached = Math.max(reached, entry.end_minute);
  }
  return reached < CLOSE_MINUTE;
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

// The venues are in Singapore, so "today" and "this month" follow Singapore time.
export function currentDate(now: Date = new Date()): string {
  return now.toLocaleDateString("en-CA", { timeZone: "Asia/Singapore" });
}

export function currentMonth(now: Date = new Date()): string {
  return currentDate(now).slice(0, 7);
}

// Approved bookings for the block's venue that share a date with it, overlap
// it in time and have not ended: the ones whose Coordinators venueService
// notifies.
export function bookingsAffectedBy(block: VenueBlock, bookings: readonly VenueBooking[], today: string): VenueBooking[] {
  return bookings.filter(
    (booking) =>
      booking.status === "approved" &&
      booking.venue_id === block.venue_id &&
      booking.end_date >= today &&
      booking.start_date <= block.end_date &&
      block.start_date <= booking.end_date &&
      booking.start_minute < block.end_minute &&
      block.start_minute < booking.end_minute,
  );
}

function shiftMonth(month: string, delta: number): string {
  const [year, monthNumber] = month.split("-").map(Number);
  const shifted = new Date(Date.UTC(year, monthNumber - 1 + delta, 1));
  return shifted.toISOString().slice(0, 7);
}

export function buildBlockCalendar(
  venue: { id: string; status?: "available" | "blocked" },
  blocks: readonly VenueBlock[],
  month: string,
  bookings: readonly VenueBooking[] = [],
): BlockCalendar {
  const [year, monthNumber] = month.split("-").map(Number);
  const dayCount = new Date(Date.UTC(year, monthNumber, 0)).getUTCDate();
  const active = blocks.filter((block) => block.status === "active" && block.venue_id === venue.id);
  const approved = bookings.filter((booking) => booking.status === "approved" && booking.venue_id === venue.id);
  const entry = (state: CalendarEntry["state"], item: { start_minute: number; end_minute: number }, text: string): CalendarEntry => ({
    state,
    start_minute: item.start_minute,
    end_minute: item.end_minute,
    time: timeRangeLabel(item.start_minute, item.end_minute),
    text,
  });

  const days: CalendarDay[] = [];
  for (let day = 1; day <= dayCount; day += 1) {
    const date = `${month}-${String(day).padStart(2, "0")}`;
    const on = (item: { start_date: string; end_date: string }) => item.start_date <= date && date <= item.end_date;
    const entries = [
      ...active.filter(on).map((block) => entry("blocked", block, blockReasonText(block))),
      ...approved.filter(on).map((booking) => entry("booked", booking, booking.event_name ?? "event")),
    ].sort((a, b) => a.start_minute - b.start_minute || a.end_minute - b.end_minute);
    days.push({ date, unavailable: venue.status === "blocked", entries, free: hasFreeTime(entries) });
  }

  return {
    month,
    label: new Date(Date.UTC(year, monthNumber - 1, 1)).toLocaleDateString("en-GB", { month: "long", year: "numeric", timeZone: "UTC" }),
    previousMonth: shiftMonth(month, -1),
    nextMonth: shiftMonth(month, 1),
    days,
  };
}
