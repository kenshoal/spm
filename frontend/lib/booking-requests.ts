import { getJson } from "./api";
import type { BookingRequestItem, BookingStatus } from "./booking-decision-form";
import { venueApiUrl } from "./venues";

// The Venue Staff queue for one status (SCRUM-32 endpoint); pending is oldest
// first so staff work through requests in order. Failures throw so the page
// shows an outage rather than an empty queue.
export async function listBookingRequests(status: BookingStatus): Promise<BookingRequestItem[]> {
  return (await getJson<BookingRequestItem[]>(venueApiUrl, `/booking-requests?status=${status}`)) ?? [];
}
