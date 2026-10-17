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
