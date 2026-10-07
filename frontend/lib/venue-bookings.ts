import { getJson } from "./api";
import type { VenueBooking } from "./venue-booking-options";
import { venueApiUrl } from "./venues";

// Approved booking requests are the confirmed bookings (SCRUM-15). Venue Staff
// read them from the SCRUM-32 queue endpoint; any failure throws so the page
// never shows booked slots as available.
export async function listApprovedBookings(): Promise<VenueBooking[]> {
  return (await getJson<VenueBooking[]>(venueApiUrl, "/booking-requests?status=approved")) ?? [];
}
