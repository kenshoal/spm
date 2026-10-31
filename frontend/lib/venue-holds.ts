import { getJson } from "./api";
import type { VenueHold } from "./venue-hold-form";
import { venueApiUrl } from "./venues";

// Every tentative hold of one event (SCRUM-18), oldest first. A missing or
// refused event (404 for an event the caller does not coordinate) throws, so the
// page shows an error and never an empty list that looks like "no holds".
export async function listEventHolds(eventRequestId: string): Promise<VenueHold[]> {
  const holds = await getJson<VenueHold[]>(
    venueApiUrl,
    `/venue-holds?event_request_id=${encodeURIComponent(eventRequestId)}`,
  );
  if (holds === null) throw new Error("Venue holds are not available for this event");
  return holds;
}
