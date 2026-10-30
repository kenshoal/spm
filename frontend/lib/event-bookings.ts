import { getJson } from "./api";
import type { ArrangementReview } from "./arrangement-reviews";
import type { Slot } from "./venue-options";
import { venueApiUrl } from "./venues";

// One venue booking request of an event (SCRUM-61), as the coordinator's event
// page shows it. Several of these can belong to one event.
export type EventBookingStatus = "pending" | "approved" | "rejected" | "cancelled";

export interface EventBooking {
  id: string;
  venue_id: string;
  start_date: string;
  end_date: string;
  // SCRUM-65: the booked time on each date.
  start_minute: number;
  end_minute: number;
  slots: Slot[];
  status: EventBookingStatus;
  created_at: string;
  cancelled_at: string | null;
  // SCRUM-63: the flagged booking this request replaces.
  replaces_booking_id: string | null;
}

export const BOOKING_STATUS_LABELS: Record<EventBookingStatus, string> = {
  pending: "Pending",
  approved: "Approved",
  rejected: "Rejected",
  cancelled: "Cancelled",
};

// The bookings a venue block flagged as needing a new venue (SCRUM-63), with the
// reason, from the event's arrangement reviews. A cleared flag, another cause and
// an equipment reservation do not count.
export function needsNewVenue(reviews: readonly ArrangementReview[]): Map<string, string> {
  const flagged = new Map<string, string>();
  for (const review of reviews) {
    if (review.arrangement === "venue_booking" && review.trigger_type === "venue_block" && review.cleared_at === null) {
      flagged.set(review.arrangement_id, review.reason);
    }
  }
  return flagged;
}

// Only a pending or an approved booking can be cancelled; the others are final.
export function canCancelBooking(status: EventBookingStatus): boolean {
  return status === "pending" || status === "approved";
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function formatDate(value: string): string {
  const [year, month, day] = value.split("-");
  return `${Number(day)} ${MONTHS[Number(month) - 1]} ${year}`;
}

export function formatBookingDates(start: string, end: string): string {
  return start === end ? formatDate(start) : `${formatDate(start)} – ${formatDate(end)}`;
}

// Every booking of one event, oldest first. A missing or refused event (the API
// answers 404 for an event the caller does not coordinate) throws, so the page
// shows an error and never an empty list that looks like "no bookings".
export async function listEventBookings(eventRequestId: string): Promise<EventBooking[]> {
  const bookings = await getJson<EventBooking[]>(
    venueApiUrl,
    `/booking-requests/event/${encodeURIComponent(eventRequestId)}`,
  );
  if (bookings === null) throw new Error("Venue bookings are not available for this event");
  return bookings;
}
