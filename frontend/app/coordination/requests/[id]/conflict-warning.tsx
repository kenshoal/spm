import { formatBookingDates } from "@/lib/booking-dates";
import { timeRangeLabel } from "@/lib/venue-options";

export interface BookingConflict {
  start_date: string;
  end_date: string;
  start_minute: number;
  end_minute: number;
}

// SCRUM-67: the approved bookings a new request overlaps, as dates and times only.
// A warning in words, not an error: the request has been submitted and Venue Staff
// still decide it.
export function ConflictWarning({ venueName, conflicts }: { venueName: string; conflicts: BookingConflict[] }) {
  if (conflicts.length === 0) return null;
  return (
    <div role="status" className="basis-full rounded-lg border border-[#eccdbe] bg-[#fff8f3] px-3 py-2 text-sm text-[#793f27]">
      <p className="font-bold">{venueName} already has an approved booking that overlaps this request</p>
      <ul className="mt-1 list-disc pl-5">
        {conflicts.map((conflict, index) => (
          <li key={index}>{formatBookingDates(conflict.start_date, conflict.end_date)}, {timeRangeLabel(conflict.start_minute, conflict.end_minute)}</li>
        ))}
      </ul>
      <p className="mt-1 text-xs">The overlap counts setup and turnaround time. The request has still been submitted, but Venue Staff will probably refuse it unless that booking changes.</p>
    </div>
  );
}
