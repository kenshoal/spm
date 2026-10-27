import { getJson } from "./api";
import { venueApiUrl } from "./venues";

// One month of times for a venue (SCRUM-31, on times by SCRUM-69). Each date is a
// partition of 07:00-24:00 into booked, blocked and free ranges, in minutes after
// midnight. The API returns times only: never block reasons, event names or ids.
export type CalendarEntryState = "booked" | "blocked";

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
};

export function monthLabel(month: string): string {
  const [year, number] = month.split("-").map(Number);
  return new Date(Date.UTC(year, number - 1, 1)).toLocaleDateString("en-GB", { month: "long", year: "numeric", timeZone: "UTC" });
}

export function adjacentMonths(month: string): { previous: string; next: string } {
  const [year, number] = month.split("-").map(Number);
  const shift = (delta: number) => new Date(Date.UTC(year, number - 1 + delta, 1)).toISOString().slice(0, 7);
  return { previous: shift(-1), next: shift(1) };
}

// A missing venue (the API answers 404) is null; any other failure throws, so
// the page shows an error and never an all-available calendar.
export async function getVenueCalendar(venueId: string, month: string): Promise<VenueCalendar | null> {
  return getJson<VenueCalendar>(venueApiUrl, `/venues/${encodeURIComponent(venueId)}/calendar?month=${encodeURIComponent(month)}`);
}
