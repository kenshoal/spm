import { listEventArrangementReviews } from "@/lib/arrangement-reviews";
import {
  BOOKING_STATUS_LABELS,
  canCancelBooking,
  formatBookingDates,
  listEventBookings,
  needsNewVenue,
  type EventBooking,
} from "@/lib/event-bookings";
import { listVenues } from "@/lib/venues";
import { CancelBookingButton } from "./cancel-booking-button";
import { RequestReplacementForm } from "./request-replacement-form";
import { RequestVenueForm } from "./request-venue-form";
import { timeRangeLabel } from "@/lib/venue-options";

// Status is written out, never conveyed by colour alone.
const STATUS_STYLES: Record<EventBooking["status"], string> = {
  pending: "bg-[#fff9eb] text-[#6f4b12]",
  approved: "bg-[#e3f2ea] text-[#145c40]",
  rejected: "bg-[#fff1ee] text-[#8a3b25]",
  cancelled: "bg-[#eef1ef] text-[#526159]",
};

export function VenueBookingsList({
  bookings,
  venueNames,
  eventRequestId,
  needsNewVenue: flagged = new Map<string, string>(),
  replacementVenues = [],
}: {
  bookings: EventBooking[];
  venueNames: Map<string, string>;
  eventRequestId: string;
  // Booking id -> the reason a venue block flagged it (SCRUM-63).
  needsNewVenue?: Map<string, string>;
  replacementVenues?: { id: string; name: string; status?: string }[];
}) {
  if (bookings.length === 0) {
    return <p className="mt-3 text-sm text-[#718078]">No venue bookings yet.</p>;
  }
  return (
    <ul className="mt-4 space-y-3">
      {bookings.map((booking) => {
        const venueName = venueNames.get(booking.venue_id) ?? "Unknown venue";
        const reason = booking.status === "approved" ? flagged.get(booking.id) : undefined;
        const replaced = booking.replaces_booking_id ? bookings.find((item) => item.id === booking.replaces_booking_id) : undefined;
        // A pending or approved replacement stands in for the form; a rejected or cancelled one does not.
        const active = bookings.find(
          (item) => item.replaces_booking_id === booking.id && (item.status === "pending" || item.status === "approved"),
        );
        return (
          <li key={booking.id} className="flex flex-wrap items-start justify-between gap-3 rounded-xl border border-[#e1e7e4] p-4">
            <div>
              <p className="font-semibold text-[#1b2b25]">{venueName}</p>
              <p className="mt-1 text-sm text-[#526159]"><span>{formatBookingDates(booking.start_date, booking.end_date)}</span></p>
              <p className="text-sm text-[#526159]"><span>{timeRangeLabel(booking.start_minute, booking.end_minute)}</span></p>
              {replaced ? <p className="mt-1 text-sm text-[#526159]">Replaces the booking at {venueNames.get(replaced.venue_id) ?? "Unknown venue"}</p> : null}
              {reason ? (
                <div className="mt-2 rounded-lg border border-[#eccdbe] bg-[#fff8f3] px-3 py-2">
                  <p className="text-sm font-bold text-[#793f27]">Needs a new venue</p>
                  <p className="mt-1 text-xs text-[#793f27]">{reason}</p>
                  <RequestReplacementForm
                    bookingId={booking.id}
                    eventRequestId={eventRequestId}
                    venueName={venueName}
                    venues={replacementVenues.filter((venue) => venue.id !== booking.venue_id && (venue.status ?? "available") === "available")}
                    active={active ? { venueName: venueNames.get(active.venue_id) ?? "Unknown venue", statusLabel: BOOKING_STATUS_LABELS[active.status] } : undefined}
                  />
                </div>
              ) : null}
            </div>
            <div className="flex flex-col items-end gap-2">
              <span className={`rounded-full px-3 py-1 text-xs font-bold ${STATUS_STYLES[booking.status]}`}>{BOOKING_STATUS_LABELS[booking.status]}</span>
              {canCancelBooking(booking.status) ? (
                <CancelBookingButton bookingId={booking.id} eventRequestId={eventRequestId} venueName={venueName} />
              ) : null}
            </div>
          </li>
        );
      })}
    </ul>
  );
}

export function VenueBookingsLoading() {
  return <div aria-label="Loading venue bookings" className="mt-5 h-24 animate-pulse rounded-2xl border border-[#e1e7e4] bg-white" />;
}

// Every venue booking of the event and where each stands (SCRUM-61). A failed
// load is an error, never an empty list; a failed venue-name load still lists
// the bookings.
export async function VenueBookingsPanel({ eventRequestId, canRequest = false }: { eventRequestId: string; canRequest?: boolean }) {
  const [bookings, venues, reviews] = await Promise.all([
    listEventBookings(eventRequestId).then((value) => ({ value, failed: false as const })).catch(() => ({ value: [] as EventBooking[], failed: true as const })),
    listVenues().catch(() => []),
    listEventArrangementReviews(eventRequestId).then((value) => ({ value, failed: false as const })).catch(() => ({ value: [], failed: true as const })),
  ]);
  return (
    <section aria-label="Venue bookings" className="mt-5 rounded-2xl border border-[#dce4e0] bg-white p-6 sm:p-7">
      <h2 className="text-lg font-bold text-[#17211d]">Venue bookings</h2>
      {bookings.failed ? (
        <p role="alert" className="mt-3 rounded-xl border border-[#eccdbe] bg-[#fff8f3] px-4 py-3 text-sm text-[#793f27]">Venue bookings could not be loaded. Refresh to try again.</p>
      ) : (
        <>
          {reviews.failed ? (
            <p role="alert" className="mt-3 rounded-xl border border-[#eccdbe] bg-[#fff8f3] px-4 py-3 text-sm text-[#793f27]">Whether a booking needs a new venue could not be checked. Refresh to try again.</p>
          ) : null}
          <VenueBookingsList
            bookings={bookings.value}
            venueNames={new Map(venues.map((venue) => [venue.id, venue.name]))}
            eventRequestId={eventRequestId}
            needsNewVenue={needsNewVenue(reviews.value)}
            replacementVenues={venues}
          />
        </>
      )}
      {canRequest ? <RequestVenueForm eventRequestId={eventRequestId} venues={venues.map(({ id, name }) => ({ id, name }))} /> : null}
    </section>
  );
}
