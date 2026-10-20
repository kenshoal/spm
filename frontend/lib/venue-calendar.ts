import { getJson } from "./api";
import type { Slot } from "./venue-options";
import { venueApiUrl } from "./venues";

// One month of slot states for a venue (SCRUM-31). The API returns states only:
// never block reasons, event names or ids.
export type CalendarState = "open" | "booked" | "blocked" | "unavailable" | "not_offered";

export interface CalendarSlot {
  slot: Slot;
  state: CalendarState;
}

export interface CalendarDay {
  date: string;
  slots: CalendarSlot[];
}

export interface VenueCalendar {
  venue_id: string;
  month: string;
  days: CalendarDay[];
}

// Written out, so a state never depends on colour alone.
export const STATE_LABELS: Record<CalendarState, string> = {
  open: "Available",
  booked: "Booked",
  blocked: "Blocked",
  unavailable: "Unavailable",
  not_offered: "Not offered",
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
