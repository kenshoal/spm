import { getJson } from "./api";
import type { RoomLayout, Slot, VenueStatus } from "./venue-options";

export { ROOM_LAYOUTS, SLOTS, layoutLabel, prepTimeLabel } from "./venue-options";
export type { RoomLayout, Slot, VenueStatus } from "./venue-options";

export interface Venue {
  id: string;
  name: string;
  location: string;
  max_capacity: number;
  facilities: string[];
  accessibility_features: string[];
  supported_layouts: RoomLayout[];
  layout_capacities?: Partial<Record<RoomLayout, number>>;
  operating_slots: Slot[];
  setup_minutes: number;
  turnaround_minutes: number;
  status: VenueStatus;
  created_at: string;
  updated_at: string;
}

// A search match; tentatively_held marks a venue free at the searched time except
// for tentative holds (SCRUM-18).
export interface VenueSearchResult extends Venue {
  tentatively_held?: boolean;
}

export const venueApiUrl = process.env.VENUE_API_URL ?? "http://127.0.0.1:8004";

export async function listVenues(): Promise<Venue[]> {
  return (await getJson<Venue[]>(venueApiUrl, "/venues")) ?? [];
}

export async function getVenue(id: string): Promise<Venue | null> {
  return getJson<Venue>(venueApiUrl, `/venues/${encodeURIComponent(id)}`);
}

export async function searchVenues(query: string): Promise<VenueSearchResult[]> {
  return (await getJson<VenueSearchResult[]>(venueApiUrl, `/venues/search?${query}`)) ?? [];
}
