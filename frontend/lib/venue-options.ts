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
