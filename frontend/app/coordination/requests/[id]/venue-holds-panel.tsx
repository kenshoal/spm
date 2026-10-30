import { formatBookingDates } from "@/lib/event-bookings";
import { formatDateTime } from "@/lib/event-requests";
import { HOLD_STATUS_LABELS, type VenueHold } from "@/lib/venue-hold-form";
import { listEventHolds } from "@/lib/venue-holds";
import { timeRangeLabel } from "@/lib/venue-options";
import { listVenues } from "@/lib/venues";
import { HoldActions, PlaceHoldForm } from "./venue-hold-controls";

// Status is written out, never conveyed by colour alone.
const STATUS_STYLES: Record<VenueHold["status"], string> = {
  active: "bg-[#fff9eb] text-[#6f4b12]",
  released: "bg-[#eef1ef] text-[#526159]",
  converted: "bg-[#e3f2ea] text-[#145c40]",
  expired: "bg-[#eef1ef] text-[#526159]",
};

// An active hold stops protecting its time at expiry even before the sweep runs.
export function isHoldActive(hold: VenueHold, now: Date = new Date()): boolean {
  return hold.status === "active" && new Date(hold.expires_at).getTime() > now.getTime();
}

export function VenueHoldsList({
  holds,
  venueNames,
  eventRequestId,
  now = new Date(),
}: {
  holds: VenueHold[];
  venueNames: Map<string, string>;
  eventRequestId: string;
  now?: Date;
}) {
  if (holds.length === 0) {
    return <p className="mt-3 text-sm text-[#718078]">No venue holds yet.</p>;
  }
  return (
    <ul className="mt-4 space-y-3">
      {holds.map((hold) => {
        const venueName = venueNames.get(hold.venue_id) ?? "Unknown venue";
        const active = isHoldActive(hold, now);
        const status = hold.status === "active" && !active ? "expired" : hold.status;
        const requested = active && hold.booking_request_id !== null;
        return (
          <li key={hold.id} className="flex flex-wrap items-start justify-between gap-3 rounded-xl border border-[#e1e7e4] p-4">
            <div>
              <p className="font-semibold text-[#1b2b25]">{venueName}</p>
              <p className="mt-1 text-sm text-[#526159]">{formatBookingDates(hold.start_date, hold.end_date)}</p>
              <p className="text-sm text-[#526159]">{timeRangeLabel(hold.start_minute, hold.end_minute)}</p>
              {active ? (
                <p className="mt-1 text-sm text-[#6f4b12]">
                  {requested ? "Booking requested; held until Venue Staff decide or " : "Held until "}
                  {formatDateTime(hold.expires_at)}
                </p>
              ) : null}
            </div>
            <div className="flex flex-col items-end gap-2">
              <span className={`rounded-full px-3 py-1 text-xs font-bold ${STATUS_STYLES[status]}`}>{HOLD_STATUS_LABELS[status]}</span>
              {active ? (
                <HoldActions holdId={hold.id} eventRequestId={eventRequestId} venueName={venueName} canConvert={!requested} />
              ) : null}
            </div>
          </li>
        );
      })}
    </ul>
  );
}

export function VenueHoldsLoading() {
  return <div aria-label="Loading venue holds" className="mt-5 h-24 animate-pulse rounded-2xl border border-[#e1e7e4] bg-white" />;
}

// The event's tentative venue holds and a form to place one (SCRUM-18). A failed
// load is an error, never an empty list.
export async function VenueHoldsPanel({ eventRequestId, canPlace }: { eventRequestId: string; canPlace: boolean }) {
  const [holds, venues] = await Promise.all([
    listEventHolds(eventRequestId).then((value) => ({ value, failed: false as const })).catch(() => ({ value: [] as VenueHold[], failed: true as const })),
    listVenues().catch(() => []),
  ]);
  return (
    <section aria-label="Venue holds" className="mt-5 rounded-2xl border border-[#dce4e0] bg-white p-6 sm:p-7">
      <h2 className="text-lg font-bold text-[#17211d]">Venue holds</h2>
      <p className="mt-1 text-sm text-[#68776f]">
        Hold a venue while the event is being finalised. A hold lasts at most 7 days; you are told 24 hours before it expires.
      </p>
      {holds.failed ? (
        <p role="alert" className="mt-3 rounded-xl border border-[#eccdbe] bg-[#fff8f3] px-4 py-3 text-sm text-[#793f27]">Venue holds could not be loaded. Refresh to try again.</p>
      ) : (
        <VenueHoldsList
          holds={holds.value}
          venueNames={new Map(venues.map((venue) => [venue.id, venue.name]))}
          eventRequestId={eventRequestId}
        />
      )}
      {canPlace ? <PlaceHoldForm eventRequestId={eventRequestId} venues={venues.map(({ id, name }) => ({ id, name }))} /> : null}
    </section>
  );
}
