import { unstable_rethrow } from "next/navigation";
import { getJson } from "@/lib/api";
import { formatBookingDates } from "@/lib/booking-dates";
import { timeRangeLabel } from "@/lib/venue-options";

const apiUrl = process.env.EVENT_REQUEST_API_URL ?? "http://127.0.0.1:8003";

interface Arrangements {
  venues: { name: string; location: string; start_date: string; end_date: string; start_minute: number; end_minute: number }[];
  equipment: { equipment_type: string; quantity: number; reserved: number }[];
}

// Hotfix 14 (Week 1 brief, step 10): the Organiser can see what is arranged.
export async function EventArrangementsPanel({ eventRequestId }: { eventRequestId: string }) {
  let arrangements: Arrangements | null = null;
  try {
    arrangements = await getJson<Arrangements>(apiUrl, `/event-requests/${encodeURIComponent(eventRequestId)}/arrangements`);
  } catch (error) {
    unstable_rethrow(error);
  }
  return (
    <section aria-label="Arrangements" className="mt-5 rounded-2xl border border-[#dce4e0] bg-white p-6 sm:p-7">
      <h2 className="text-lg font-bold text-[#17211d]">Arrangements</h2>
      {arrangements === null ? (
        <p role="alert" className="mt-3 rounded-xl border border-[#eccdbe] bg-[#fff8f3] px-4 py-3 text-sm text-[#793f27]">Arrangements could not be loaded. Refresh to try again.</p>
      ) : (
        <>
          {arrangements.venues.length === 0 ? (
            <p className="mt-3 text-sm text-[#718078]">No venue has been approved yet.</p>
          ) : (
            <ul className="mt-3 space-y-2 text-sm">
              {arrangements.venues.map((venue, index) => (
                <li key={index} className="rounded-xl bg-[#f4f7f5] px-4 py-3">
                  <span className="font-semibold text-[#17211d]">{venue.name}</span>, {venue.location}
                  <p className="mt-1 text-[#526159]">{formatBookingDates(venue.start_date, venue.end_date)}, {timeRangeLabel(venue.start_minute, venue.end_minute)}</p>
                </li>
              ))}
            </ul>
          )}
          {arrangements.equipment.length > 0 ? (
            <ul className="mt-3 space-y-2 text-sm">
              {arrangements.equipment.map((item, index) => (
                <li key={index} className="rounded-xl bg-[#f4f7f5] px-4 py-3">
                  <span className="font-semibold text-[#17211d]">{item.quantity} × {item.equipment_type}</span>{" · "}{item.reserved} reserved
                </li>
              ))}
            </ul>
          ) : null}
        </>
      )}
    </section>
  );
}
