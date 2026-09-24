import { getJson } from "./api";

export const ROOM_LAYOUTS = ["classroom", "theatre", "boardroom", "banquet", "exhibition"] as const;
export const SLOTS = ["AM", "PM", "NIGHT"] as const;
export type RoomLayout = (typeof ROOM_LAYOUTS)[number];
export type Slot = (typeof SLOTS)[number];
export type VenueStatus = "available" | "blocked";

export interface Venue {
  id: string;
  name: string;
  location: string;
  max_capacity: number;
  facilities: string[];
  accessibility_features: string[];
  supported_layouts: RoomLayout[];
  operating_slots: Slot[];
  status: VenueStatus;
  created_at: string;
  updated_at: string;
}

export const venueApiUrl = process.env.VENUE_API_URL ?? "http://127.0.0.1:8004";

export async function listVenues(): Promise<Venue[]> {
  return (await getJson<Venue[]>(venueApiUrl, "/venues")) ?? [];
}

export async function getVenue(id: string): Promise<Venue | null> {
  return getJson<Venue>(venueApiUrl, `/venues/${encodeURIComponent(id)}`);
}

export function layoutLabel(layout: RoomLayout): string {
  return layout.charAt(0).toUpperCase() + layout.slice(1);
}
