// Client-safe shape of an approved venue booking (SCRUM-15) as the block
// calendar needs it; see lib/venue-block-options.ts for the same pattern.
import type { Slot } from "./venue-options";

export interface VenueBooking {
  id: string;
  venue_id: string;
  event_name: string | null;
  start_date: string;
  end_date: string;
  slots: Slot[];
  status: "pending" | "approved" | "rejected";
}
