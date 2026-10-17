import {
  BOOKING_STATUS_LABELS,
  canCancelBooking,
  formatBookingDates,
  listEventBookings,
  type EventBooking,
} from "@/lib/event-bookings";
import { listVenues } from "@/lib/venues";
import { CancelBookingButton } from "./cancel-booking-button";

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
}: {
  bookings: EventBooking[];
  venueNames: Map<string, string>;
  eventRequestId: string;
}) {
  if (bookings.length === 0) {
    return <p className="mt-3 text-sm text-[#718078]">No venue bookings yet.</p>;
  }
  return (
    <ul className="mt-4 space-y-3">
      {bookings.map((booking) => {
        const venueName = venueNames.get(booking.venue_id) ?? "Unknown venue";
        return (
          <li key={booking.id} className="flex flex-wrap items-start justify-between gap-3 rounded-xl border border-[#e1e7e4] p-4">
            <div>
              <p className="font-semibold text-[#1b2b25]">{venueName}</p>
              <p className="mt-1 text-sm text-[#526159]"><span>{formatBookingDates(booking.start_date, booking.end_date)}</span></p>
              <p className="text-sm text-[#526159]"><span>{booking.slots.join(", ")}</span></p>
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
export async function VenueBookingsPanel({ eventRequestId }: { eventRequestId: string }) {
  const [bookings, venues] = await Promise.all([
    listEventBookings(eventRequestId).then((value) => ({ value, failed: false as const })).catch(() => ({ value: [] as EventBooking[], failed: true as const })),
    listVenues().catch(() => []),
  ]);
  return (
    <section aria-label="Venue bookings" className="mt-5 rounded-2xl border border-[#dce4e0] bg-white p-6 sm:p-7">
      <h2 className="text-lg font-bold text-[#17211d]">Venue bookings</h2>
      {bookings.failed ? (
        <p role="alert" className="mt-3 rounded-xl border border-[#eccdbe] bg-[#fff8f3] px-4 py-3 text-sm text-[#793f27]">Venue bookings could not be loaded. Refresh to try again.</p>
      ) : (
        <VenueBookingsList
          bookings={bookings.value}
          venueNames={new Map(venues.map((venue) => [venue.id, venue.name]))}
          eventRequestId={eventRequestId}
        />
      )}
    </section>
  );
}
