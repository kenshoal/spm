import type { EventChangeBookingPlanItem } from "@/lib/event-requests";
import { formatBookingMinute } from "@/lib/booking-plan-format";

/** Saved accepted ranges are decision evidence, separate from the original proposal. */
export function AppliedBookingPlan({ plan }: { plan?: EventChangeBookingPlanItem[] | null }) {
  if (plan === undefined || plan === null) return null;
  return (
    <section aria-label="Applied booking ranges" className="mt-3 rounded-lg bg-[#f4f8f6] p-3 text-sm">
      <h4 className="font-semibold">Applied booking ranges</h4>
      {plan.length === 0 ? <p className="mt-2">No venue bookings required moving.</p> : <ul className="mt-2 space-y-2">
        {plan.map((row) => <li key={row.booking_id} className="break-words">
          <p className="break-all">Booking {row.booking_id}</p>
          <p><time dateTime={row.start_date}>{row.start_date}</time> to <time dateTime={row.end_date}>{row.end_date}</time> · {formatBookingMinute(row.start_minute)}–{formatBookingMinute(row.end_minute)} (Singapore)</p>
        </li>)}
      </ul>}
    </section>
  );
}
