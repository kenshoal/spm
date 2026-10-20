// Client-safe shape of an approved venue booking (SCRUM-15) as the block
// calendar needs it; see lib/venue-block-options.ts for the same pattern.
import type { Slot } from "./venue-options";

export interface VenueBooking {
  id: string;
  venue_id: string;
  event_name: string | null;
  start_date: string;
  end_date: string;
  // SCRUM-65: the booked time on each date; slots are what it touches.
  start_minute: number;
  end_minute: number;
  slots: Slot[];
  status: "pending" | "approved" | "rejected";
}
