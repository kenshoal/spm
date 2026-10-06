import { getJson } from "./api";
import type { VenueBlock } from "./venue-block-options";
import { venueApiUrl } from "./venues";

// Every recorded block for a venue, including lifted ones. null means the
// venue no longer exists; any other failure throws so the page can show an
// outage instead of an all-available calendar.
export async function listVenueBlocks(venueId: string): Promise<VenueBlock[] | null> {
  return getJson<VenueBlock[]>(venueApiUrl, `/venues/${encodeURIComponent(venueId)}/blocks`);
}
