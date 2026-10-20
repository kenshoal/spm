// Client-safe venue constants and types: no import of ./api, ./auth or
// anything else that touches next/headers. lib/venues.ts re-exports these so
// its public surface is unchanged, but a "use client" component (like
// app/venues/venue-form.tsx) can import the runtime values straight from
// here without dragging server-only code into the browser bundle.
export const ROOM_LAYOUTS = ["classroom", "theatre", "boardroom", "banquet", "exhibition"] as const;
export const SLOTS = ["AM", "PM", "NIGHT"] as const;
export type RoomLayout = (typeof ROOM_LAYOUTS)[number];
export type Slot = (typeof SLOTS)[number];
export type VenueStatus = "available" | "blocked";

export function layoutLabel(layout: RoomLayout): string {
  return layout.charAt(0).toUpperCase() + layout.slice(1);
}

// SCRUM-59: setup and turnaround times are minutes in 15-minute steps
// (discussion #131), up to the 1020-minute 07:00-24:00 window. 0 means none.
export const PREP_MINUTES_STEP = 15;
export const MAX_PREP_MINUTES = 1020;

export function prepTimeLabel(minutes: number): string {
  return minutes > 0 ? `${minutes} min` : "None";
}

// SCRUM-65: venues are booked and blocked by start and end time, in
// minutes after midnight on 15-minute steps within 07:00-24:00 (discussion
// #131). The API carries minutes; screens show HH:MM, with 24:00 for midnight.
export const OPEN_MINUTE = 420;
export const CLOSE_MINUTE = 1440;
export const TIME_STEP = 15;
const steps = (from: number, to: number) =>
  Array.from({ length: (to - from) / TIME_STEP + 1 }, (_, i) => from + i * TIME_STEP);
export const START_TIMES = steps(OPEN_MINUTE, CLOSE_MINUTE - TIME_STEP);
export const END_TIMES = steps(OPEN_MINUTE + TIME_STEP, CLOSE_MINUTE);

export function timeLabel(minutes: number): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(Math.floor(minutes / 60))}:${pad(minutes % 60)}`;
}

export function timeRangeLabel(start: number, end: number): string {
  return `${timeLabel(start)}–${timeLabel(end)}`;
}

function parseTime(value: string): number | null {
  const match = /^(\d{2}):(\d{2})$/.exec(value);
  if (!match) return null;
  const minutes = Number(match[1]) * 60 + Number(match[2]);
  return Number(match[2]) < 60 && minutes <= CLOSE_MINUTE ? minutes : null;
}

// Parses "HH:MM" start and end times with the API's rules and messages.
export function timeRangeFrom(startText: string, endText: string): {
  start_minute: number;
  end_minute: number;
  errors: Record<string, string>;
} {
  const start = parseTime(startText);
  const end = parseTime(endText);
  const errors: Record<string, string> = {};
  if (start === null) errors.start_time = "Choose a start time.";
  if (end === null) errors.end_time = "Choose an end time.";
  if (start !== null && end !== null) {
    if (start % TIME_STEP || end % TIME_STEP) errors.start_time = "Times must be on a 15-minute step.";
    else if (start < OPEN_MINUTE || end > CLOSE_MINUTE) errors.start_time = "Times must fall between 07:00 and 24:00.";
    else if (end <= start) errors.end_time = "The end must be after the start.";
  }
  return { start_minute: start ?? 0, end_minute: end ?? 0, errors };
}

// Reads the start_time / end_time fields of a form.
export function readTimeRange(formData: FormData) {
  return timeRangeFrom(String(formData.get("start_time") ?? ""), String(formData.get("end_time") ?? ""));
}
