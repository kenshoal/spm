import { getJson } from "./api";
import { venueApiUrl } from "./venues";

// One month of times for a venue (SCRUM-31, on times by SCRUM-69). Each date is a
// partition of 07:00-24:00 into booked, blocked and free ranges, in minutes after
// midnight. The API returns times only: never block reasons, event names or ids.
// SCRUM-18 adds tentative holds; a block wins over a booking and a booking over a hold.
export type CalendarEntryState = "booked" | "blocked" | "held";

export interface CalendarEntry {
  state: CalendarEntryState;
  start_minute: number;
  end_minute: number;
}

export interface CalendarRange {
  start_minute: number;
  end_minute: number;
}

export interface CalendarDay {
  date: string;
  // The venue is blocked as a whole in the catalogue.
  unavailable: boolean;
  entries: CalendarEntry[];
  free: CalendarRange[];
}

export interface VenueCalendar {
  venue_id: string;
  month: string;
  days: CalendarDay[];
}

// Written out, so a state never depends on colour alone.
export const ENTRY_LABELS: Record<CalendarEntryState, string> = {
  booked: "Booked",
  blocked: "Blocked",
  held: "Tentatively held",
};

export function monthLabel(month: string): string {
  const [year, number] = month.split("-").map(Number);
  return new Date(Date.UTC(year, number - 1, 1)).toLocaleDateString("en-GB", { month: "long", year: "numeric", timeZone: "UTC" });
}

const MONTH_PATTERN = /^(\d{4})-(0[1-9]|1[0-2])$/;
const pad = (value: number, width: number) => String(value).padStart(width, "0");

// A month the API accepts: YYYY-MM with a real year (0000 is not a calendar
// year). Anything else falls back, so the page never asks for a month the API
// refuses and then reports it as a missing venue.
export function parseCalendarMonth(value: string | undefined, fallback: string): string {
  const match = value ? MONTH_PATTERN.exec(value) : null;
  return match && Number(match[1]) >= 1 ? (value as string) : fallback;
}

// The month of a searched date (YYYY-MM-DD), or null when it is not a real month.
export function monthOfDate(value: string): string | null {
  const match = /^(\d{4}-\d{2})-\d{2}$/.exec(value);
  return match ? parseCalendarMonth(match[1], "") || null : null;
}

// Plain integer arithmetic: Date treats years 0 to 99 as 1900s and writes year
// 10000 with a plus sign. There is no month before 0001-01 or after 9999-12.
export function adjacentMonths(month: string): { previous: string | null; next: string | null } {
  const [year, number] = month.split("-").map(Number);
  return {
    previous: number > 1 ? `${pad(year, 4)}-${pad(number - 1, 2)}` : year > 1 ? `${pad(year - 1, 4)}-12` : null,
    next: number < 12 ? `${pad(year, 4)}-${pad(number + 1, 2)}` : year < 9999 ? `${pad(year + 1, 4)}-01` : null,
  };
}

// A missing venue (the API answers 404) is null; any other failure throws, so
// the page shows an error and never an all-available calendar.
export async function getVenueCalendar(venueId: string, month: string): Promise<VenueCalendar | null> {
  return getJson<VenueCalendar>(venueApiUrl, `/venues/${encodeURIComponent(venueId)}/calendar?month=${encodeURIComponent(month)}`);
}
